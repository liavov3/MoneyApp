"""POST /api/v1/transactions/quick-add — basic merchant input slice.

Extends Quick Add with an optional `merchant_input` (typed merchant text,
MERCHANT_NORMALIZATION_SPEC §4/§7). Covers:
- amount-only and amount+category still work (no regression)
- typed merchant creates a merchant and links it on the transaction
- pre-resolved merchant_id is ownership-safe and wins over typed text
- user-confirmed aliases resolve to their canonical merchant
- response carries merchant_id / merchant_display_name; raw input persisted
- a case/whitespace variant reuses the SAME merchant (normalized_exact)
- cross-script / typo inputs do NOT silently merge (separate merchants)
- client-supplied user_id never owns the merchant or the transaction
- a new merchant gets a low-trust first alias; no category rules are created
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


async def _seed_merchant(uid: str, normalized: str, display: str) -> str:
    async with get_sessionmaker()() as s:
        mid = (
            await s.execute(
                text(
                    "INSERT INTO merchants (user_id, normalized_merchant_name, display_name) "
                    "VALUES (:u, :n, :d) RETURNING id::text AS id"
                ),
                {"u": uid, "n": normalized, "d": display},
            )
        ).scalar_one()
        await s.commit()
        return mid


async def _seed_confirmed_alias(uid: str, mid: str, raw: str, normalized: str) -> None:
    async with get_sessionmaker()() as s:
        await s.execute(
            text(
                "INSERT INTO merchant_aliases "
                "(user_id, merchant_id, alias_text, normalized_alias_key, source, confidence) "
                "VALUES (:u, CAST(:m AS uuid), :raw, :n, 'user_confirmed', "
                "'user_confirmed')"
            ),
            {"u": uid, "m": mid, "raw": raw, "n": normalized},
        )
        await s.commit()


async def _alias_rows(uid: str) -> list[dict]:
    async with get_sessionmaker()() as s:
        rows = (
            await s.execute(
                text(
                    "SELECT merchant_id::text AS merchant_id, alias_text, "
                    "normalized_alias_key, source, confidence FROM merchant_aliases "
                    "WHERE user_id = :u ORDER BY created_at"
                ),
                {"u": uid},
            )
        ).mappings().all()
        return [dict(r) for r in rows]


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
    assert await _alias_rows(uid) == [
        {
            "merchant_id": txn["merchant_id"],
            "alias_text": "Golda",
            "normalized_alias_key": "golda",
            "source": "system_suggested",
            "confidence": "none",
        }
    ]


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
# Pre-resolved merchant id and confirmed aliases.
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_valid_merchant_id_links_existing_merchant(principal, migrated: None) -> None:
    token, uid = principal
    await _ensure_user(uid)
    mid = await _seed_merchant(uid, "golda", "Golda")

    resp = await _quick_add(token, {"amount": "12.00", "merchant_id": mid})
    assert resp.status_code == 201
    txn = resp.json()["transaction"]
    assert txn["merchant_id"] == mid
    assert txn["merchant_display_name"] == "Golda"
    assert (await _txn_row(txn["id"]))["raw_merchant_input"] is None
    assert await _count("merchants", uid) == 1


@pytest.mark.asyncio
async def test_merchant_id_wins_and_typed_text_is_preserved(
    principal, migrated: None
) -> None:
    token, uid = principal
    await _ensure_user(uid)
    mid = await _seed_merchant(uid, "golda", "Golda")

    resp = await _quick_add(
        token, {"amount": "12.00", "merchant_id": mid, "merchant_input": "  Wolt  "}
    )
    assert resp.status_code == 201
    txn = resp.json()["transaction"]
    assert txn["merchant_id"] == mid
    assert txn["merchant_display_name"] == "Golda"
    assert (await _txn_row(txn["id"]))["raw_merchant_input"] == "  Wolt  "
    assert await _count("merchants", uid) == 1  # no Wolt merchant was created


@pytest.mark.asyncio
@pytest.mark.parametrize("merchant_id", ["not-a-uuid", str(uuid.uuid4())])
async def test_invalid_or_missing_merchant_id_returns_404(
    principal, migrated: None, merchant_id: str
) -> None:
    token, uid = principal
    await _ensure_user(uid)
    resp = await _quick_add(token, {"amount": "12.00", "merchant_id": merchant_id})
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "not_found"
    assert await _count("transactions", uid) == 0


@pytest.mark.asyncio
async def test_foreign_merchant_id_returns_404(principal, migrated: None) -> None:
    token, uid = principal
    await _ensure_user(uid)
    other = str(uuid.uuid4())
    await _ensure_user(other)
    foreign_mid = await _seed_merchant(other, "foreign", "Foreign")

    resp = await _quick_add(token, {"amount": "12.00", "merchant_id": foreign_mid})
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "not_found"
    assert await _count("transactions", uid) == 0


@pytest.mark.asyncio
async def test_typed_confirmed_alias_resolves_without_duplicate(
    principal, migrated: None
) -> None:
    token, uid = principal
    await _ensure_user(uid)
    mid = await _seed_merchant(uid, "golda", "Golda")
    await _seed_confirmed_alias(uid, mid, "גולדה", "גולדה")

    resp = await _quick_add(token, {"amount": "12.00", "merchant_input": "גולדה"})
    assert resp.status_code == 201
    txn = resp.json()["transaction"]
    assert txn["merchant_id"] == mid
    assert txn["merchant_display_name"] == "Golda"
    assert (await _txn_row(txn["id"]))["raw_merchant_input"] == "גולדה"
    assert await _count("merchants", uid) == 1
    assert await _count("merchant_aliases", uid) == 1


@pytest.mark.asyncio
async def test_exact_canonical_precedes_ambiguous_alias_then_alias_precedes_normalized(
    principal, migrated: None
) -> None:
    token, uid = principal
    await _ensure_user(uid)
    canonical = await _seed_merchant(uid, "wolt", "Wolt")
    aliased = await _seed_merchant(uid, "golda", "Golda")
    # Cross-table ambiguity is possible: alias keys and canonical keys have
    # separate uniqueness constraints.
    await _seed_confirmed_alias(uid, aliased, "wolt", "wolt")

    exact = (
        await _quick_add(token, {"amount": "5.00", "merchant_input": "Wolt"})
    ).json()["transaction"]
    alias_variant = (
        await _quick_add(token, {"amount": "6.00", "merchant_input": "wolt"})
    ).json()["transaction"]
    whitespace_variant = (
        await _quick_add(token, {"amount": "7.00", "merchant_input": "  Wolt  "})
    ).json()["transaction"]

    assert exact["merchant_id"] == canonical  # exact canonical wins
    assert alias_variant["merchant_id"] == aliased  # alias beats normalized canonical
    assert whitespace_variant["merchant_id"] == aliased
    assert await _count("merchants", uid) == 2


@pytest.mark.asyncio
async def test_id_only_request_returns_recent_memory_category_suggestion(
    principal, migrated: None
) -> None:
    token, uid = principal
    await _ensure_user(uid)
    cat = await _consumer_category()
    first = (
        await _quick_add(
            token, {"amount": "5.00", "merchant_input": "Golda", "category_id": cat}
        )
    ).json()["transaction"]

    resp = await _quick_add(token, {"amount": "6.00", "merchant_id": first["merchant_id"]})
    assert resp.status_code == 201
    suggestion = resp.json()["category_suggestion"]
    assert suggestion["category_id"] == cat
    assert suggestion["source"] == "recent_memory"
    assert resp.json()["transaction"]["category_id"] is None  # suggest-only


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
async def test_initial_alias_but_no_rules_created(principal, migrated: None) -> None:
    token, uid = principal
    await _ensure_user(uid)
    cat = await _consumer_category()
    assert (
        await _quick_add(
            token, {"amount": "9.00", "merchant_input": "Golda", "category_id": cat}
        )
    ).status_code == 201
    aliases = await _alias_rows(uid)
    assert len(aliases) == 1
    assert aliases[0]["source"] == "system_suggested"
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
