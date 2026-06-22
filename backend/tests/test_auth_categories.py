"""Auth + GET /api/v1/categories (API_CONTRACT §3, §5, §6).

Covers:
- unauthorized (missing token) -> 401 standard envelope (QA-09-10 / QA-11-05)
- invalid bearer token -> 401 standard envelope
- valid bearer token -> 200
- exactly 22 categories returned (QA-13-01 / §6)
- canonical keys present incl. interest_bank_fee, cash_deposit_withdrawal
- forbidden aliases bank_fee_interest / cash_movement NOT returned as keys
- consumer_spending count == 14 (frozen §6)
- response shape matches the contract field-for-field
- client cannot name user_id (server-resolved only — QA-09-11)
- the dev token is never logged (QA-10-06 / privacy)

The 401 tests run without a database (auth fails before any DB access). The 200
tests require a reachable, migrated DB (Neon by default) and otherwise SKIP via
the shared `migrated` fixture.
"""

from __future__ import annotations

import logging

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient

import app.db as _db
from app.config import get_settings
from app.logging_utils import get_logger
from app.main import create_app


@pytest_asyncio.fixture(autouse=True)
async def _fresh_global_engine():
    """Rebuild the app's global async engine on each test's event loop.

    The app caches one engine/sessionmaker process-wide (standard for FastAPI),
    but pytest-asyncio runs every test on a fresh loop; an asyncpg engine is
    bound to the loop that created it. Null the cache before the test so the
    endpoint builds the engine on the current loop, and dispose it after on that
    same loop (avoids cross-loop dispose).
    """
    _db._engine = None
    _db._sessionmaker = None
    yield
    await _db.dispose_engine()

CONTRACT_FIELDS = {
    "id",
    "key",
    "label_en",
    "label_he",
    "layer",
    "included_in_actual_spending",
    "included_in_cash_flow",
    "is_system",
}

CANONICAL_KEYS = {
    "groceries", "eating_out", "transport", "car_fuel", "shopping", "entertainment",
    "subscriptions", "health", "education", "home", "gifts", "travel", "personal_care",
    "other_spending",
    "income", "incoming_transfer", "outgoing_transfer", "credit_card_settlement",
    "loan_payment", "interest_bank_fee", "cash_deposit_withdrawal", "other_bank_movement",
}


@pytest.fixture
def dev_token(monkeypatch) -> str:
    """Configure a known server-side dev token for the test (env override).

    Clears the settings cache so `require_principal` reads this token, and again
    on teardown so later tests/fixtures see clean settings.
    """
    token = "test-dev-token-9c1f2a"
    monkeypatch.setenv("DEV_BEARER_TOKEN", token)
    get_settings.cache_clear()
    yield token
    get_settings.cache_clear()


async def _get_categories(
    token: str | None = None, params: dict | None = None
):
    app = create_app()
    headers = {}
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.get("/api/v1/categories", headers=headers, params=params)


def _assert_401_envelope(resp) -> None:
    assert resp.status_code == 401
    body = resp.json()
    assert set(body.keys()) == {"error"}
    err = body["error"]
    assert err["code"] == "unauthorized"
    assert err["message"] == "Authentication required."
    assert isinstance(err["request_id"], str) and err["request_id"]
    # Generic envelope: no field_errors for unauthorized.
    assert "field_errors" not in err


# --------------------------------------------------------------------------- #
# 401 paths — no database required.
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_missing_token_returns_401_envelope(dev_token: str) -> None:
    resp = await _get_categories(token=None)
    _assert_401_envelope(resp)


@pytest.mark.asyncio
async def test_invalid_token_returns_401_envelope(dev_token: str) -> None:
    resp = await _get_categories(token="not-the-right-token")
    _assert_401_envelope(resp)


@pytest.mark.asyncio
async def test_malformed_authorization_header_returns_401(dev_token: str) -> None:
    # Right value but missing the Bearer scheme -> unresolved principal.
    app = create_app()
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        resp = await client.get(
            "/api/v1/categories", headers={"Authorization": dev_token}
        )
    _assert_401_envelope(resp)


# --------------------------------------------------------------------------- #
# 200 paths — require a reachable, migrated DB (skips otherwise via `migrated`).
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_valid_token_returns_200(dev_token: str, migrated: None) -> None:
    resp = await _get_categories(token=dev_token)
    assert resp.status_code == 200
    assert "items" in resp.json()


@pytest.mark.asyncio
async def test_returns_exactly_22_categories(dev_token: str, migrated: None) -> None:
    resp = await _get_categories(token=dev_token)
    items = resp.json()["items"]
    assert len(items) == 22


@pytest.mark.asyncio
async def test_canonical_keys_present(dev_token: str, migrated: None) -> None:
    keys = {c["key"] for c in (await _get_categories(token=dev_token)).json()["items"]}
    assert keys == CANONICAL_KEYS
    assert "interest_bank_fee" in keys
    assert "cash_deposit_withdrawal" in keys


@pytest.mark.asyncio
async def test_forbidden_aliases_not_returned(dev_token: str, migrated: None) -> None:
    keys = {c["key"] for c in (await _get_categories(token=dev_token)).json()["items"]}
    assert "bank_fee_interest" not in keys
    assert "cash_movement" not in keys


@pytest.mark.asyncio
async def test_consumer_spending_count_matches_contract(
    dev_token: str, migrated: None
) -> None:
    items = (await _get_categories(token=dev_token)).json()["items"]
    consumer = [c for c in items if c["layer"] == "consumer_spending"]
    bank = [c for c in items if c["layer"] == "bank_movement"]
    assert len(consumer) == 14
    assert len(bank) == 8
    # Layer flags exactly per §6.
    assert all(
        c["included_in_actual_spending"] and not c["included_in_cash_flow"]
        for c in consumer
    )
    assert all(
        not c["included_in_actual_spending"] and c["included_in_cash_flow"]
        for c in bank
    )


@pytest.mark.asyncio
async def test_response_shape_matches_contract(dev_token: str, migrated: None) -> None:
    items = (await _get_categories(token=dev_token)).json()["items"]
    for c in items:
        # Exactly the contract fields — no committed_projection, no user_id leak.
        assert set(c.keys()) == CONTRACT_FIELDS
        assert "included_in_committed_projection" not in c
        assert "user_id" not in c
        assert c["is_system"] is True
        assert c["layer"] in ("consumer_spending", "bank_movement")


@pytest.mark.asyncio
async def test_client_cannot_name_user_id(dev_token: str, migrated: None) -> None:
    """QA-09-11: a client-supplied user_id is ignored; server-resolved principal used."""
    resp = await _get_categories(
        token=dev_token, params={"user_id": "ffffffff-ffff-ffff-ffff-ffffffffffff"}
    )
    assert resp.status_code == 200
    # System categories are shared and identical for any principal (QA-13-10).
    assert len(resp.json()["items"]) == 22


@pytest.mark.asyncio
async def test_dev_token_never_logged(dev_token: str, migrated: None) -> None:
    """Privacy: the bearer token must never appear in logs (QA-10-06)."""

    records: list[logging.LogRecord] = []

    class _Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    handler = _Capture()
    logger = get_logger()
    prev_level = logger.level
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)  # ensure INFO access logs reach the handler
    try:
        resp = await _get_categories(token=dev_token)
    finally:
        logger.removeHandler(handler)
        logger.setLevel(prev_level)

    assert resp.status_code == 200
    assert records, "expected at least one safe log record"
    for r in records:
        rendered = r.getMessage() + " " + " ".join(str(v) for v in (r.args or ()))
        assert dev_token not in rendered
        assert "Authorization" not in rendered
