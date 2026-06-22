"""DELETE /api/v1/transactions/{id} — hard delete slice (API_CONTRACT §9).

Covers:
- missing/invalid token -> 401 envelope
- valid token + owned transaction -> 204 No Content (no body)
- deleted transaction no longer appears in GET /transactions or GET /{id}
- re-delete same id -> 404; missing id -> 404; malformed UUID -> 404
- a transaction owned by ANOTHER user -> 404 (not 403); other users unaffected
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


@pytest_asyncio.fixture(autouse=True)
async def _fresh_global_engine():
    _db._engine = None
    _db._sessionmaker = None
    yield
    await _db.dispose_engine()


@pytest.fixture
def principal(monkeypatch) -> tuple[str, str]:
    token = "test-del-token-7d"
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


async def _txn_exists(txn_id: str) -> bool:
    async with get_sessionmaker()() as s:
        return (
            await s.execute(
                text("SELECT count(*) FROM transactions WHERE id = CAST(:id AS uuid)"),
                {"id": txn_id},
            )
        ).scalar_one() == 1


def _client(app):
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def _delete(token: str | None, txn_id: str, params: dict | None = None):
    app = create_app()
    headers = {}
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    async with _client(app) as c:
        return await c.delete(
            f"/api/v1/transactions/{txn_id}", params=params, headers=headers
        )


async def _quick_add(token: str, payload: dict):
    app = create_app()
    async with _client(app) as c:
        return await c.post(
            "/api/v1/transactions/quick-add", json=payload,
            headers={"Authorization": f"Bearer {token}"},
        )


async def _get_one(token: str, txn_id: str):
    app = create_app()
    async with _client(app) as c:
        return await c.get(
            f"/api/v1/transactions/{txn_id}",
            headers={"Authorization": f"Bearer {token}"},
        )


async def _list_ids(token: str) -> set[str]:
    app = create_app()
    async with _client(app) as c:
        r = await c.get(
            "/api/v1/transactions", headers={"Authorization": f"Bearer {token}"}
        )
    return {i["id"] for i in r.json()["items"]}


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
    _assert_401(await _delete(None, str(uuid.uuid4())))


@pytest.mark.asyncio
async def test_invalid_token_returns_401(principal) -> None:
    _assert_401(await _delete("wrong-token", str(uuid.uuid4())))


# --------------------------------------------------------------------------- #
# Delete behavior — requires DB.
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_owned_delete_returns_204_no_body(principal, migrated: None) -> None:
    token, uid = principal
    await _ensure_user(uid)
    txn_id = (await _quick_add(token, {"amount": "35.90"})).json()["transaction"]["id"]

    resp = await _delete(token, txn_id)
    assert resp.status_code == 204
    assert resp.content == b""  # no body
    assert not await _txn_exists(txn_id)  # actually gone from the DB


@pytest.mark.asyncio
async def test_deleted_gone_from_list_and_get(principal, migrated: None) -> None:
    token, uid = principal
    await _ensure_user(uid)
    txn_id = (await _quick_add(token, {"amount": "10.00"})).json()["transaction"]["id"]
    assert txn_id in await _list_ids(token)

    assert (await _delete(token, txn_id)).status_code == 204

    assert txn_id not in await _list_ids(token)        # gone from list
    _assert_404(await _get_one(token, txn_id))          # gone from single read


@pytest.mark.asyncio
async def test_redelete_returns_404(principal, migrated: None) -> None:
    token, uid = principal
    await _ensure_user(uid)
    txn_id = (await _quick_add(token, {"amount": "5.00"})).json()["transaction"]["id"]
    assert (await _delete(token, txn_id)).status_code == 204
    _assert_404(await _delete(token, txn_id))  # idempotent re-delete -> 404


@pytest.mark.asyncio
async def test_missing_id_returns_404(principal, migrated: None) -> None:
    token, uid = principal
    await _ensure_user(uid)
    _assert_404(await _delete(token, str(uuid.uuid4())))


@pytest.mark.asyncio
async def test_malformed_id_returns_404(principal, migrated: None) -> None:
    token, uid = principal
    await _ensure_user(uid)
    _assert_404(await _delete(token, "not-a-uuid"))


@pytest.mark.asyncio
async def test_other_users_delete_returns_404_not_403_and_keeps_row(
    principal, migrated: None
) -> None:
    token, uid = principal
    await _ensure_user(uid)

    other_uid = str(uuid.uuid4())
    await _ensure_user(other_uid)
    other_txn = await _insert_txn(other_uid, -4242)

    resp = await _delete(token, other_txn)
    assert resp.status_code == 404  # NOT 403
    assert resp.json()["error"]["code"] == "not_found"
    # The other user's row must remain untouched.
    assert await _txn_exists(other_txn)


@pytest.mark.asyncio
async def test_forged_user_id_not_trusted(principal, migrated: None) -> None:
    """A forged ?user_id pointing at the owner must not grant delete access."""
    token, uid = principal
    await _ensure_user(uid)
    other_uid = str(uuid.uuid4())
    await _ensure_user(other_uid)
    other_txn = await _insert_txn(other_uid, -777)

    resp = await _delete(token, other_txn, params={"user_id": other_uid})
    assert resp.status_code == 404
    assert await _txn_exists(other_txn)  # still there

    # My own row is deletable (sanity).
    mine = (await _quick_add(token, {"amount": "1.00"})).json()["transaction"]["id"]
    assert (await _delete(token, mine, params={"user_id": other_uid})).status_code == 204


@pytest.mark.asyncio
async def test_no_pii_in_logs(principal, migrated: None) -> None:
    token, uid = principal
    await _ensure_user(uid)
    secret_note = "del-secret-note-ww"
    txn_id = (
        await _quick_add(token, {"amount": "35.90", "note": secret_note})
    ).json()["transaction"]["id"]

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
        resp = await _delete(token, txn_id)
    finally:
        logger.removeHandler(handler)
        logger.setLevel(prev)

    assert resp.status_code == 204
    assert records
    for r in records:
        rendered = r.getMessage() + " " + " ".join(str(v) for v in (r.args or ()))
        assert secret_note not in rendered
        assert "35.90" not in rendered
        assert "3590" not in rendered
