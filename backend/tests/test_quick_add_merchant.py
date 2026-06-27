"""POST /api/v1/transactions/quick-add — basic merchant input slice.

Extends Quick Add with an optional `merchant_input` (typed merchant text,
MERCHANT_NORMALIZATION_SPEC §4/§7). Covers:
- amount-only and amount+category still work (no regression)
- typed merchant creates a merchant and links it on the transaction
- response carries merchant_id / merchant_display_name; raw input persisted
- a case/whitespace variant reuses the SAME merchant (normalized_exact)
- cross-script / typo inputs do NOT silently merge (separate merchants)
- client-supplied user_id never owns the merchant or the transaction
- no merchant_aliases and no category_rules are created in this slice
- no PII (merchant text / normalized key / amount) appears in logs

Fresh ephemeral principal per test; all need a migrated DB.
"""

from __future__ import annotations

import logging
import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

import app.db as _db
from app.config import get_settings
from app.db import get_sessionmaker
from app.logging_utils import get_logger
from app.main import create_app


@pytest_asyncio.fixture(autouse=True)
async def _fresh_global_engine():
    _db._engine = None
    _db._sessionmaker = None
    yield
    await _db.dispose_engine()


@pytest.fixture
def principal(monkeypatch) -> tuple[str, str]:
    token = "test-qamerch-token-5p"
    uid = str(uuid.uuid4())
    monkeypatch.setenv("DEV_BEARER_TOKEN", token)
    monkeypatch.setenv("DEV_USER_ID", uid)
    get_settings.cache_clear()
    yield token, uid
    get_settings.cache_clear()


async def _ensure_user(uid: str) -> None:
    async with get_sessionmaker()() as s:
        await s.execute(
            text(
                "INSERT INTO users (id, base_currency, locale) "
                "SELECT :u, 'ILS', 'en' "
                "WHERE NOT EXISTS (SELECT 1 FROM users WHERE id = :u)"
            ),
            {"u": uid},
        )
        await s.commit()


async def _consumer_category() -> str:
    async with get_sessionmaker()() as s:
        return (
            await s.execute(
                text(
                    "SELECT id::text AS id FROM categories "
                    "WHERE layer = 'consumer_spending' AND user_id IS NULL LIMIT 1"
                )
            )
        ).scalar_one()


async def _txn_row(txn_id: str):
    async with get_sessionmaker()() as s:
        return (
            await s.execute(
                text(
                    "SELECT user_id::text AS user_id, merchant_id::text AS merchant_id, "
                    "raw_merchant_input, category_id::text AS category_id "
                    "FROM transactions WHERE id = CAST(:id AS uuid)"
                ),
                {"id": txn_id},
            )
        ).mappings().one_or_none()


async def _merchant_row(merchant_id: str):
    async with get_sessionmaker()() as s:
        return (
            await s.execute(
                text(
                    "SELECT user_id::text AS user_id, normalized_merchant_name, "
                    "display_name FROM merchants WHERE id = CAST(:id AS uuid)"
                ),
                {"id": merchant_id},
            )
        ).mappings().one_or_none()


async def _count(table: str, uid: str) -> int:
    async with get_sessionmaker()() as s:
        return (
            await s.execute(
                text(f"SELECT count(*) FROM {table} WHERE user_id = :u"), {"u": uid}
            )
        ).scalar_one()


def _client(app):
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def _quick_add(token: str, payload: dict):
    app = create_app()
    async with _client(app) as c:
        return await c.post(
            "/api/v1/transactions/quick-add", json=payload,
            headers={"Authorization": f"Bearer {token}"},
        )


# --------------------------------------------------------------------------- #
# Regression: prior behavior unchanged.
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_amount_only_still_works(principal, migrated: None) -> None:
    token, uid = principal
    await _ensure_user(uid)
    txn = (await _quick_add(token, {"amount": "33.50"})).json()["transaction"]
    assert txn["amount_minor"] == -3350
    assert txn["merchant_id"] is None and txn["merchant_display_name"] is None
    assert await _count("merchants", uid) == 0  # no merchant created


@pytest.mark.asyncio
async def test_amount_plus_category_still_works(principal, migrated: None) -> None:
    token, uid = principal
    await _ensure_user(uid)
    cat = await _consumer_category()
    txn = (await _quick_add(token, {"amount": "10.00", "category_id": cat})).json()["transaction"]
    assert txn["category_id"] == cat
    assert txn["merchant_id"] is None


# --------------------------------------------------------------------------- #
# Merchant create / link.
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_merchant_input_creates_and_links(principal, migrated: None) -> None:
    token, uid = principal
    await _ensure_user(uid)
    resp = await _quick_add(token, {"amount": "33.50", "merchant_input": "Golda"})
    assert resp.status_code == 201
    txn = resp.json()["transaction"]
    # Response carries the contract's merchant fields.
    assert txn["merchant_id"] is not None
    assert txn["merchant_display_name"] == "Golda"
    # DB: transaction links the merchant; raw input preserved; merchant owned + normalized.
    row = await _txn_row(txn["id"])
    assert row["merchant_id"] == txn["merchant_id"]
    assert row["raw_merchant_input"] == "Golda"
    m = await _merchant_row(txn["merchant_id"])
    assert m["normalized_merchant_name"] == "golda"
    assert m["display_name"] == "Golda"
    assert m["user_id"] == uid
    assert await _count("merchants", uid) == 1


@pytest.mark.asyncio
async def test_case_whitespace_variant_reuses_merchant(principal, migrated: None) -> None:
    token, uid = principal
    await _ensure_user(uid)
    first = (await _quick_add(token, {"amount": "5.00", "merchant_input": "Golda"})).json()
    second = (await _quick_add(token, {"amount": "6.00", "merchant_input": "  golda  "})).json()
    # Same normalized key -> same merchant reused (normalized_exact, §7).
    assert first["transaction"]["merchant_id"] == second["transaction"]["merchant_id"]
    assert await _count("merchants", uid) == 1
    # Display keeps the FIRST-created form.
    assert second["transaction"]["merchant_display_name"] == "Golda"


@pytest.mark.asyncio
async def test_cross_script_and_typo_do_not_merge(principal, migrated: None) -> None:
    token, uid = principal
    await _ensure_user(uid)
    en = (await _quick_add(token, {"amount": "5.00", "merchant_input": "Golda"})).json()
    he = (await _quick_add(token, {"amount": "6.00", "merchant_input": "גולדה"})).json()
    typo = (await _quick_add(token, {"amount": "7.00", "merchant_input": "Goldaa"})).json()
    ids = {
        en["transaction"]["merchant_id"],
        he["transaction"]["merchant_id"],
        typo["transaction"]["merchant_id"],
    }
    assert len(ids) == 3  # no silent cross-script or fuzzy merge
    assert await _count("merchants", uid) == 3


@pytest.mark.asyncio
async def test_blank_merchant_input_is_no_merchant(principal, migrated: None) -> None:
    token, uid = principal
    await _ensure_user(uid)
    txn = (await _quick_add(token, {"amount": "5.00", "merchant_input": "   "})).json()["transaction"]
    assert txn["merchant_id"] is None
    assert await _count("merchants", uid) == 0


# --------------------------------------------------------------------------- #
# Ownership / scope guards.
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_forged_user_id_ignored(principal, migrated: None) -> None:
    token, uid = principal
    await _ensure_user(uid)
    other = str(uuid.uuid4())
    txn = (
        await _quick_add(token, {"amount": "9.00", "merchant_input": "Golda", "user_id": other})
    ).json()["transaction"]
    row = await _txn_row(txn["id"])
    m = await _merchant_row(txn["merchant_id"])
    # Both the transaction and the merchant belong to the server-resolved principal.
    assert row["user_id"] == uid
    assert m["user_id"] == uid


@pytest.mark.asyncio
async def test_no_aliases_or_rules_created(principal, migrated: None) -> None:
    token, uid = principal
    await _ensure_user(uid)
    cat = await _consumer_category()
    assert (
        await _quick_add(
            token, {"amount": "9.00", "merchant_input": "Golda", "category_id": cat}
        )
    ).status_code == 201
    assert await _count("merchant_aliases", uid) == 0  # no alias in this slice
    assert await _count("category_rules", uid) == 0    # no rule promotion


@pytest.mark.asyncio
async def test_no_pii_in_logs(principal, migrated: None) -> None:
    token, uid = principal
    await _ensure_user(uid)
    secret_merchant = "SecretShopXY"
    secret_note = "qamerch-note-qq"

    records: list[logging.LogRecord] = []

    class _Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    handler = _Capture()
    logger = get_logger()
    prev = logger.level
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    try:
        resp = await _quick_add(
            token,
            {"amount": "35.90", "merchant_input": secret_merchant, "note": secret_note},
        )
    finally:
        logger.removeHandler(handler)
        logger.setLevel(prev)

    assert resp.status_code == 201
    assert records
    for r in records:
        rendered = r.getMessage() + " " + " ".join(str(v) for v in (r.args or ()))
        assert secret_merchant not in rendered            # merchant text
        assert secret_merchant.casefold() not in rendered  # normalized key
        assert secret_note not in rendered
        assert "35.90" not in rendered and "3590" not in rendered
