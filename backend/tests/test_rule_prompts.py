"""Quick Add's post-save, explicitly accepted category learning (API §8/§10)."""
import asyncio
import logging
from logging.handlers import BufferingHandler
from uuid import uuid4

import pytest
import pytest_asyncio
from httpx import ASGITransport, AsyncClient
from sqlalchemy import text
from sqlalchemy.ext.asyncio import AsyncSession

import app.db as db
from app.config import get_settings
from app.db import get_sessionmaker
from app.logging_utils import get_logger
from app.main import create_app
from app.routers import transactions

TOKEN = "rule-prompt-test-only"


@pytest_asyncio.fixture
async def owner(monkeypatch, migrated):
    uid = str(uuid4())
    monkeypatch.setenv("DEV_USER_ID", uid)
    monkeypatch.setenv("DEV_BEARER_TOKEN", TOKEN)
    get_settings.cache_clear()
    db._engine = None
    db._sessionmaker = None
    async with get_sessionmaker()() as session:
        await session.execute(text("INSERT INTO users (id,base_currency) VALUES (:u,'ILS')"), {"u": uid})
        await session.commit()
    try:
        yield uid
    finally:
        async with get_sessionmaker()() as session:
            await session.execute(text("DELETE FROM users WHERE id=:u"), {"u": uid})
            await session.commit()
        await db.dispose_engine()
        get_settings.cache_clear()


async def call(method, path, body=None):
    async with AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://test") as client:
        return await client.request(method, "/api/v1" + path, json=body,
                                    headers={"Authorization": "Bearer " + TOKEN})


async def category(key):
    async with get_sessionmaker()() as session:
        return (await session.execute(text("SELECT id::text FROM categories WHERE key=:k AND user_id IS NULL"), {"k": key})).scalar_one()


async def quick(merchant="Golda", category_key="eating_out", amount="31.25"):
    body = {"amount": amount}
    if merchant is not None:
        body["merchant_input"] = merchant
    if category_key is not None:
        body["category_id"] = await category(category_key)
    response = await call("POST", "/transactions/quick-add", body)
    assert response.status_code == 201
    return response.json()


async def rule_count(uid):
    async with get_sessionmaker()() as session:
        return (await session.execute(text("SELECT count(*) FROM category_rules WHERE user_id=:u"), {"u": uid})).scalar_one()


@pytest.mark.asyncio
async def test_offer_describes_saved_mapping_without_creating_a_rule(owner):
    result = await quick()
    txn = result["transaction"]
    assert result["rule_prompt"] == {
        "offer": True, "merchant_id": txn["merchant_id"],
        "suggested_category_id": txn["category_id"], "suggested_category_key": "eating_out",
    }
    assert txn["amount_minor"] == -3125
    assert await rule_count(owner) == 0  # ignoring/declining the prompt makes no write


@pytest.mark.asyncio
@pytest.mark.parametrize("merchant,category_key", [
    (None, None), (None, "eating_out"), ("Golda", None),
    ("Golda", "other_spending"), ("Bit", "gifts"), ("ביט", "gifts"),
    ("Paybox", "gifts"), ("ATM", "other_spending"), ("Market", "groceries"),
    ("העברה יוצאת", "gifts"), ("Max", "shopping"),
])
async def test_no_offer_for_incomplete_one_off_or_generic_entries(owner, merchant, category_key):
    assert (await quick(merchant, category_key))["rule_prompt"] == {"offer": False}
    assert await rule_count(owner) == 0


@pytest.mark.asyncio
async def test_named_cafe_is_not_mistaken_for_a_generic_payee(owner):
    assert (await quick("Cafe Greg"))["rule_prompt"]["offer"] is True


@pytest.mark.asyncio
@pytest.mark.parametrize("match_type,active,source,expected", [
    ("merchant_exact", True, "user_correction", False),
    ("merchant_exact", True, "system", False),
    ("merchant_exact", False, "user_correction", True),
    ("merchant_contains", True, "user_correction", True),
])
async def test_only_active_exact_rules_suppress_the_offer(owner, match_type, active, source, expected):
    cat = await category("shopping")
    async with get_sessionmaker()() as session:
        await session.execute(text("""INSERT INTO category_rules
            (user_id,match_type,match_value,category_id,source,is_active)
            VALUES (:u,:mt,'golda',CAST(:cat AS uuid),:source,:active)"""),
            {"u": owner, "mt": match_type, "cat": cat, "source": source, "active": active})
        await session.commit()
    assert (await quick())["rule_prompt"]["offer"] is expected


@pytest.mark.asyncio
async def test_other_repeat_threshold_is_per_owned_merchant(owner):
    foreign = str(uuid4())
    cat = await category("other_spending")
    async with get_sessionmaker()() as session:
        await session.execute(text("INSERT INTO users(id,base_currency) VALUES(:u,'ILS')"), {"u": foreign})
        await session.execute(text("""INSERT INTO category_rules(user_id,match_type,match_value,category_id)
            VALUES(:u,'merchant_exact','golda',CAST(:cat AS uuid))"""), {"u": foreign, "cat": cat})
        await session.commit()
    try:
        await quick("Different merchant", "other_spending")
        await quick("Different merchant", "other_spending")
        assert (await quick("Golda", "other_spending"))["rule_prompt"]["offer"] is False
        repeated = await quick("Golda", "other_spending")
        assert repeated["rule_prompt"]["offer"] is True
        assert repeated["rule_prompt"]["suggested_category_key"] == "other_spending"
        assert await rule_count(owner) == 0
    finally:
        async with get_sessionmaker()() as session:
            await session.execute(text("DELETE FROM users WHERE id=:u"), {"u": foreign})
            await session.commit()


@pytest.mark.asyncio
async def test_confirmation_learns_for_future_suggestions_and_preserves_prior_rows(owner):
    prior = await quick(category_key="shopping", amount="6.10")
    saved = await quick()
    txn = saved["transaction"]
    body = {"category_id": txn["category_id"], "promote_to_rule": True,
            "match_type": "merchant_exact", "apply_to_existing": False}
    for _ in range(2):  # an explicit retry updates one rule, never stacks it
        response = await call("POST", f"/transactions/{txn['id']}/categorize", body)
        assert response.status_code == 200
        assert response.json()["applied_to_existing_count"] == 0
        assert response.json()["rule"]["source"] == "user_correction"
    assert await rule_count(owner) == 1
    old = (await call("GET", f"/transactions/{prior['transaction']['id']}")).json()
    assert old["category_key"] == "shopping" and old["amount_minor"] == -610
    suggestions = (await call("GET", "/merchants/suggestions?query=Golda")).json()
    item = next(item for item in suggestions["items"] if item["merchant_id"] == txn["merchant_id"])
    assert item["suggested_category_id"] == txn["category_id"]
    assert item["suggested_category_source"] == "user_correction_merchant_exact"
    assert (await quick())["rule_prompt"] == {"offer": False}


@pytest.mark.asyncio
async def test_concurrent_merchant_edit_and_promotion_use_one_consistent_merchant(owner, monkeypatch):
    saved = (await quick())["transaction"]
    replacement = (await quick("Cafe Greg"))["transaction"]
    reached_lookup = asyncio.Future()
    execute = AsyncSession.execute

    async def observe_lookup(session, statement, params=None, *args, **kwargs):
        if (str(statement).startswith("SELECT merchant_id::text AS merchant_id FROM transactions ")
                and params and params.get("id") == saved["id"] and not reached_lookup.done()):
            pid = (await execute(session, text("SELECT pg_backend_pid()"))).scalar_one()
            reached_lookup.set_result(pid)
        return await execute(session, statement, params, *args, **kwargs)

    monkeypatch.setattr(AsyncSession, "execute", observe_lookup)
    promotion = None
    try:
        async with get_sessionmaker()() as writer:
            # Hold an uncommitted merchant edit. Promotion must wait and use
            # that committed identity, rather than reading the old name and
            # then waiting only when its category UPDATE reaches the row.
            await writer.execute(text("UPDATE transactions SET merchant_id=CAST(:m AS uuid) WHERE id=:id AND user_id=:u"),
                                 {"m": replacement["merchant_id"], "id": saved["id"], "u": owner})
            promotion = asyncio.create_task(call("POST", f"/transactions/{saved['id']}/categorize", {
                "category_id": saved["category_id"], "promote_to_rule": True,
                "match_type": "merchant_exact", "apply_to_existing": False,
            }))
            async with asyncio.timeout(15):
                pid = await reached_lookup
                async with get_sessionmaker()() as observer:
                    while not (await observer.execute(text("SELECT cardinality(pg_blocking_pids(:pid))"), {"pid": pid})).scalar_one():
                        await asyncio.sleep(0.01)
            await writer.commit()
        response = await asyncio.wait_for(promotion, timeout=15)
        assert response.status_code == 200
        assert response.json()["transaction"]["merchant_id"] == replacement["merchant_id"]
        assert response.json()["transaction"]["amount_minor"] == -3125
        async with get_sessionmaker()() as session:
            rule = (await session.execute(text("SELECT match_value FROM category_rules WHERE user_id=:u"), {"u": owner})).scalar_one()
        assert rule == "cafe greg"
    finally:
        if promotion and not promotion.done():
            promotion.cancel()
            await asyncio.gather(promotion, return_exceptions=True)


@pytest.mark.asyncio
@pytest.mark.parametrize("mode", ["failure", "timeout"])
async def test_rule_offer_failure_preserves_saved_transaction_and_duplicate_warning(owner, monkeypatch, mode):
    first = await quick()
    cancelled = []
    async def broken(*args):
        if mode == "failure":
            raise RuntimeError("private-rule-lookup-input")
        try:
            await asyncio.sleep(30)
        finally:
            cancelled.append(True)
    async def duplicate(*args):
        return first["transaction"]["id"]
    monkeypatch.setattr(transactions, "quick_add_rule_prompt", broken)
    monkeypatch.setattr(transactions, "_find_duplicate", duplicate)
    monkeypatch.setattr(transactions, "_WARNING_TIMEOUT_SECONDS", 0.01)
    logger = get_logger()
    previous = logger.level
    handler = BufferingHandler(100)
    logger.addHandler(handler)
    logger.setLevel(logging.INFO)
    try:
        saved = await quick()
    finally:
        logger.removeHandler(handler)
        logger.setLevel(previous)
    assert saved["rule_prompt"] == {"offer": False}
    assert saved["warnings"][0]["similar_transaction_id"] == first["transaction"]["id"]
    assert saved["transaction"]["id"] != first["transaction"]["id"]
    fetched = await call("GET", f"/transactions/{saved['transaction']['id']}")
    assert fetched.status_code == 200 and fetched.json()["amount_minor"] == -3125
    assert await rule_count(owner) == 0
    messages = " ".join(record.getMessage() for record in handler.buffer)
    assert "quick_add_rule_prompt_skipped" in messages
    assert "private-rule-lookup-input" not in messages
    assert bool(cancelled) is (mode == "timeout")
