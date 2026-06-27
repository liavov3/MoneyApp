"""PATCH /api/v1/transactions/{id} — partial edit slice (API_CONTRACT §9).

Covers:
- missing/invalid token -> 401 envelope
- malformed id -> 404; missing id -> 404; empty body -> 422 validation_error
- owned patch of note / amount / occurred_on / category -> 200, exact DB writes
- amount re-normalized to signed agorot; "33.555"/"0" rejected, row UNCHANGED
- partial update: omitted fields stay unchanged
- category: consumer set/clear; bank_movement -> not_consumer_category; unknown
  -> invalid_category
- created_at never changes; updated_at advances on success
- another user's row -> 404 (not 403), row untouched; forged ?user_id ignored
- no PII (amount / note / raw input) appears in logs

Each test uses a fresh ephemeral principal. 401 / malformed-id / empty-body
need no DB; the rest require a migrated DB (categories seeded by 0002).
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
    token = "test-patch-token-9k"
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


async def _insert_txn(uid: str, amount_minor: int) -> str:
    async with get_sessionmaker()() as s:
        row = (
            await s.execute(
                text(
                    "INSERT INTO transactions "
                    "(user_id, amount_minor, currency, transaction_type, source) "
                    "VALUES (:u, :a, 'ILS', 'expense', 'manual') "
                    "RETURNING id::text AS id"
                ),
                {"u": uid, "a": amount_minor},
            )
        ).mappings().one()
        await s.commit()
        return row["id"]


async def _raw_row(txn_id: str):
    """Full-precision DB snapshot (timestamps kept as datetimes for ordering)."""
    async with get_sessionmaker()() as s:
        return (
            await s.execute(
                text(
                    "SELECT amount_minor, note, transaction_type, "
                    "category_id::text AS category_id, occurred_on::text AS occurred_on, "
                    "created_at, updated_at "
                    "FROM transactions WHERE id = CAST(:id AS uuid)"
                ),
                {"id": txn_id},
            )
        ).mappings().one_or_none()


async def _category_id(layer: str) -> str:
    async with get_sessionmaker()() as s:
        return (
            await s.execute(
                text(
                    "SELECT id::text AS id FROM categories "
                    "WHERE layer = :l AND user_id IS NULL LIMIT 1"
                ),
                {"l": layer},
            )
        ).mappings().one()["id"]


def _client(app):
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def _patch(token, txn_id, body=None, params=None):
    app = create_app()
    headers = {}
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    async with _client(app) as c:
        return await c.patch(
            f"/api/v1/transactions/{txn_id}", json=body, params=params, headers=headers
        )


async def _quick_add(token: str, payload: dict):
    app = create_app()
    async with _client(app) as c:
        return await c.post(
            "/api/v1/transactions/quick-add", json=payload,
            headers={"Authorization": f"Bearer {token}"},
        )


def _assert_401(resp) -> None:
    assert resp.status_code == 401
    err = resp.json()["error"]
    assert err["code"] == "unauthorized"
    assert err["message"] == "Authentication required."
    assert err["request_id"]
    assert "field_errors" not in err


def _assert_404(resp) -> None:
    assert resp.status_code == 404
    err = resp.json()["error"]
    assert err["code"] == "not_found"
    assert err["message"] == "Resource not found."
    assert err["request_id"]


def _field_code(resp) -> str:
    return resp.json()["error"]["field_errors"][0]["code"]


# --------------------------------------------------------------------------- #
# Auth + shape — no DB required.
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_missing_token_returns_401(principal) -> None:
    _assert_401(await _patch(None, str(uuid.uuid4()), {"note": "x"}))


@pytest.mark.asyncio
async def test_invalid_token_returns_401(principal) -> None:
    _assert_401(await _patch("wrong-token", str(uuid.uuid4()), {"note": "x"}))


@pytest.mark.asyncio
async def test_malformed_id_returns_404(principal) -> None:
    token, _ = principal
    _assert_404(await _patch(token, "not-a-uuid", {"note": "x"}))


@pytest.mark.asyncio
async def test_empty_body_returns_validation_error(principal) -> None:
    token, _ = principal
    resp = await _patch(token, str(uuid.uuid4()), {})
    assert resp.status_code == 422
    assert resp.json()["error"]["code"] == "validation_error"
    assert _field_code(resp) == "empty_patch"


# --------------------------------------------------------------------------- #
# Edit behavior — requires DB.
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_note_patch_success_and_clear(principal, migrated: None) -> None:
    token, uid = principal
    await _ensure_user(uid)
    txn_id = (await _quick_add(token, {"amount": "10.00"})).json()["transaction"]["id"]

    resp = await _patch(token, txn_id, {"note": "split with Dana"})
    assert resp.status_code == 200
    assert resp.json()["note"] == "split with Dana"
    assert (await _raw_row(txn_id))["note"] == "split with Dana"

    # null clears the note (nullable field).
    assert (await _patch(token, txn_id, {"note": None})).json()["note"] is None
    assert (await _raw_row(txn_id))["note"] is None


@pytest.mark.asyncio
async def test_amount_patch_updates_minor_exactly(principal, migrated: None) -> None:
    token, uid = principal
    await _ensure_user(uid)
    txn_id = (await _quick_add(token, {"amount": "10.00"})).json()["transaction"]["id"]
    assert (await _raw_row(txn_id))["amount_minor"] == -1000  # expense -> negative

    resp = await _patch(token, txn_id, {"amount": "35.90"})
    assert resp.status_code == 200
    assert resp.json()["amount_minor"] == -3590
    assert (await _raw_row(txn_id))["amount_minor"] == -3590


@pytest.mark.asyncio
async def test_too_many_decimals_rejected_no_change(principal, migrated: None) -> None:
    token, uid = principal
    await _ensure_user(uid)
    txn_id = (await _quick_add(token, {"amount": "10.00"})).json()["transaction"]["id"]
    before = await _raw_row(txn_id)

    resp = await _patch(token, txn_id, {"amount": "33.555"})
    assert resp.status_code == 422
    assert _field_code(resp) == "too_many_decimals"
    assert (await _raw_row(txn_id))["amount_minor"] == before["amount_minor"]  # unchanged


@pytest.mark.asyncio
async def test_zero_amount_rejected_no_change(principal, migrated: None) -> None:
    token, uid = principal
    await _ensure_user(uid)
    txn_id = (await _quick_add(token, {"amount": "10.00"})).json()["transaction"]["id"]
    before = await _raw_row(txn_id)

    resp = await _patch(token, txn_id, {"amount": "0"})
    assert resp.status_code == 422
    assert _field_code(resp) == "zero_amount"
    assert (await _raw_row(txn_id))["amount_minor"] == before["amount_minor"]  # unchanged


@pytest.mark.asyncio
async def test_occurred_on_patch_only_changes_date(principal, migrated: None) -> None:
    token, uid = principal
    await _ensure_user(uid)
    txn_id = (
        await _quick_add(token, {"amount": "10.00", "note": "keep me"})
    ).json()["transaction"]["id"]
    before = await _raw_row(txn_id)

    resp = await _patch(token, txn_id, {"occurred_on": "2026-06-13"})
    assert resp.status_code == 200
    after = await _raw_row(txn_id)
    assert after["occurred_on"] == "2026-06-13"
    assert after["amount_minor"] == before["amount_minor"]  # untouched
    assert after["note"] == before["note"]                  # untouched


@pytest.mark.asyncio
async def test_category_patch_set_and_clear(principal, migrated: None) -> None:
    token, uid = principal
    await _ensure_user(uid)
    txn_id = (await _quick_add(token, {"amount": "10.00"})).json()["transaction"]["id"]
    cat_id = await _category_id("consumer_spending")

    resp = await _patch(token, txn_id, {"category_id": cat_id})
    assert resp.status_code == 200
    assert resp.json()["category_id"] == cat_id
    assert resp.json()["category_key"]  # joined display key present
    assert (await _raw_row(txn_id))["category_id"] == cat_id

    # null clears to uncategorized.
    assert (await _patch(token, txn_id, {"category_id": None})).json()["category_id"] is None
    assert (await _raw_row(txn_id))["category_id"] is None


@pytest.mark.asyncio
async def test_bank_movement_category_rejected(principal, migrated: None) -> None:
    token, uid = principal
    await _ensure_user(uid)
    txn_id = (await _quick_add(token, {"amount": "10.00"})).json()["transaction"]["id"]
    bank_cat = await _category_id("bank_movement")

    resp = await _patch(token, txn_id, {"category_id": bank_cat})
    assert resp.status_code == 422
    assert _field_code(resp) == "not_consumer_category"
    assert (await _raw_row(txn_id))["category_id"] is None  # unchanged


@pytest.mark.asyncio
async def test_unknown_category_rejected(principal, migrated: None) -> None:
    token, uid = principal
    await _ensure_user(uid)
    txn_id = (await _quick_add(token, {"amount": "10.00"})).json()["transaction"]["id"]

    resp = await _patch(token, txn_id, {"category_id": str(uuid.uuid4())})
    assert resp.status_code == 422
    assert _field_code(resp) == "invalid_category"


@pytest.mark.asyncio
async def test_created_at_stable_updated_at_advances(principal, migrated: None) -> None:
    token, uid = principal
    await _ensure_user(uid)
    txn_id = (await _quick_add(token, {"amount": "10.00"})).json()["transaction"]["id"]
    before = await _raw_row(txn_id)

    assert (await _patch(token, txn_id, {"note": "touch"})).status_code == 200
    after = await _raw_row(txn_id)
    assert after["created_at"] == before["created_at"]   # never changes
    assert after["updated_at"] > before["updated_at"]    # advances on success


@pytest.mark.asyncio
async def test_missing_id_returns_404(principal, migrated: None) -> None:
    token, uid = principal
    await _ensure_user(uid)
    _assert_404(await _patch(token, str(uuid.uuid4()), {"note": "x"}))


@pytest.mark.asyncio
async def test_other_users_patch_404_not_403_and_keeps_row(
    principal, migrated: None
) -> None:
    token, uid = principal
    await _ensure_user(uid)
    other_uid = str(uuid.uuid4())
    await _ensure_user(other_uid)
    other_txn = await _insert_txn(other_uid, -4242)

    resp = await _patch(token, other_txn, {"amount": "1.00", "note": "hijack"})
    assert resp.status_code == 404  # NOT 403
    assert resp.json()["error"]["code"] == "not_found"
    row = await _raw_row(other_txn)
    assert row["amount_minor"] == -4242 and row["note"] is None  # untouched


@pytest.mark.asyncio
async def test_forged_user_id_not_trusted(principal, migrated: None) -> None:
    token, uid = principal
    await _ensure_user(uid)
    other_uid = str(uuid.uuid4())
    await _ensure_user(other_uid)
    other_txn = await _insert_txn(other_uid, -777)

    # Forged ?user_id pointing at the owner must not grant access.
    resp = await _patch(token, other_txn, {"note": "nope"}, params={"user_id": other_uid})
    assert resp.status_code == 404
    assert (await _raw_row(other_txn))["note"] is None  # untouched

    # My own row is patchable even with the forged query param present.
    mine = (await _quick_add(token, {"amount": "1.00"})).json()["transaction"]["id"]
    ok = await _patch(token, mine, {"note": "mine"}, params={"user_id": other_uid})
    assert ok.status_code == 200 and ok.json()["note"] == "mine"


@pytest.mark.asyncio
async def test_no_pii_in_logs(principal, migrated: None) -> None:
    token, uid = principal
    await _ensure_user(uid)
    txn_id = (await _quick_add(token, {"amount": "10.00"})).json()["transaction"]["id"]
    secret_note = "patch-secret-note-zz"

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
        resp = await _patch(token, txn_id, {"amount": "35.90", "note": secret_note})
    finally:
        logger.removeHandler(handler)
        logger.setLevel(prev)

    assert resp.status_code == 200
    assert records
    for r in records:
        rendered = r.getMessage() + " " + " ".join(str(v) for v in (r.args or ()))
        assert secret_note not in rendered
        assert "35.90" not in rendered
        assert "3590" not in rendered
