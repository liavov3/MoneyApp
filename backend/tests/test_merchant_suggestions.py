"""GET /api/v1/merchants/suggestions?query= — typed autocomplete slice.

Read-only, principal-scoped. Implements the deterministic, alias-free subset of
the MERCHANT_NORMALIZATION_SPEC §7 confidence ladder: exact / normalized_exact
(auto-select), recent_suggestion (prefix), contains (whole-token, confirm), else
none. Cross-script + fuzzy never match (no transliteration, no fuzzy). Covers:

- missing/invalid token -> 401; empty query -> 422 validation_error
- exact typed merchant -> confidence=exact, auto_select set
- normalized_exact (case/space variant) -> auto_select set
- prefix -> recent_suggestion (no confirmation, no auto-select)
- contains (multi-token) -> requires_confirmation, never auto-select
- typo "Goldaa" -> none (no fuzzy merge)
- cross-script "גולדה" vs "Golda" -> none (no silent cross-script merge)
- only the principal's merchants are searched; forged user_id ignored
- limit default 8 / max 20
- raw query and display_name never appear in logs

401/empty-query need no DB; the rest require a migrated DB.
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
    token = "test-sugg-token-8w"
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


def _client(app):
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def _quick_add(token: str, payload: dict):
    app = create_app()
    async with _client(app) as c:
        return await c.post(
            "/api/v1/transactions/quick-add", json=payload,
            headers={"Authorization": f"Bearer {token}"},
        )


async def _suggest(token: str | None, params: dict | None = None):
    app = create_app()
    headers = {}
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    async with _client(app) as c:
        return await c.get("/api/v1/merchants/suggestions", params=params, headers=headers)


def _assert_401(resp) -> None:
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "unauthorized"


# --------------------------------------------------------------------------- #
# Auth + validation — no DB.
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_missing_token_returns_401(principal) -> None:
    _assert_401(await _suggest(None, {"query": "Golda"}))


@pytest.mark.asyncio
async def test_invalid_token_returns_401(principal) -> None:
    _assert_401(await _suggest("wrong-token", {"query": "Golda"}))


@pytest.mark.asyncio
async def test_missing_query_param_returns_422(principal) -> None:
    token, _ = principal
    assert (await _suggest(token)).status_code == 422  # required param missing


@pytest.mark.asyncio
async def test_blank_query_returns_422(principal, migrated: None) -> None:
    token, uid = principal
    await _ensure_user(uid)
    resp = await _suggest(token, {"query": "   "})
    assert resp.status_code == 422
    err = resp.json()["error"]
    assert err["code"] == "validation_error"
    assert err["field_errors"][0]["code"] == "empty_query"


# --------------------------------------------------------------------------- #
# Confidence ladder — requires DB.
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_exact_match_auto_selects(principal, migrated: None) -> None:
    token, uid = principal
    await _ensure_user(uid)
    mid = (await _quick_add(token, {"amount": "5.00", "merchant_input": "Golda"})).json()[
        "transaction"
    ]["merchant_id"]

    body = (await _suggest(token, {"query": "Golda"})).json()
    assert body["query_confidence"] == "exact"
    assert body["auto_select_merchant_id"] == mid
    item = body["items"][0]
    assert item["confidence"] == "exact"
    assert item["requires_confirmation"] is False
    assert item["matched_via"] == "merchant"
    assert item["suggested_category_source"] == "none"  # no default set yet


@pytest.mark.asyncio
async def test_normalized_exact_auto_selects(principal, migrated: None) -> None:
    token, uid = principal
    await _ensure_user(uid)
    mid = (await _quick_add(token, {"amount": "5.00", "merchant_input": "Golda"})).json()[
        "transaction"
    ]["merchant_id"]

    body = (await _suggest(token, {"query": "  golda "})).json()  # case/space variant
    assert body["query_confidence"] == "normalized_exact"
    assert body["auto_select_merchant_id"] == mid


@pytest.mark.asyncio
async def test_prefix_is_recent_suggestion(principal, migrated: None) -> None:
    token, uid = principal
    await _ensure_user(uid)
    await _quick_add(token, {"amount": "5.00", "merchant_input": "Golda"})

    body = (await _suggest(token, {"query": "gol"})).json()
    assert body["query_confidence"] == "recent_suggestion"
    assert body["auto_select_merchant_id"] is None  # suggestion, not auto-select
    assert body["items"][0]["confidence"] == "recent_suggestion"
    assert body["items"][0]["requires_confirmation"] is False


@pytest.mark.asyncio
async def test_contains_requires_confirmation_no_auto_select(principal, migrated: None) -> None:
    token, uid = principal
    await _ensure_user(uid)
    await _quick_add(token, {"amount": "5.00", "merchant_input": "Wolt"})

    body = (await _suggest(token, {"query": "Wolt Tel Aviv"})).json()
    assert body["query_confidence"] == "contains"
    assert body["auto_select_merchant_id"] is None  # never auto-merge a contains
    assert body["items"][0]["confidence"] == "contains"
    assert body["items"][0]["requires_confirmation"] is True


@pytest.mark.asyncio
async def test_typo_behaves_as_none(principal, migrated: None) -> None:
    token, uid = principal
    await _ensure_user(uid)
    await _quick_add(token, {"amount": "5.00", "merchant_input": "Golda"})

    body = (await _suggest(token, {"query": "Goldaa"})).json()  # one-char typo
    assert body == {"query_confidence": "none", "auto_select_merchant_id": None, "items": []}


@pytest.mark.asyncio
async def test_cross_script_does_not_match(principal, migrated: None) -> None:
    token, uid = principal
    await _ensure_user(uid)
    await _quick_add(token, {"amount": "5.00", "merchant_input": "Golda"})

    body = (await _suggest(token, {"query": "גולדה"})).json()  # Hebrew vs English merchant
    # No transliteration in v0.0.1 -> no silent cross-script candidate.
    assert body["query_confidence"] == "none"
    assert body["auto_select_merchant_id"] is None
    assert body["items"] == []


@pytest.mark.asyncio
async def test_only_own_merchants_and_forged_user_id_ignored(principal, migrated: None) -> None:
    token, uid = principal
    await _ensure_user(uid)
    other = str(uuid.uuid4())
    await _ensure_user(other)
    await _seed_merchant(other, "golda", "Golda")  # another user's Golda
    await _quick_add(token, {"amount": "5.00", "merchant_input": "Mine"})

    # Querying "Golda" must NOT surface the other user's merchant.
    assert (await _suggest(token, {"query": "Golda"})).json() == {
        "query_confidence": "none", "auto_select_merchant_id": None, "items": []
    }
    # A forged ?user_id pointing at the other user is ignored.
    forged = await _suggest(token, {"query": "Golda", "user_id": other})
    assert forged.json()["items"] == []


@pytest.mark.asyncio
async def test_limit_clamped(principal, migrated: None) -> None:
    token, uid = principal
    await _ensure_user(uid)
    # 22 merchants all sharing the "shop" prefix -> all recent_suggestion matches.
    for n in range(22):
        await _quick_add(token, {"amount": "5.00", "merchant_input": f"shop{n:02d}"})

    assert len((await _suggest(token, {"query": "shop"})).json()["items"]) == 8       # default
    assert len((await _suggest(token, {"query": "shop", "limit": 3})).json()["items"]) == 3
    assert len((await _suggest(token, {"query": "shop", "limit": 999})).json()["items"]) == 20


@pytest.mark.asyncio
async def test_no_pii_in_logs(principal, migrated: None) -> None:
    token, uid = principal
    await _ensure_user(uid)
    secret = "SuggSecretShopWW"
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
        resp = await _suggest(token, {"query": secret})
    finally:
        logger.removeHandler(handler)
        logger.setLevel(prev)

    assert resp.status_code == 200
    assert resp.json()["query_confidence"] == "exact"  # it did match
    assert records
    for r in records:
        rendered = r.getMessage() + " " + " ".join(str(v) for v in (r.args or ()))
        assert secret not in rendered              # raw query / display name
        assert secret.casefold() not in rendered   # normalized key
