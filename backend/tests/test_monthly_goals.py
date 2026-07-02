"""/api/v1/monthly-goals — goal types + default/override scopes (additive).

GET returns the EFFECTIVE state for all three goal types for a month (override
wins over default). PUT upserts one goal. DELETE removes one (idempotent). Each
test uses a FRESH ephemeral principal (random DEV_USER_ID), which also proves
per-user isolation. 401 tests need no DB; the rest require a migrated DB.
"""

from __future__ import annotations

import uuid

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text

import app.db as _db
from app.config import get_settings
from app.db import get_sessionmaker
from app.main import create_app


@pytest_asyncio.fixture(autouse=True)
async def _fresh_global_engine():
    _db._engine = None
    _db._sessionmaker = None
    yield
    await _db.dispose_engine()


@pytest.fixture
def principal(monkeypatch) -> tuple[str, str]:
    token = "test-goals-token-5c"
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


async def _count_defaults(uid: str, goal_type: str) -> int:
    async with get_sessionmaker()() as s:
        return (
            await s.execute(
                text(
                    "SELECT COUNT(*) FROM monthly_goals "
                    "WHERE user_id = :u AND goal_type = :gt AND scope = 'default'"
                ),
                {"u": uid, "gt": goal_type},
            )
        ).scalar_one()


def _client():
    app = create_app()
    transport = ASGITransport(app=app)
    return AsyncClient(transport=transport, base_url="http://test")


async def _put(token: str | None, body: dict | None):
    headers = {"Authorization": f"Bearer {token}"} if token is not None else {}
    async with _client() as client:
        return await client.put("/api/v1/monthly-goals", json=body, headers=headers)


async def _get(token: str | None, params: dict | None = None):
    headers = {"Authorization": f"Bearer {token}"} if token is not None else {}
    async with _client() as client:
        return await client.get("/api/v1/monthly-goals", params=params, headers=headers)


async def _delete(token: str | None, params: dict | None = None):
    headers = {"Authorization": f"Bearer {token}"} if token is not None else {}
    async with _client() as client:
        return await client.delete(
            "/api/v1/monthly-goals", params=params, headers=headers
        )


def _state(get_body: dict, goal_type: str) -> dict:
    return next(i for i in get_body["items"] if i["goal_type"] == goal_type)


# --------------------------------------------------------------------------- #
# Auth — no DB required.
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_get_missing_token_returns_401(principal) -> None:
    resp = await _get(None, {"month": "2026-07"})
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "unauthorized"


@pytest.mark.asyncio
async def test_put_invalid_token_returns_401(principal) -> None:
    resp = await _put(
        "wrong-token",
        {"goal_type": "expense", "scope": "default", "amount_minor": 100000},
    )
    assert resp.status_code == 401


# --------------------------------------------------------------------------- #
# 1. PUT default expense -> GET shows default effective.
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_put_default_effective_is_default(principal, migrated: None) -> None:
    token, uid = principal
    await _ensure_user(uid)
    resp = await _put(
        token, {"goal_type": "expense", "scope": "default", "amount_minor": 350000}
    )
    assert resp.status_code == 200
    saved = resp.json()
    assert saved == {
        "goal_type": "expense",
        "scope": "default",
        "month": None,
        "amount_minor": 350000,
        "currency": "ILS",
    }

    body = (await _get(token, {"month": "2026-07"})).json()
    assert body["month"] == "2026-07"
    assert body["currency"] == "ILS"
    assert len(body["items"]) == 3
    assert [i["goal_type"] for i in body["items"]] == ["expense", "income", "savings"]
    exp = _state(body, "expense")
    assert exp == {
        "goal_type": "expense",
        "default_amount_minor": 350000,
        "override_amount_minor": None,
        "effective_amount_minor": 350000,
        "effective_source": "default",
    }


# --------------------------------------------------------------------------- #
# 2. Override for month M wins; other month falls back to default.
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_override_wins_other_month_default(principal, migrated: None) -> None:
    token, uid = principal
    await _ensure_user(uid)
    await _put(
        token, {"goal_type": "expense", "scope": "default", "amount_minor": 300000}
    )
    await _put(
        token,
        {
            "goal_type": "expense",
            "scope": "month_override",
            "month": "2026-07",
            "amount_minor": 500000,
        },
    )

    m = _state((await _get(token, {"month": "2026-07"})).json(), "expense")
    assert m["default_amount_minor"] == 300000
    assert m["override_amount_minor"] == 500000
    assert m["effective_amount_minor"] == 500000
    assert m["effective_source"] == "month_override"

    other = _state((await _get(token, {"month": "2026-08"})).json(), "expense")
    assert other["override_amount_minor"] is None
    assert other["effective_amount_minor"] == 300000
    assert other["effective_source"] == "default"


# --------------------------------------------------------------------------- #
# 3. Three goal types set + read independently.
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_three_types_independent(principal, migrated: None) -> None:
    token, uid = principal
    await _ensure_user(uid)
    await _put(token, {"goal_type": "expense", "scope": "default", "amount_minor": 100000})
    await _put(token, {"goal_type": "income", "scope": "default", "amount_minor": 200000})
    await _put(token, {"goal_type": "savings", "scope": "default", "amount_minor": 300000})

    body = (await _get(token, {"month": "2026-07"})).json()
    assert _state(body, "expense")["effective_amount_minor"] == 100000
    assert _state(body, "income")["effective_amount_minor"] == 200000
    assert _state(body, "savings")["effective_amount_minor"] == 300000


# --------------------------------------------------------------------------- #
# 4. DELETE override -> falls back to default.
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_delete_override_falls_back(principal, migrated: None) -> None:
    token, uid = principal
    await _ensure_user(uid)
    await _put(token, {"goal_type": "expense", "scope": "default", "amount_minor": 300000})
    await _put(
        token,
        {
            "goal_type": "expense",
            "scope": "month_override",
            "month": "2026-07",
            "amount_minor": 500000,
        },
    )
    resp = await _delete(
        token, {"goal_type": "expense", "scope": "month_override", "month": "2026-07"}
    )
    assert resp.status_code == 204

    m = _state((await _get(token, {"month": "2026-07"})).json(), "expense")
    assert m["override_amount_minor"] is None
    assert m["effective_amount_minor"] == 300000
    assert m["effective_source"] == "default"


# --------------------------------------------------------------------------- #
# 5. DELETE default -> all-null for that type.
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_delete_default_all_null(principal, migrated: None) -> None:
    token, uid = principal
    await _ensure_user(uid)
    await _put(token, {"goal_type": "expense", "scope": "default", "amount_minor": 300000})
    resp = await _delete(token, {"goal_type": "expense", "scope": "default"})
    assert resp.status_code == 204

    m = _state((await _get(token, {"month": "2026-07"})).json(), "expense")
    assert m == {
        "goal_type": "expense",
        "default_amount_minor": None,
        "override_amount_minor": None,
        "effective_amount_minor": None,
        "effective_source": None,
    }


# --------------------------------------------------------------------------- #
# 6. Update-in-place: PUT default twice -> one row, new value.
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_put_default_updates_in_place(principal, migrated: None) -> None:
    token, uid = principal
    await _ensure_user(uid)
    await _put(token, {"goal_type": "expense", "scope": "default", "amount_minor": 100000})
    await _put(token, {"goal_type": "expense", "scope": "default", "amount_minor": 250000})

    m = _state((await _get(token, {"month": "2026-07"})).json(), "expense")
    assert m["default_amount_minor"] == 250000
    assert await _count_defaults(uid, "expense") == 1  # no duplicate row


# --------------------------------------------------------------------------- #
# 7. User isolation.
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_user_isolation(principal, migrated: None, monkeypatch) -> None:
    token, uid = principal
    await _ensure_user(uid)
    await _put(token, {"goal_type": "expense", "scope": "default", "amount_minor": 999999})

    other_token = "test-goals-token-other"
    other_uid = str(uuid.uuid4())
    monkeypatch.setenv("DEV_BEARER_TOKEN", other_token)
    monkeypatch.setenv("DEV_USER_ID", other_uid)
    get_settings.cache_clear()
    await _ensure_user(other_uid)

    body = (await _get(other_token, {"month": "2026-07"})).json()
    for item in body["items"]:
        assert item["effective_amount_minor"] is None


# --------------------------------------------------------------------------- #
# 8. Validation — 422s.
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_put_invalid_goal_type(principal, migrated: None) -> None:
    token, uid = principal
    await _ensure_user(uid)
    resp = await _put(
        token, {"goal_type": "rent", "scope": "default", "amount_minor": 100000}
    )
    assert resp.status_code == 422
    err = resp.json()["error"]
    assert err["code"] == "validation_error"
    assert any(fe["field"] == "goal_type" for fe in err["field_errors"])


@pytest.mark.asyncio
async def test_put_invalid_scope(principal, migrated: None) -> None:
    token, uid = principal
    await _ensure_user(uid)
    resp = await _put(
        token, {"goal_type": "expense", "scope": "yearly", "amount_minor": 100000}
    )
    assert resp.status_code == 422
    assert any(
        fe["field"] == "scope" for fe in resp.json()["error"]["field_errors"]
    )


@pytest.mark.asyncio
async def test_put_override_without_month(principal, migrated: None) -> None:
    token, uid = principal
    await _ensure_user(uid)
    resp = await _put(
        token,
        {"goal_type": "expense", "scope": "month_override", "amount_minor": 100000},
    )
    assert resp.status_code == 422
    assert any(
        fe["field"] == "month" for fe in resp.json()["error"]["field_errors"]
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("amount", [0, -100, None])
async def test_put_invalid_amount(principal, migrated: None, amount) -> None:
    token, uid = principal
    await _ensure_user(uid)
    body = {"goal_type": "expense", "scope": "default"}
    if amount is not None:
        body["amount_minor"] = amount
    resp = await _put(token, body)
    assert resp.status_code == 422
    assert any(
        fe["field"] == "amount_minor" for fe in resp.json()["error"]["field_errors"]
    )


@pytest.mark.asyncio
@pytest.mark.parametrize("bad_month", ["2026-13", "bad"])
async def test_put_invalid_month_format(principal, migrated: None, bad_month) -> None:
    token, uid = principal
    await _ensure_user(uid)
    resp = await _put(
        token,
        {
            "goal_type": "expense",
            "scope": "month_override",
            "month": bad_month,
            "amount_minor": 100000,
        },
    )
    assert resp.status_code == 422
    assert any(
        fe["field"] == "month" for fe in resp.json()["error"]["field_errors"]
    )


# --------------------------------------------------------------------------- #
# 9. DELETE is idempotent.
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_delete_nonexistent_override_idempotent(principal, migrated: None) -> None:
    token, uid = principal
    await _ensure_user(uid)
    resp = await _delete(
        token, {"goal_type": "expense", "scope": "month_override", "month": "2026-07"}
    )
    assert resp.status_code == 204


# --------------------------------------------------------------------------- #
# 10. DELETE validation + auth.
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_delete_invalid_goal_type(principal, migrated: None) -> None:
    token, uid = principal
    await _ensure_user(uid)
    resp = await _delete(token, {"goal_type": "rent", "scope": "default"})
    assert resp.status_code == 422


@pytest.mark.asyncio
async def test_delete_missing_token_returns_401(principal) -> None:
    resp = await _delete(
        None, {"goal_type": "expense", "scope": "default"}
    )
    assert resp.status_code == 401
