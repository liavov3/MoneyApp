"""Wire category_rules into merchant/category suggestions (§9 precedence).

Consumes the rules created by POST /transactions/{id}/categorize and surfaces
the suggested category in GET /merchants/suggestions, GET /merchants/recent, and
POST /transactions/quick-add (suggest-only). Covers:

- suggestions/recent surface a promoted user_correction rule's category
- no rule -> unchanged behavior (no invented suggestion)
- precedence: rule beats merchant_default; inactive rule ignored; newest wins
- merchant_contains rule applies to a longer merchant name
- user isolation: A's rule never reaches B (same normalized name)
- quick-add SUGGESTS only — the saved row is not auto-categorized
- match_value (merchant text) never appears in logs

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


@pytest_asyncio.fixture(autouse=True)
async def _fresh_global_engine():
    _db._engine = None
    _db._sessionmaker = None
    yield
    await _db.dispose_engine()


@pytest.fixture
def principal(monkeypatch) -> tuple[str, str]:
    token = "test-rulesug-token-3z"
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


async def _category(key: str) -> str:
    async with get_sessionmaker()() as s:
        return (
            await s.execute(
                text(
                    "SELECT id::text FROM categories "
                    "WHERE key = :k AND user_id IS NULL LIMIT 1"
                ),
                {"k": key},
            )
        ).scalar_one()


async def _seed_merchant(uid: str, normalized: str, display: str) -> str:
    async with get_sessionmaker()() as s:
        r = (
            await s.execute(
                text(
                    "INSERT INTO merchants (user_id, normalized_merchant_name, display_name) "
                    "VALUES (:u, :n, :d) RETURNING id::text AS id"
                ),
                {"u": uid, "n": normalized, "d": display},
            )
        ).mappings().one()
        await s.commit()
        return r["id"]


async def _seed_rule(uid: str, match_value: str, category_id: str, *,
                     match_type: str = "merchant_exact",
                     source: str = "user_correction", is_active: bool = True) -> None:
    async with get_sessionmaker()() as s:
        await s.execute(
            text(
                "INSERT INTO category_rules "
                "(user_id, match_type, match_value, category_id, source, is_active) "
                "VALUES (:u, :mt, :mv, CAST(:c AS uuid), :src, :act)"
            ),
            {"u": uid, "mt": match_type, "mv": match_value, "c": category_id,
             "src": source, "act": is_active},
        )
        await s.commit()


async def _deactivate_rules(uid: str) -> None:
    async with get_sessionmaker()() as s:
        await s.execute(
            text("UPDATE category_rules SET is_active = false WHERE user_id = :u"), {"u": uid}
        )
        await s.commit()


async def _set_default(merchant_id: str, category_id: str) -> None:
    async with get_sessionmaker()() as s:
        await s.execute(
            text(
                "UPDATE merchants SET default_category_id = CAST(:c AS uuid) "
                "WHERE id = CAST(:m AS uuid)"
            ),
            {"c": category_id, "m": merchant_id},
        )
        await s.commit()


async def _bank_category() -> str:
    async with get_sessionmaker()() as s:
        return (
            await s.execute(
                text(
                    "SELECT id::text FROM categories "
                    "WHERE layer = 'bank_movement' AND user_id IS NULL LIMIT 1"
                )
            )
        ).scalar_one()


async def _seed_categorized_txn(uid: str, merchant_id: str, category_id: str) -> None:
    async with get_sessionmaker()() as s:
        await s.execute(
            text(
                "INSERT INTO transactions "
                "(user_id, amount_minor, currency, transaction_type, source, "
                " merchant_id, category_id) "
                "VALUES (:u, -500, 'ILS', 'expense', 'manual', "
                " CAST(:m AS uuid), CAST(:c AS uuid))"
            ),
            {"u": uid, "m": merchant_id, "c": category_id},
        )
        await s.commit()


async def _txn_category(txn_id: str) -> str | None:
    async with get_sessionmaker()() as s:
        return (
            await s.execute(
                text("SELECT category_id::text FROM transactions WHERE id = CAST(:i AS uuid)"),
                {"i": txn_id},
            )
        ).scalar_one()


def _client(app):
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def _quick_add(token: str, payload: dict):
    app = create_app()
    async with _client(app) as c:
        return await c.post(
            "/api/v1/transactions/quick-add", json=payload,
            headers={"Authorization": f"Bearer {token}"},
        )


async def _categorize(token: str, txn_id: str, body: dict):
    app = create_app()
    async with _client(app) as c:
        return await c.post(
            f"/api/v1/transactions/{txn_id}/categorize", json=body,
            headers={"Authorization": f"Bearer {token}"},
        )


async def _suggest(token: str, query: str):
    app = create_app()
    async with _client(app) as c:
        return await c.get(
            "/api/v1/merchants/suggestions", params={"query": query},
            headers={"Authorization": f"Bearer {token}"},
        )


async def _recent(token: str):
    app = create_app()
    async with _client(app) as c:
        return await c.get(
            "/api/v1/merchants/recent", headers={"Authorization": f"Bearer {token}"}
        )


async def _add_wolt(token: str) -> tuple[str, str]:
    t = (await _quick_add(token, {"amount": "10.00", "merchant_input": "Wolt"})).json()[
        "transaction"
    ]
    return t["id"], t["merchant_id"]


async def _promote_wolt(token: str, category_id: str, match_type: str = "merchant_exact") -> str:
    txn_id, merchant_id = await _add_wolt(token)
    await _categorize(
        token, txn_id,
        {"category_id": category_id, "promote_to_rule": True, "match_type": match_type},
    )
    return merchant_id


def _item_for(body: dict, merchant_id: str) -> dict:
    return next(i for i in body["items"] if i["merchant_id"] == merchant_id)


# --------------------------------------------------------------------------- #
# Suggestions surface the rule.
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_suggestions_use_promoted_rule(principal, migrated: None) -> None:
    token, uid = principal
    await _ensure_user(uid)
    eating = await _category("eating_out")
    merchant = await _promote_wolt(token, eating)

    item = _item_for((await _suggest(token, "Wolt")).json(), merchant)
    assert item["suggested_category_id"] == eating
    assert item["suggested_category_key"] == "eating_out"
    assert item["suggested_category_source"] == "user_correction_merchant_exact"


@pytest.mark.asyncio
async def test_no_rule_keeps_none(principal, migrated: None) -> None:
    token, uid = principal
    await _ensure_user(uid)
    (await _quick_add(token, {"amount": "5.00", "merchant_input": "Golda"})).json()
    item = (await _suggest(token, "Golda")).json()["items"][0]
    assert item["suggested_category_id"] is None
    assert item["suggested_category_source"] == "none"


@pytest.mark.asyncio
async def test_recent_uses_rule(principal, migrated: None) -> None:
    token, uid = principal
    await _ensure_user(uid)
    eating = await _category("eating_out")
    merchant = await _promote_wolt(token, eating)

    item = _item_for((await _recent(token)).json(), merchant)
    assert item["suggested_category_id"] == eating
    assert item["suggested_category_source"] == "user_correction_merchant_exact"


# --------------------------------------------------------------------------- #
# Precedence.
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_rule_beats_merchant_default(principal, migrated: None) -> None:
    token, uid = principal
    await _ensure_user(uid)
    eating = await _category("eating_out")
    shopping = await _category("shopping")
    merchant = await _promote_wolt(token, eating)        # rule -> eating_out
    await _set_default(merchant, shopping)               # default -> shopping

    item = _item_for((await _suggest(token, "Wolt")).json(), merchant)
    assert item["suggested_category_id"] == eating  # rule wins over default
    assert item["suggested_category_source"] == "user_correction_merchant_exact"


@pytest.mark.asyncio
async def test_inactive_rule_ignored(principal, migrated: None) -> None:
    token, uid = principal
    await _ensure_user(uid)
    eating = await _category("eating_out")
    # An UNcategorized Wolt txn + an inactive rule -> no rule, no memory.
    _, merchant = await _add_wolt(token)
    await _seed_rule(uid, "wolt", eating, is_active=False)

    item = _item_for((await _suggest(token, "Wolt")).json(), merchant)
    assert item["suggested_category_id"] is None
    assert item["suggested_category_source"] == "none"


@pytest.mark.asyncio
async def test_updated_rule_returns_newest(principal, migrated: None) -> None:
    token, uid = principal
    await _ensure_user(uid)
    eating = await _category("eating_out")
    shopping = await _category("shopping")
    txn_id, merchant = await _add_wolt(token)
    await _categorize(token, txn_id, {"category_id": eating, "promote_to_rule": True})
    await _categorize(token, txn_id, {"category_id": shopping, "promote_to_rule": True})

    item = _item_for((await _suggest(token, "Wolt")).json(), merchant)
    assert item["suggested_category_id"] == shopping  # newest correction


@pytest.mark.asyncio
async def test_merchant_contains_rule_applies(principal, migrated: None) -> None:
    token, uid = principal
    await _ensure_user(uid)
    eating = await _category("eating_out")
    await _promote_wolt(token, eating, match_type="merchant_contains")  # rule value "wolt"
    # A longer merchant name contains the fragment.
    branch = (await _quick_add(token, {"amount": "7.00", "merchant_input": "Wolt Tel Aviv"})).json()[
        "transaction"
    ]["merchant_id"]

    item = _item_for((await _suggest(token, "Wolt Tel Aviv")).json(), branch)
    assert item["suggested_category_id"] == eating
    assert item["suggested_category_source"] == "user_correction_merchant_contains"


# --------------------------------------------------------------------------- #
# User isolation.
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_other_users_rule_does_not_leak(principal, migrated: None) -> None:
    token, uid = principal  # this is user B
    await _ensure_user(uid)
    eating = await _category("eating_out")
    # User A has a Wolt merchant + an active rule; B must not see it.
    other = str(uuid.uuid4())
    await _ensure_user(other)
    await _seed_merchant(other, "wolt", "Wolt")
    await _seed_rule(other, "wolt", eating)

    b_merchant = (await _quick_add(token, {"amount": "5.00", "merchant_input": "Wolt"})).json()[
        "transaction"
    ]["merchant_id"]
    item = _item_for((await _suggest(token, "Wolt")).json(), b_merchant)
    assert item["suggested_category_id"] is None  # A's rule never reaches B
    assert item["suggested_category_source"] == "none"


# --------------------------------------------------------------------------- #
# Quick Add — suggest only, never auto-apply.
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_quick_add_suggests_but_does_not_apply(principal, migrated: None) -> None:
    token, uid = principal
    await _ensure_user(uid)
    eating = await _category("eating_out")
    await _promote_wolt(token, eating)

    resp = (await _quick_add(token, {"amount": "12.00", "merchant_input": "Wolt"})).json()
    sugg = resp["category_suggestion"]
    assert sugg is not None
    assert sugg["category_id"] == eating
    assert sugg["category_key"] == "eating_out"
    assert sugg["source"] == "user_correction_merchant_exact"
    # SUGGEST-ONLY: the saved transaction stays uncategorized.
    assert resp["transaction"]["category_id"] is None
    assert await _txn_category(resp["transaction"]["id"]) is None


@pytest.mark.asyncio
async def test_quick_add_no_rule_no_suggestion(principal, migrated: None) -> None:
    token, uid = principal
    await _ensure_user(uid)
    resp = (await _quick_add(token, {"amount": "5.00", "merchant_input": "Golda"})).json()
    assert resp["category_suggestion"] is None


@pytest.mark.asyncio
async def test_quick_add_explicit_category_no_suggestion(principal, migrated: None) -> None:
    token, uid = principal
    await _ensure_user(uid)
    eating = await _category("eating_out")
    shopping = await _category("shopping")
    await _promote_wolt(token, eating)

    # Client explicitly chooses a category -> no suggestion returned, that wins.
    resp = (
        await _quick_add(token, {"amount": "9.00", "merchant_input": "Wolt", "category_id": shopping})
    ).json()
    assert resp["category_suggestion"] is None
    assert resp["transaction"]["category_id"] == shopping


@pytest.mark.asyncio
async def test_no_match_value_in_logs(principal, migrated: None) -> None:
    token, uid = principal
    await _ensure_user(uid)
    eating = await _category("eating_out")
    secret = "RuleSugSecretZZ"
    txn_id = (await _quick_add(token, {"amount": "5.00", "merchant_input": secret})).json()[
        "transaction"
    ]["id"]
    await _categorize(token, txn_id, {"category_id": eating, "promote_to_rule": True})

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
        resp = await _suggest(token, secret)
    finally:
        logger.removeHandler(handler)
        logger.setLevel(prev)

    assert resp.status_code == 200
    assert records
    for r in records:
        rendered = r.getMessage() + " " + " ".join(str(v) for v in (r.args or ()))
        assert secret not in rendered             # merchant text / match_value
        assert secret.casefold() not in rendered  # normalized key


# --------------------------------------------------------------------------- #
# Recent-merchant memory (§9 level 5).
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_recent_memory_used_when_no_rule(principal, migrated: None) -> None:
    token, uid = principal
    await _ensure_user(uid)
    eating = await _category("eating_out")
    txn_id, merchant = await _add_wolt(token)
    await _categorize(token, txn_id, {"category_id": eating})  # categorize only, NO rule

    item = _item_for((await _suggest(token, "Wolt")).json(), merchant)
    assert item["suggested_category_id"] == eating
    assert item["suggested_category_source"] == "recent_memory"


@pytest.mark.asyncio
async def test_recent_memory_most_recent_wins(principal, migrated: None) -> None:
    token, uid = principal
    await _ensure_user(uid)
    eating = await _category("eating_out")
    shopping = await _category("shopping")
    # older categorized txn -> eating_out
    older = (
        await _quick_add(
            token, {"amount": "5.00", "merchant_input": "Wolt", "occurred_on": "2026-06-20"}
        )
    ).json()["transaction"]
    await _categorize(token, older["id"], {"category_id": eating})
    # newer categorized txn (default today) -> shopping
    newer_id, merchant = await _add_wolt(token)
    await _categorize(token, newer_id, {"category_id": shopping})

    item = _item_for((await _suggest(token, "Wolt")).json(), merchant)
    assert item["suggested_category_id"] == shopping  # recency leads


@pytest.mark.asyncio
async def test_rule_beats_recent_memory(principal, migrated: None) -> None:
    token, uid = principal
    await _ensure_user(uid)
    eating = await _category("eating_out")
    shopping = await _category("shopping")
    merchant = await _promote_wolt(token, eating)            # rule -> eating_out
    newer_id, _ = await _add_wolt(token)
    await _categorize(token, newer_id, {"category_id": shopping})  # newer memory -> shopping

    item = _item_for((await _suggest(token, "Wolt")).json(), merchant)
    assert item["suggested_category_id"] == eating  # rule outranks memory
    assert item["suggested_category_source"] == "user_correction_merchant_exact"


@pytest.mark.asyncio
async def test_recent_memory_excludes_bank_movement(principal, migrated: None) -> None:
    token, uid = principal
    await _ensure_user(uid)
    bank = await _bank_category()
    merchant = await _seed_merchant(uid, "wolt", "Wolt")
    await _seed_categorized_txn(uid, merchant, bank)  # a bank-categorized row

    item = _item_for((await _suggest(token, "Wolt")).json(), merchant)
    # bank_movement is never suggested in Quick Add (§9) -> no memory.
    assert item["suggested_category_id"] is None
    assert item["suggested_category_source"] == "none"


@pytest.mark.asyncio
async def test_quick_add_uses_recent_memory(principal, migrated: None) -> None:
    token, uid = principal
    await _ensure_user(uid)
    eating = await _category("eating_out")
    txn_id, _ = await _add_wolt(token)
    await _categorize(token, txn_id, {"category_id": eating})  # categorize only

    resp = (await _quick_add(token, {"amount": "8.00", "merchant_input": "Wolt"})).json()
    sugg = resp["category_suggestion"]
    assert sugg is not None
    assert sugg["category_id"] == eating
    assert sugg["source"] == "recent_memory"
    assert resp["transaction"]["category_id"] is None  # suggest-only
