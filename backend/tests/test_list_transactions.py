"""GET /api/v1/transactions — list slice (API_CONTRACT §9).

Covers:
- missing/invalid token -> 401 envelope
- valid token -> 200; empty result is a valid `{items: [], next_cursor: null}`
- returns transactions created via quick-add; amount_minor exact
- newest-first ordering (occurred_on DESC, then created_at DESC)
- month filter includes the matching month and excludes others
- client-supplied user_id is ignored; no cross-user leakage (ownership proof)
- cursor pagination yields the same rows split across pages
- no PII (amount / note / raw input) appears in logs
- response shape matches the contract

Each test gets a FRESH ephemeral principal (random DEV_USER_ID) so the list is
perfectly isolated — which also proves rows are scoped to the resolved user.
401 tests need no DB; the rest require a migrated DB (Neon) and otherwise SKIP.
"""

from __future__ import annotations

import logging
import uuid
from datetime import date

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
    """A fresh ephemeral dev principal: known token + random server user_id."""
    token = "test-list-token-3b"
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


async def _insert_txn(uid: str, amount_minor: int, occurred_on: str) -> str:
    async with get_sessionmaker()() as s:
        row = (
            await s.execute(
                text(
                    "INSERT INTO transactions "
                    "(user_id, amount_minor, currency, transaction_type, source, occurred_on) "
                    "VALUES (:u, :a, 'ILS', 'expense', 'manual', :d) "
                    "RETURNING id::text AS id"
                ),
                {"u": uid, "a": amount_minor, "d": date.fromisoformat(occurred_on)},
            )
        ).mappings().one()
        await s.commit()
        return row["id"]


async def _get(token: str | None, params: dict | None = None):
    app = create_app()
    headers = {}
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.get("/api/v1/transactions", params=params, headers=headers)


async def _quick_add(token: str, payload: dict):
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.post(
            "/api/v1/transactions/quick-add",
            json=payload,
            headers={"Authorization": f"Bearer {token}"},
        )


def _assert_401(resp) -> None:
    assert resp.status_code == 401
    err = resp.json()["error"]
    assert err["code"] == "unauthorized"
    assert err["message"] == "Authentication required."
    assert err["request_id"]
    assert "field_errors" not in err


# --------------------------------------------------------------------------- #
# Auth — no DB required.
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_missing_token_returns_401(principal) -> None:
    _assert_401(await _get(None))


@pytest.mark.asyncio
async def test_invalid_token_returns_401(principal) -> None:
    _assert_401(await _get("wrong-token"))


# --------------------------------------------------------------------------- #
# List behavior — requires DB.
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_empty_result_shape(principal, migrated: None) -> None:
    token, uid = principal
    await _ensure_user(uid)
    resp = await _get(token)
    assert resp.status_code == 200
    body = resp.json()
    assert set(body.keys()) == {"items", "next_cursor"}
    assert body["items"] == []
    assert body["next_cursor"] is None


@pytest.mark.asyncio
async def test_returns_quick_add_txn_with_exact_amount(principal, migrated: None) -> None:
    token, uid = principal
    await _ensure_user(uid)
    created = await _quick_add(token, {"amount": "35.90"})
    assert created.status_code == 201
    txn_id = created.json()["transaction"]["id"]

    body = (await _get(token)).json()
    by_id = {i["id"]: i for i in body["items"]}
    assert txn_id in by_id
    assert by_id[txn_id]["amount_minor"] == -3590  # exact agorot
    assert set(by_id[txn_id].keys()) == TXN_FIELDS


@pytest.mark.asyncio
async def test_response_shape_matches_contract(principal, migrated: None) -> None:
    token, uid = principal
    await _ensure_user(uid)
    await _quick_add(token, {"amount": "10.00"})
    item = (await _get(token)).json()["items"][0]
    assert set(item.keys()) == TXN_FIELDS
    # Amount-only rows: merchant/category joins are null.
    assert item["merchant_id"] is None and item["merchant_display_name"] is None
    assert item["category_id"] is None and item["category_key"] is None
    assert item["source"] == "manual"
    assert item["created_at"].endswith("Z") and item["updated_at"].endswith("Z")


@pytest.mark.asyncio
async def test_newest_first_ordering(principal, migrated: None) -> None:
    token, uid = principal
    await _ensure_user(uid)
    # Distinct dates -> occurred_on DESC ordering.
    id_10 = await _insert_txn(uid, -100, "2020-01-10")
    id_20 = await _insert_txn(uid, -200, "2020-01-20")
    id_15 = await _insert_txn(uid, -150, "2020-01-15")
    items = (await _get(token, {"month": "2020-01"})).json()["items"]
    order = [i["id"] for i in items]
    assert order == [id_20, id_15, id_10]


@pytest.mark.asyncio
async def test_created_at_tiebreaker_ordering(principal, migrated: None) -> None:
    token, uid = principal
    await _ensure_user(uid)
    # Same occurred_on; later-created must sort first (created_at DESC).
    first = (await _quick_add(token, {"amount": "1.00", "occurred_on": "2020-02-02"})).json()["transaction"]["id"]
    second = (await _quick_add(token, {"amount": "2.00", "occurred_on": "2020-02-02"})).json()["transaction"]["id"]
    items = (await _get(token, {"month": "2020-02"})).json()["items"]
    order = [i["id"] for i in items]
    assert order == [second, first]


@pytest.mark.asyncio
async def test_month_filter_includes_and_excludes(principal, migrated: None) -> None:
    token, uid = principal
    await _ensure_user(uid)
    in_id = await _insert_txn(uid, -111, "2020-03-15")
    out_id = await _insert_txn(uid, -222, "2020-04-15")
    ids = {i["id"] for i in (await _get(token, {"month": "2020-03"})).json()["items"]}
    assert in_id in ids       # matching month included
    assert out_id not in ids  # other month excluded


@pytest.mark.asyncio
async def test_client_user_id_ignored_and_no_cross_user_leak(
    principal, migrated: None
) -> None:
    token, uid = principal
    await _ensure_user(uid)
    mine = (await _quick_add(token, {"amount": "8.00"})).json()["transaction"]["id"]

    # A different user with their own transaction.
    other_uid = str(uuid.uuid4())
    await _ensure_user(other_uid)
    other_txn = await _insert_txn(other_uid, -999, "2020-05-05")

    # Pass a forged user_id query param pointing at the other user.
    body = (await _get(token, {"user_id": other_uid})).json()
    returned_ids = {i["id"] for i in body["items"]}
    assert mine in returned_ids            # still my own rows
    assert other_txn not in returned_ids   # never the other user's row


@pytest.mark.asyncio
async def test_cursor_pagination(principal, migrated: None) -> None:
    token, uid = principal
    await _ensure_user(uid)
    a = await _insert_txn(uid, -100, "2020-06-10")
    b = await _insert_txn(uid, -200, "2020-06-20")  # newest

    page1 = (await _get(token, {"month": "2020-06", "limit": 1})).json()
    assert [i["id"] for i in page1["items"]] == [b]
    assert page1["next_cursor"] is not None

    page2 = (await _get(token, {"month": "2020-06", "limit": 1, "cursor": page1["next_cursor"]})).json()
    assert [i["id"] for i in page2["items"]] == [a]
    assert page2["next_cursor"] is None


@pytest.mark.asyncio
async def test_no_pii_in_logs(principal, migrated: None) -> None:
    token, uid = principal
    await _ensure_user(uid)

    records: list[logging.LogRecord] = []

    class _Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    handler = _Capture()
    logger = get_logger()
    prev = logger.level
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    secret_note = "list-secret-note-zzz"
    try:
        await _quick_add(token, {"amount": "35.90", "note": secret_note})
        resp = await _get(token)
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
