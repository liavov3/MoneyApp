"""GET /api/v1/transactions/{id} — single read slice (API_CONTRACT §9).

Covers:
- missing/invalid token -> 401 envelope
- valid token + owned transaction -> 200 with the contract transaction shape
- amount_minor is exact
- not-found id -> 404 envelope
- a transaction owned by ANOTHER user -> 404 (not 403), identical to missing
- a forged client user_id is ignored / never trusted
- no PII (amount / note / raw input) appears in logs

Each test uses a fresh ephemeral principal (random DEV_USER_ID) for isolation.
401 / malformed-id tests need no DB; the rest require a migrated DB (Neon).
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

TXN_FIELDS = {
    "id", "amount_minor", "currency", "transaction_type", "source",
    "merchant_id", "merchant_display_name", "category_id", "category_key",
    "occurred_on", "note", "is_card_settlement", "created_at", "updated_at",
}


@pytest_asyncio.fixture(autouse=True)
async def _fresh_global_engine():
    _db._engine = None
    _db._sessionmaker = None
    yield
    await _db.dispose_engine()


@pytest.fixture
def principal(monkeypatch) -> tuple[str, str]:
    token = "test-get-token-5c"
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


async def _get(token: str | None, txn_id: str, params: dict | None = None):
    app = create_app()
    headers = {}
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.get(
            f"/api/v1/transactions/{txn_id}", params=params, headers=headers
        )


async def _quick_add(token: str, payload: dict):
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.post(
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


# --------------------------------------------------------------------------- #
# Auth — no DB required.
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_missing_token_returns_401(principal) -> None:
    _assert_401(await _get(None, str(uuid.uuid4())))


@pytest.mark.asyncio
async def test_invalid_token_returns_401(principal) -> None:
    _assert_401(await _get("wrong-token", str(uuid.uuid4())))


# --------------------------------------------------------------------------- #
# Single read — requires DB.
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_owned_transaction_returns_200_contract_shape(
    principal, migrated: None
) -> None:
    token, uid = principal
    await _ensure_user(uid)
    created = await _quick_add(token, {"amount": "35.90"})
    txn_id = created.json()["transaction"]["id"]

    resp = await _get(token, txn_id)
    assert resp.status_code == 200
    body = resp.json()
    # Bare transaction object (no wrapper), exact contract field set.
    assert set(body.keys()) == TXN_FIELDS
    assert body["id"] == txn_id
    assert body["amount_minor"] == -3590  # exact
    assert body["currency"] == "ILS"
    assert body["source"] == "manual"
    assert body["merchant_id"] is None and body["merchant_display_name"] is None
    assert body["category_id"] is None and body["category_key"] is None
    assert "raw_merchant_input" not in body  # sensitive; never returned
    assert body["created_at"].endswith("Z") and body["updated_at"].endswith("Z")


@pytest.mark.asyncio
async def test_not_found_id_returns_404(principal, migrated: None) -> None:
    token, uid = principal
    await _ensure_user(uid)
    _assert_404(await _get(token, str(uuid.uuid4())))


@pytest.mark.asyncio
async def test_malformed_id_returns_404(principal, migrated: None) -> None:
    token, uid = principal
    await _ensure_user(uid)
    _assert_404(await _get(token, "not-a-uuid"))


@pytest.mark.asyncio
async def test_other_users_transaction_returns_404_not_403(
    principal, migrated: None
) -> None:
    token, uid = principal
    await _ensure_user(uid)

    # A real transaction owned by a DIFFERENT user.
    other_uid = str(uuid.uuid4())
    await _ensure_user(other_uid)
    other_txn = await _insert_txn(other_uid, -4242)

    resp = await _get(token, other_txn)
    assert resp.status_code == 404  # NOT 403
    assert resp.json()["error"]["code"] == "not_found"
    # Identical to a missing id (no existence leak).
    missing = await _get(token, str(uuid.uuid4()))
    assert resp.json()["error"]["code"] == missing.json()["error"]["code"]
    assert resp.json()["error"]["message"] == missing.json()["error"]["message"]


@pytest.mark.asyncio
async def test_forged_user_id_not_trusted(principal, migrated: None) -> None:
    """A forged ?user_id pointing at the owner must not grant access."""
    token, uid = principal
    await _ensure_user(uid)
    other_uid = str(uuid.uuid4())
    await _ensure_user(other_uid)
    other_txn = await _insert_txn(other_uid, -777)

    # Even naming the true owner via a query param yields 404 (param ignored).
    resp = await _get(token, other_txn, params={"user_id": other_uid})
    assert resp.status_code == 404

    # And my own transaction is still reachable (sanity).
    mine = (await _quick_add(token, {"amount": "1.00"})).json()["transaction"]["id"]
    assert (await _get(token, mine, params={"user_id": other_uid})).status_code == 200


@pytest.mark.asyncio
async def test_no_pii_in_logs(principal, migrated: None) -> None:
    token, uid = principal
    await _ensure_user(uid)
    secret_note = "get-secret-note-qq"
    created = await _quick_add(token, {"amount": "35.90", "note": secret_note})
    txn_id = created.json()["transaction"]["id"]

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
        resp = await _get(token, txn_id)
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
