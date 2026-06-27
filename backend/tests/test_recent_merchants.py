"""GET /api/v1/merchants/recent — recent merchant chips slice.

Read-only, principal-scoped. Covers:
- missing/invalid token -> 401 envelope
- empty history -> { "items": [] }
- merchants created by quick-add appear, most-recently-used first
- re-using a merchant (quick-add again) bumps it back to the front
- only the server-resolved user's merchants are returned; forged user_id ignored
- limit default 8 / max 20 behavior
- suggested_category_* null when no merchant default (no rules/aliases needed)
- no PII (display_name / normalized key) appears in logs

401 cases need no DB; the rest require a migrated DB.
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
    token = "test-recent-token-2t"
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


async def _seed_merchant(uid: str, normalized: str, display: str) -> str:
    """Insert a merchant directly (e.g. for a different user) and return its id."""
    async with get_sessionmaker()() as s:
        row = (
            await s.execute(
                text(
                    "INSERT INTO merchants (user_id, normalized_merchant_name, display_name) "
                    "VALUES (:u, :n, :d) RETURNING id::text AS id"
                ),
                {"u": uid, "n": normalized, "d": display},
            )
        ).mappings().one()
        await s.commit()
        return row["id"]


def _client(app):
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def _quick_add(token: str, payload: dict):
    app = create_app()
    async with _client(app) as c:
        return await c.post(
            "/api/v1/transactions/quick-add", json=payload,
            headers={"Authorization": f"Bearer {token}"},
        )


async def _recent(token: str | None, params: dict | None = None):
    app = create_app()
    headers = {}
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    async with _client(app) as c:
        return await c.get("/api/v1/merchants/recent", params=params, headers=headers)


def _assert_401(resp) -> None:
    assert resp.status_code == 401
    err = resp.json()["error"]
    assert err["code"] == "unauthorized"
    assert err["message"] == "Authentication required."
    assert err["request_id"]


# --------------------------------------------------------------------------- #
# Auth — no DB.
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_missing_token_returns_401(principal) -> None:
    _assert_401(await _recent(None))


@pytest.mark.asyncio
async def test_invalid_token_returns_401(principal) -> None:
    _assert_401(await _recent("wrong-token"))


# --------------------------------------------------------------------------- #
# Behavior — requires DB.
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_empty_history_returns_empty_items(principal, migrated: None) -> None:
    token, uid = principal
    await _ensure_user(uid)
    resp = await _recent(token)
    assert resp.status_code == 200
    assert resp.json() == {"items": []}


@pytest.mark.asyncio
async def test_quick_add_merchants_appear_recent_first(principal, migrated: None) -> None:
    token, uid = principal
    await _ensure_user(uid)
    await _quick_add(token, {"amount": "5.00", "merchant_input": "Golda"})
    await _quick_add(token, {"amount": "6.00", "merchant_input": "Wolt"})

    items = (await _recent(token)).json()["items"]
    names = [i["display_name"] for i in items]
    assert names == ["Wolt", "Golda"]  # most-recently-used first
    # Contract fields present; no merchant default set yet -> null suggestion.
    top = items[0]
    assert set(top) == {
        "merchant_id", "display_name", "suggested_category_id",
        "suggested_category_key", "suggested_category_source", "last_used_at",
    }
    assert top["suggested_category_id"] is None
    assert top["suggested_category_source"] is None
    assert top["last_used_at"].endswith("Z")


@pytest.mark.asyncio
async def test_reuse_bumps_to_front(principal, migrated: None) -> None:
    token, uid = principal
    await _ensure_user(uid)
    await _quick_add(token, {"amount": "5.00", "merchant_input": "Golda"})
    await _quick_add(token, {"amount": "6.00", "merchant_input": "Wolt"})
    await _quick_add(token, {"amount": "7.00", "merchant_input": "golda"})  # reuse Golda

    names = [i["display_name"] for i in (await _recent(token)).json()["items"]]
    assert names == ["Golda", "Wolt"]  # reuse moved Golda back to front


@pytest.mark.asyncio
async def test_only_own_merchants_returned(principal, migrated: None) -> None:
    token, uid = principal
    await _ensure_user(uid)
    other = str(uuid.uuid4())
    await _ensure_user(other)
    await _seed_merchant(other, "othermerchant", "OtherMerchant")  # not mine
    await _quick_add(token, {"amount": "5.00", "merchant_input": "Mine"})

    items = (await _recent(token)).json()["items"]
    names = [i["display_name"] for i in items]
    assert names == ["Mine"]  # the other user's merchant is excluded
    assert "OtherMerchant" not in names


@pytest.mark.asyncio
async def test_forged_user_id_ignored(principal, migrated: None) -> None:
    token, uid = principal
    await _ensure_user(uid)
    other = str(uuid.uuid4())
    await _ensure_user(other)
    await _seed_merchant(other, "othermerchant", "OtherMerchant")
    await _quick_add(token, {"amount": "5.00", "merchant_input": "Mine"})

    # A forged ?user_id pointing at the other user must not leak their merchants.
    items = (await _recent(token, params={"user_id": other})).json()["items"]
    assert [i["display_name"] for i in items] == ["Mine"]


@pytest.mark.asyncio
async def test_limit_clamped_to_max_20(principal, migrated: None) -> None:
    token, uid = principal
    await _ensure_user(uid)
    for n in range(22):
        await _quick_add(token, {"amount": "5.00", "merchant_input": f"M{n:02d}"})

    assert len(((await _recent(token)).json())["items"]) == 8        # default
    assert len(((await _recent(token, {"limit": 3})).json())["items"]) == 3
    assert len(((await _recent(token, {"limit": 999})).json())["items"]) == 20  # max
    assert len(((await _recent(token, {"limit": 0})).json())["items"]) == 1     # floor


@pytest.mark.asyncio
async def test_no_pii_in_logs(principal, migrated: None) -> None:
    token, uid = principal
    await _ensure_user(uid)
    secret = "RecentSecretShopZZ"
    await _quick_add(token, {"amount": "5.00", "merchant_input": secret})

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
        resp = await _recent(token)
    finally:
        logger.removeHandler(handler)
        logger.setLevel(prev)

    assert resp.status_code == 200
    assert any(i["display_name"] == secret for i in resp.json()["items"])
    assert records
    for r in records:
        rendered = r.getMessage() + " " + " ".join(str(v) for v in (r.args or ()))
        assert secret not in rendered                 # display name
        assert secret.casefold() not in rendered      # normalized key
