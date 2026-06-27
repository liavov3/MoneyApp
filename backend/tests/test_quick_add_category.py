"""POST /api/v1/transactions/quick-add — category-on-create slice (API_CONTRACT §8).

Extends amount-only Quick Add to accept an optional `category_id`. Covers:
- amount-only create still works (no regression); category fields stay null
- a valid consumer category persists category_id and returns category_key
- response carries the contract's category fields exactly
- bank_movement -> not_consumer_category; unknown/malformed -> invalid_category
- omitted category -> null; client-supplied user_id is ignored (server-resolved)
- setting a category creates NO category_rules row
- no PII (amount / note / category text) appears in logs

Fresh ephemeral principal per test. 401-style/no-DB cases are covered by the
existing test_quick_add.py; these need a migrated DB (categories seeded by 0002).
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
    token = "test-qacat-token-3m"
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


async def _category(layer: str) -> tuple[str, str]:
    """Return (id, key) for a seeded system category of the given layer."""
    async with get_sessionmaker()() as s:
        r = (
            await s.execute(
                text(
                    "SELECT id::text AS id, key FROM categories "
                    "WHERE layer = :l AND user_id IS NULL LIMIT 1"
                ),
                {"l": layer},
            )
        ).mappings().one()
        return r["id"], r["key"]


async def _raw_row(txn_id: str):
    async with get_sessionmaker()() as s:
        return (
            await s.execute(
                text(
                    "SELECT user_id::text AS user_id, amount_minor, "
                    "category_id::text AS category_id "
                    "FROM transactions WHERE id = CAST(:id AS uuid)"
                ),
                {"id": txn_id},
            )
        ).mappings().one_or_none()


async def _rules_count(uid: str) -> int:
    async with get_sessionmaker()() as s:
        return (
            await s.execute(
                text("SELECT count(*) FROM category_rules WHERE user_id = :u"),
                {"u": uid},
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


def _field_code(resp) -> str:
    return resp.json()["error"]["field_errors"][0]["code"]


# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_amount_only_still_works(principal, migrated: None) -> None:
    token, uid = principal
    await _ensure_user(uid)
    resp = await _quick_add(token, {"amount": "33.50"})
    assert resp.status_code == 201
    txn = resp.json()["transaction"]
    assert txn["amount_minor"] == -3350
    assert txn["category_id"] is None and txn["category_key"] is None  # uncategorized


@pytest.mark.asyncio
async def test_valid_category_saved_and_returned(principal, migrated: None) -> None:
    token, uid = principal
    await _ensure_user(uid)
    cat_id, cat_key = await _category("consumer_spending")

    resp = await _quick_add(token, {"amount": "33.50", "category_id": cat_id})
    assert resp.status_code == 201
    txn = resp.json()["transaction"]
    # Response carries the contract's category fields exactly.
    assert txn["category_id"] == cat_id
    assert txn["category_key"] == cat_key
    # DB proof: the row persisted the category.
    assert (await _raw_row(txn["id"]))["category_id"] == cat_id


@pytest.mark.asyncio
async def test_bank_movement_category_rejected(principal, migrated: None) -> None:
    token, uid = principal
    await _ensure_user(uid)
    bank_id, _ = await _category("bank_movement")
    resp = await _quick_add(token, {"amount": "33.50", "category_id": bank_id})
    assert resp.status_code == 422
    assert _field_code(resp) == "not_consumer_category"


@pytest.mark.asyncio
async def test_unknown_and_malformed_category_rejected(principal, migrated: None) -> None:
    token, uid = principal
    await _ensure_user(uid)
    unknown = await _quick_add(token, {"amount": "5.00", "category_id": str(uuid.uuid4())})
    assert unknown.status_code == 422 and _field_code(unknown) == "invalid_category"
    malformed = await _quick_add(token, {"amount": "5.00", "category_id": "not-a-uuid"})
    assert malformed.status_code == 422 and _field_code(malformed) == "invalid_category"


@pytest.mark.asyncio
async def test_omitted_category_is_null(principal, migrated: None) -> None:
    token, uid = principal
    await _ensure_user(uid)
    txn = (await _quick_add(token, {"amount": "5.00"})).json()["transaction"]
    assert txn["category_id"] is None and txn["category_key"] is None
    assert (await _raw_row(txn["id"]))["category_id"] is None


@pytest.mark.asyncio
async def test_forged_user_id_ignored(principal, migrated: None) -> None:
    token, uid = principal
    await _ensure_user(uid)
    cat_id, _ = await _category("consumer_spending")
    other = str(uuid.uuid4())

    txn = (
        await _quick_add(token, {"amount": "9.00", "category_id": cat_id, "user_id": other})
    ).json()["transaction"]
    # The saved row is owned by the server-resolved principal, never the forged id.
    assert (await _raw_row(txn["id"]))["user_id"] == uid


@pytest.mark.asyncio
async def test_category_creates_no_rule(principal, migrated: None) -> None:
    token, uid = principal
    await _ensure_user(uid)
    cat_id, _ = await _category("consumer_spending")
    assert await _rules_count(uid) == 0
    assert (await _quick_add(token, {"amount": "9.00", "category_id": cat_id})).status_code == 201
    assert await _rules_count(uid) == 0  # no rule promotion in this slice


@pytest.mark.asyncio
async def test_no_pii_in_logs(principal, migrated: None) -> None:
    token, uid = principal
    await _ensure_user(uid)
    cat_id, cat_key = await _category("consumer_spending")
    secret_note = "qacat-secret-note-vv"

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
            token, {"amount": "35.90", "note": secret_note, "category_id": cat_id}
        )
    finally:
        logger.removeHandler(handler)
        logger.setLevel(prev)

    assert resp.status_code == 201
    assert records
    for r in records:
        rendered = r.getMessage() + " " + " ".join(str(v) for v in (r.args or ()))
        assert secret_note not in rendered
        assert "35.90" not in rendered
        assert "3590" not in rendered
        assert cat_key not in rendered  # category text never logged
