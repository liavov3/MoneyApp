"""POST /api/v1/transactions/quick-add — amount-only slice (API_CONTRACT §8/§14).

Covers:
- missing token -> 401 envelope; invalid token -> 401 envelope
- valid amount-only request -> 201 with the contract response shape
- saved row belongs to the server-resolved dev user
- a client-supplied user_id is ignored (server-resolved principal used)
- money parsing: "35.90"->-3590, "35"->-3500, "0.10"->-10, "0.30"->-30
- "33.555" rejected (too_many_decimals), never rounded
- "0" rejected (zero_amount)
- transaction count increases by exactly 1 only for valid saves
- no merchant/category required (amount-only persists)
- no PII (amount / note / raw input) appears in logs

401 tests need no DB. The rest require a reachable, migrated DB (Neon by
default) and otherwise SKIP via the shared `migrated` fixture.
"""

from __future__ import annotations

import logging
from logging.handlers import BufferingHandler
import uuid
import asyncio
from datetime import date, datetime, timedelta, timezone

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

import app.db as _db
from app.config import get_settings
from app.db import get_sessionmaker
from app.logging_utils import get_logger
from app.main import create_app
from app.routers import transactions

TXN_FIELDS = {
    "id", "amount_minor", "currency", "transaction_type", "source",
    "merchant_id", "merchant_display_name", "category_id", "category_key",
    "occurred_on", "note", "is_card_settlement", "created_at", "updated_at",
}


@pytest_asyncio.fixture(autouse=True)
async def _fresh_global_engine():
    """Rebuild the app's global async engine on each test's event loop."""
    _db._engine = None
    _db._sessionmaker = None
    yield
    await _db.dispose_engine()


@pytest.fixture
def dev_token(monkeypatch) -> str:
    token = "test-dev-token-qa-77"
    monkeypatch.setenv("DEV_BEARER_TOKEN", token)
    monkeypatch.setenv("DEV_USER_ID", str(uuid.uuid4()))
    get_settings.cache_clear()
    yield token
    get_settings.cache_clear()


@pytest_asyncio.fixture(autouse=True)
async def _isolated_user(request, dev_token, _fresh_global_engine):
    # These tests previously wrote into the configured development principal.
    # Auth-only tests still run without a database; persistence tests get an
    # ephemeral owner, so warning assertions do not depend on prior test runs.
    if "migrated" not in request.fixturenames:
        yield
        return
    request.getfixturevalue("migrated")
    uid = get_settings().dev_user_id
    async with get_sessionmaker()() as session:
        await session.execute(text("INSERT INTO users (id, base_currency) VALUES (:u, 'ILS')"), {"u": uid})
        await session.commit()
    try:
        yield
    finally:
        async with get_sessionmaker()() as session:
            await session.execute(text("DELETE FROM users WHERE id = :u"), {"u": uid})
            await session.commit()


async def _post(token: str | None, payload: dict):
    app = create_app()
    headers = {}
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.post(
            "/api/v1/transactions/quick-add", json=payload, headers=headers
        )


async def _fetch_txn(txn_id: str):
    async with get_sessionmaker()() as s:
        return (
            await s.execute(
                text(
                    "SELECT user_id::text AS user_id, amount_minor, source, "
                    "merchant_id, category_id, is_card_settlement, dedup_hash "
                    "FROM transactions WHERE id = :id"
                ),
                {"id": txn_id},
            )
        ).mappings().one_or_none()


async def _count_txns(user_id: str) -> int:
    async with get_sessionmaker()() as s:
        return (
            await s.execute(
                text("SELECT count(*) FROM transactions WHERE user_id = :u"),
                {"u": user_id},
            )
        ).scalar_one()


def _assert_401_envelope(resp) -> None:
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
async def test_missing_token_returns_401(dev_token: str) -> None:
    _assert_401_envelope(await _post(None, {"amount": "35.90"}))


@pytest.mark.asyncio
async def test_invalid_token_returns_401(dev_token: str) -> None:
    _assert_401_envelope(await _post("wrong-token", {"amount": "35.90"}))


# --------------------------------------------------------------------------- #
# Amount-only happy path — requires DB.
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_amount_only_returns_201_contract_shape(
    dev_token: str, migrated: None
) -> None:
    resp = await _post(dev_token, {"amount": "35.90"})
    assert resp.status_code == 201
    body = resp.json()
    assert set(body.keys()) == {
        "transaction", "warnings", "category_suggestion", "rule_prompt",
        "alias_suggestion",
    }
    assert body["warnings"] == []
    assert body["category_suggestion"] is None
    assert body["rule_prompt"] == {"offer": False}
    assert body["alias_suggestion"] is None

    txn = body["transaction"]
    assert set(txn.keys()) == TXN_FIELDS
    assert txn["amount_minor"] == -3590
    assert txn["currency"] == "ILS"
    assert txn["transaction_type"] == "expense"
    assert txn["source"] == "manual"
    assert txn["merchant_id"] is None
    assert txn["merchant_display_name"] is None
    assert txn["category_id"] is None
    assert txn["category_key"] is None
    assert txn["note"] is None
    assert txn["is_card_settlement"] is False
    assert txn["occurred_on"]  # defaulted to today
    assert txn["created_at"].endswith("Z")


@pytest.mark.asyncio
async def test_saved_row_belongs_to_dev_user(dev_token: str, migrated: None) -> None:
    resp = await _post(dev_token, {"amount": "12.00"})
    assert resp.status_code == 201
    txn_id = resp.json()["transaction"]["id"]
    row = await _fetch_txn(txn_id)
    assert row is not None
    assert row["user_id"] == get_settings().dev_user_id
    assert row["source"] == "manual"
    assert row["dedup_hash"] is None
    assert row["is_card_settlement"] is False


@pytest.mark.asyncio
async def test_client_supplied_user_id_not_trusted(
    dev_token: str, migrated: None
) -> None:
    bogus = "ffffffff-ffff-ffff-ffff-ffffffffffff"
    resp = await _post(dev_token, {"amount": "5.00", "user_id": bogus})
    assert resp.status_code == 201
    row = await _fetch_txn(resp.json()["transaction"]["id"])
    assert row["user_id"] == get_settings().dev_user_id
    assert row["user_id"] != bogus


@pytest.mark.asyncio
@pytest.mark.parametrize(
    "amount,expected_minor",
    [("35.90", -3590), ("35", -3500), ("0.10", -10), ("0.30", -30)],
)
async def test_money_parsing_exact(
    dev_token: str, migrated: None, amount: str, expected_minor: int
) -> None:
    resp = await _post(dev_token, {"amount": amount})
    assert resp.status_code == 201
    txn_id = resp.json()["transaction"]["id"]
    assert resp.json()["transaction"]["amount_minor"] == expected_minor
    row = await _fetch_txn(txn_id)
    assert row["amount_minor"] == expected_minor  # exact in the DB too


@pytest.mark.asyncio
async def test_too_many_decimals_rejected_not_rounded(
    dev_token: str, migrated: None
) -> None:
    before = await _count_txns(get_settings().dev_user_id)
    resp = await _post(dev_token, {"amount": "33.555"})
    assert resp.status_code == 422
    err = resp.json()["error"]
    assert err["code"] == "validation_error"
    assert any(
        fe["field"] == "amount" and fe["code"] == "too_many_decimals"
        for fe in err["field_errors"]
    )
    # Never rounded -> no new row at all.
    after = await _count_txns(get_settings().dev_user_id)
    assert after == before


@pytest.mark.asyncio
async def test_zero_amount_rejected(dev_token: str, migrated: None) -> None:
    before = await _count_txns(get_settings().dev_user_id)
    resp = await _post(dev_token, {"amount": "0"})
    assert resp.status_code == 422
    err = resp.json()["error"]
    assert err["code"] == "validation_error"
    assert any(
        fe["field"] == "amount" and fe["code"] == "zero_amount"
        for fe in err["field_errors"]
    )
    assert await _count_txns(get_settings().dev_user_id) == before


@pytest.mark.asyncio
async def test_count_increases_by_one_only_for_valid(
    dev_token: str, migrated: None
) -> None:
    uid = get_settings().dev_user_id
    before = await _count_txns(uid)
    assert (await _post(dev_token, {"amount": "7.77"})).status_code == 201
    assert await _count_txns(uid) == before + 1
    # An invalid save does not change the count.
    assert (await _post(dev_token, {"amount": "33.555"})).status_code == 422
    assert await _count_txns(uid) == before + 1


@pytest.mark.asyncio
async def test_no_merchant_or_category_required(dev_token: str, migrated: None) -> None:
    resp = await _post(dev_token, {"amount": "9.50"})
    assert resp.status_code == 201
    txn = resp.json()["transaction"]
    assert txn["merchant_id"] is None and txn["category_id"] is None


@pytest.mark.asyncio
async def test_no_pii_in_logs(dev_token: str, migrated: None) -> None:
    """Amount, note, and raw input must never appear in logs (privacy §15)."""
    records: list[logging.LogRecord] = []

    class _Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    handler = _Capture()
    logger = get_logger()
    prev = logger.level
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    secret_note = "secret-note-do-not-log-xyz"
    try:
        resp = await _post(dev_token, {"amount": "35.90", "note": secret_note})
    finally:
        logger.removeHandler(handler)
        logger.setLevel(prev)

    assert resp.status_code == 201
    assert records
    for r in records:
        rendered = r.getMessage() + " " + " ".join(str(v) for v in (r.args or ()))
        assert secret_note not in rendered
        assert "35.90" not in rendered  # raw amount string
        assert "3590" not in rendered   # amount magnitude


@pytest.mark.asyncio
async def test_duplicate_is_saved_and_warns_with_only_the_prior_owned_id(dev_token, migrated):
    first = (await _post(dev_token, {"amount": "33.50"})).json()["transaction"]
    second = await _post(dev_token, {"amount": "33.50"})
    assert second.status_code == 201
    body = second.json()
    assert body["transaction"]["id"] != first["id"]
    assert body["transaction"]["amount_minor"] == -3350
    assert body["warnings"] == [{
        "code": "duplicate_looking", "message": "A similar entry was just added.",
        "similar_transaction_id": first["id"],
    }]
    assert await _count_txns(get_settings().dev_user_id) == 2


@pytest.mark.asyncio
async def test_duplicate_uses_resolved_merchant_identity(dev_token, migrated):
    first = (await _post(dev_token, {"amount": "8.25", "merchant_input": "Same Store"})).json()["transaction"]
    second = (await _post(dev_token, {"amount": "8.25", "merchant_input": " SAME STORE "})).json()
    assert second["transaction"]["merchant_id"] == first["merchant_id"]
    assert second["warnings"][0]["similar_transaction_id"] == first["id"]


@pytest.mark.asyncio
@pytest.mark.parametrize("difference", [
    {"amount": "33.51"}, {"currency": "USD"}, {"merchant_input": "Different Store"},
    {"occurred_on": (date.today() - timedelta(days=1)).isoformat()},
    {"transaction_type": "refund"},
])
async def test_distinct_transaction_is_not_a_duplicate(dev_token, migrated, difference):
    await _post(dev_token, {"amount": "33.50", "transaction_type": "income"})
    result = await _post(dev_token, {"amount": "33.50", "transaction_type": "income", **difference})
    assert result.status_code == 201
    assert result.json()["warnings"] == []


@pytest.mark.asyncio
@pytest.mark.parametrize("boundary,expected", [("start", True), ("before_start", False), ("end", False)])
async def test_duplicate_window_is_the_saved_rows_utc_creation_day(dev_token, migrated, boundary, expected):
    first = (await _post(dev_token, {"amount": "17.13"})).json()["transaction"]
    start = datetime.now(timezone.utc).replace(hour=0, minute=0, second=0, microsecond=0)
    created = start if boundary == "start" else start - timedelta(microseconds=1) if boundary == "before_start" else start + timedelta(days=1)
    async with get_sessionmaker()() as session:
        await session.execute(text("UPDATE transactions SET created_at=:created WHERE id=CAST(:id AS uuid)"), {"created": created, "id": first["id"]})
        await session.commit()
    result = (await _post(dev_token, {"amount": "17.13"})).json()
    assert bool(result["warnings"]) is expected


@pytest.mark.asyncio
async def test_foreign_recent_transaction_is_not_disclosed(dev_token, migrated):
    foreign = str(uuid.uuid4())
    async with get_sessionmaker()() as session:
        await session.execute(text("INSERT INTO users (id,base_currency) VALUES (:u,'ILS')"), {"u": foreign})
        await session.execute(text("INSERT INTO transactions (user_id,amount_minor,currency,transaction_type,source,occurred_on) VALUES (:u,-1731,'ILS','expense','manual',:d)"), {"u": foreign, "d": date.today()})
        await session.commit()
    try:
        result = await _post(dev_token, {"amount": "17.31", "user_id": foreign})
        assert result.status_code == 201
        assert result.json()["warnings"] == []
    finally:
        async with get_sessionmaker()() as session:
            await session.execute(text("DELETE FROM users WHERE id=:u"), {"u": foreign})
            await session.commit()


@pytest.mark.asyncio
@pytest.mark.parametrize("amount,ttype,confirmed,expected", [
    ("9999.99", "expense", False, None),
    ("10000", "expense", False, -1000000),
    ("12000", "income", False, 1200000),
    ("12000", "expense", True, None),
])
async def test_large_amount_warning_uses_exact_minor_units_and_confirmation(dev_token, migrated, amount, ttype, confirmed, expected):
    result = await _post(dev_token, {"amount": amount, "transaction_type": ttype, "confirm_large_amount": confirmed})
    assert result.status_code == 201
    warnings = result.json()["warnings"]
    assert [w["amount_minor"] for w in warnings if w["code"] == "large_amount"] == ([] if expected is None else [expected])
    assert await _fetch_txn(result.json()["transaction"]["id"]) is not None


@pytest.mark.asyncio
async def test_large_amount_confirmation_does_not_suppress_duplicate_warning(dev_token, migrated):
    first = (await _post(dev_token, {"amount": "10000"})).json()["transaction"]
    result = (await _post(dev_token, {"amount": "10000", "confirm_large_amount": True})).json()
    assert [w["code"] for w in result["warnings"]] == ["duplicate_looking"]
    assert result["warnings"][0]["similar_transaction_id"] == first["id"]


@pytest.mark.asyncio
async def test_warning_lookup_failure_cannot_undo_or_hide_a_committed_save(dev_token, migrated, monkeypatch):
    visible_at_lookup = []
    async def broken_lookup(params, transaction_id, created_at):
        visible_at_lookup.append(await _fetch_txn(transaction_id) is not None)
        raise RuntimeError("sensitive-enrichment-failure")
    monkeypatch.setattr(transactions, "_find_duplicate", broken_lookup)
    handler = BufferingHandler(100)
    logger = get_logger()
    previous_level = logger.level
    logger.addHandler(handler)
    # ASGITransport does not run lifespan, so configure INFO capture explicitly.
    logger.setLevel(logging.INFO)
    try:
        result = await _post(dev_token, {"amount": "10000"})
    finally:
        logger.removeHandler(handler)
        logger.setLevel(previous_level)
    assert result.status_code == 201
    assert visible_at_lookup == [True]  # seen through a separate connection, before enrichment
    assert [w["code"] for w in result.json()["warnings"]] == ["large_amount"]
    assert await _count_txns(get_settings().dev_user_id) == 1
    messages = " ".join(record.getMessage() for record in handler.buffer)
    assert "quick_add_warning_skipped" in messages
    assert "sensitive-enrichment-failure" not in messages


@pytest.mark.asyncio
async def test_warning_lookup_timeout_retains_a_successful_save(dev_token, migrated, monkeypatch):
    cancelled = False
    async def stalled_lookup(*args):
        nonlocal cancelled
        try:
            await asyncio.sleep(30)
        finally:
            cancelled = True
    monkeypatch.setattr(transactions, "_find_duplicate", stalled_lookup)
    monkeypatch.setattr(transactions, "_WARNING_TIMEOUT_SECONDS", 0.01)
    result = await _post(dev_token, {"amount": "9.17"})
    assert result.status_code == 201
    assert cancelled
    assert await _count_txns(get_settings().dev_user_id) == 1
