"""GET /merchants/suggestions — alias_exact resolution (wires §11 aliases into §7).

After a user_confirmed alias is created (POST /merchants/{id}/aliases), typing
that variant resolves at `alias_exact` and auto-selects the merchant — the
cross-script "type גולדה -> Golda" loop. Covers:

- confirmed alias -> alias_exact, matched_via=alias, auto_select set, no confirm
- the canonical name still resolves stronger as `exact` (matched_via=merchant)
- aliases are principal-scoped (another user's alias never matches my query)
- only `user_confirmed` aliases auto-select (system_suggested does NOT)
- alias text / normalized key never appear in logs

All require a migrated DB.
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
from app.merchants import normalize_merchant_name


@pytest_asyncio.fixture(autouse=True)
async def _fresh_global_engine():
    _db._engine = None
    _db._sessionmaker = None
    yield
    await _db.dispose_engine()


@pytest.fixture
def principal(monkeypatch) -> tuple[str, str]:
    token = "test-aliasx-token-4r"
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


async def _seed_alias(uid: str, merchant_id: str, alias_text: str, source: str) -> None:
    async with get_sessionmaker()() as s:
        await s.execute(
            text(
                "INSERT INTO merchant_aliases "
                "(user_id, merchant_id, alias_text, normalized_alias_key, source) "
                "VALUES (:u, CAST(:m AS uuid), :t, :nk, :src)"
            ),
            {"u": uid, "m": merchant_id, "t": alias_text,
             "nk": normalize_merchant_name(alias_text), "src": source},
        )
        await s.commit()


def _client(app):
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def _quick_add(token: str, payload: dict):
    app = create_app()
    async with _client(app) as c:
        return await c.post(
            "/api/v1/transactions/quick-add", json=payload,
            headers={"Authorization": f"Bearer {token}"},
        )


async def _post_alias(token: str, merchant_id: str, body: dict):
    app = create_app()
    async with _client(app) as c:
        return await c.post(
            f"/api/v1/merchants/{merchant_id}/aliases", json=body,
            headers={"Authorization": f"Bearer {token}"},
        )


async def _suggest(token: str, params: dict):
    app = create_app()
    async with _client(app) as c:
        return await c.get(
            "/api/v1/merchants/suggestions", params=params,
            headers={"Authorization": f"Bearer {token}"},
        )


async def _new_merchant(token: str, name: str) -> str:
    return (await _quick_add(token, {"amount": "5.00", "merchant_input": name})).json()[
        "transaction"
    ]["merchant_id"]


# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_confirmed_alias_auto_selects_cross_script(principal, migrated: None) -> None:
    token, uid = principal
    await _ensure_user(uid)
    golda = await _new_merchant(token, "Golda")
    assert (await _post_alias(token, golda, {"alias_text": "גולדה"})).status_code == 201

    body = (await _suggest(token, {"query": "גולדה"})).json()  # Hebrew variant
    assert body["query_confidence"] == "alias_exact"
    assert body["auto_select_merchant_id"] == golda
    item = next(i for i in body["items"] if i["merchant_id"] == golda)
    assert item["confidence"] == "alias_exact"
    assert item["matched_via"] == "alias"
    assert item["requires_confirmation"] is False


@pytest.mark.asyncio
async def test_canonical_name_still_exact(principal, migrated: None) -> None:
    token, uid = principal
    await _ensure_user(uid)
    golda = await _new_merchant(token, "Golda")
    await _post_alias(token, golda, {"alias_text": "גולדה"})

    body = (await _suggest(token, {"query": "Golda"})).json()  # canonical name
    assert body["query_confidence"] == "exact"
    item = body["items"][0]
    assert item["confidence"] == "exact"
    assert item["matched_via"] == "merchant"  # not via the alias


@pytest.mark.asyncio
async def test_alias_is_principal_scoped(principal, migrated: None) -> None:
    token, uid = principal
    await _ensure_user(uid)
    other = str(uuid.uuid4())
    await _ensure_user(other)
    other_m = await _seed_merchant(other, "golda", "Golda")
    await _seed_alias(other, other_m, "גולדה", "user_confirmed")  # the OTHER user's alias

    # I have no merchant/alias -> the other user's alias must not resolve for me.
    body = (await _suggest(token, {"query": "גולדה"})).json()
    assert body == {"query_confidence": "none", "auto_select_merchant_id": None, "items": []}


@pytest.mark.asyncio
async def test_system_suggested_alias_does_not_auto_select(principal, migrated: None) -> None:
    token, uid = principal
    await _ensure_user(uid)
    golda = await _new_merchant(token, "Golda")
    await _seed_alias(uid, golda, "גולדה", "system_suggested")  # low-trust, not confirmed

    body = (await _suggest(token, {"query": "גולדה"})).json()
    # Only user_confirmed aliases auto-select (spec §6) -> no match here.
    assert body["query_confidence"] == "none"
    assert body["items"] == []


@pytest.mark.asyncio
async def test_no_pii_in_logs(principal, migrated: None) -> None:
    token, uid = principal
    await _ensure_user(uid)
    golda = await _new_merchant(token, "Golda")
    secret = "AliasXSecretVarPP"
    await _post_alias(token, golda, {"alias_text": secret})

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
        resp = await _suggest(token, {"query": secret})
    finally:
        logger.removeHandler(handler)
        logger.setLevel(prev)

    assert resp.status_code == 200
    assert resp.json()["query_confidence"] == "alias_exact"  # it matched
    assert records
    for r in records:
        rendered = r.getMessage() + " " + " ".join(str(v) for v in (r.args or ()))
        assert secret not in rendered
        assert secret.casefold() not in rendered
