"""GET /api/v1/home — dashboard slice (API_CONTRACT §13).

Covers: contract response shape; empty state; the Layer-A spend filter (manual
expenses, in-month, settlements/income/refunds excluded, uncategorized counted
but not ranked, bank_movement categories excluded); category_totals ranking +
top_category; month boundaries; the all-time recent recall list (schema §10
query 3); uncategorized_count (month-scoped, query 4); Layer-B projection +
the actual/projected separation (NEVER blended); user isolation; bad `month`
→ 422; and no PII in logs.

Each test uses a FRESH ephemeral principal (random DEV_USER_ID), which also
proves per-user isolation. 401 tests need no DB; the rest require a migrated DB.
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

HOME_FIELDS = {
    "month", "currency", "spent_so_far_minor", "top_category", "category_totals",
    "recent_transactions", "uncategorized_count", "upcoming_commitments",
    "committed_amount_minor", "known_this_month", "warnings",
}
RECENT_FIELDS = {
    "id", "amount_minor", "currency", "merchant_display_name", "category_key",
    "occurred_on", "is_uncategorized",
}
CAT_TOTAL_FIELDS = {"category_id", "category_key", "label_en", "total_minor"}
UPCOMING_FIELDS = {
    "template_id", "name_present", "category_key", "amount_minor",
    "next_expected_date",
}


@pytest_asyncio.fixture(autouse=True)
async def _fresh_global_engine():
    _db._engine = None
    _db._sessionmaker = None
    yield
    await _db.dispose_engine()


@pytest.fixture
def principal(monkeypatch) -> tuple[str, str]:
    token = "test-home-token-9f"
    uid = str(uuid.uuid4())
    monkeypatch.setenv("DEV_BEARER_TOKEN", token)
    monkeypatch.setenv("DEV_USER_ID", uid)
    get_settings.cache_clear()
    yield token, uid
    get_settings.cache_clear()


# --------------------------------------------------------------------------- #
# DB helpers
# --------------------------------------------------------------------------- #
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


async def _cat_id(key: str) -> str:
    async with get_sessionmaker()() as s:
        return (
            await s.execute(
                text("SELECT id::text FROM categories WHERE key = :k AND user_id IS NULL"),
                {"k": key},
            )
        ).scalar_one()


async def _insert_txn(
    uid: str,
    amount_minor: int,
    occurred_on: str,
    *,
    ttype: str = "expense",
    category_id: str | None = None,
    source: str = "manual",
    is_card_settlement: bool = False,
) -> str:
    async with get_sessionmaker()() as s:
        row = (
            await s.execute(
                text(
                    "INSERT INTO transactions "
                    "(user_id, amount_minor, currency, transaction_type, source, "
                    " occurred_on, category_id, is_card_settlement) "
                    "VALUES (:u, :a, 'ILS', :tt, :src, :d, CAST(:c AS uuid), :s) "
                    "RETURNING id::text AS id"
                ),
                {
                    "u": uid, "a": amount_minor, "tt": ttype, "src": source,
                    "d": date.fromisoformat(occurred_on), "c": category_id,
                    "s": is_card_settlement,
                },
            )
        ).mappings().one()
        await s.commit()
        return row["id"]


async def _insert_template(
    uid: str,
    amount_minor: int,
    next_expected_date: str,
    category_id: str,
    *,
    is_active: bool = True,
    counts_in_projection: bool = True,
) -> str:
    async with get_sessionmaker()() as s:
        row = (
            await s.execute(
                text(
                    "INSERT INTO recurring_expense_templates "
                    "(user_id, name, amount_minor, currency, category_id, cadence, "
                    " next_expected_date, counts_in_projection, is_active) "
                    "VALUES (:u, 'Gym', :a, 'ILS', CAST(:c AS uuid), 'monthly', "
                    " :d, :cp, :ia) RETURNING id::text AS id"
                ),
                {
                    "u": uid, "a": amount_minor, "c": category_id,
                    "d": date.fromisoformat(next_expected_date),
                    "cp": counts_in_projection, "ia": is_active,
                },
            )
        ).mappings().one()
        await s.commit()
        return row["id"]


async def _home(token: str | None, params: dict | None = None):
    app = create_app()
    headers = {"Authorization": f"Bearer {token}"} if token is not None else {}
    transport = ASGITransport(app=app)
    async with AsyncClient(transport=transport, base_url="http://test") as client:
        return await client.get("/api/v1/home", params=params, headers=headers)


# --------------------------------------------------------------------------- #
# Auth — no DB required.
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_missing_token_returns_401(principal) -> None:
    resp = await _home(None)
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "unauthorized"


@pytest.mark.asyncio
async def test_invalid_token_returns_401(principal) -> None:
    resp = await _home("wrong-token")
    assert resp.status_code == 401


# --------------------------------------------------------------------------- #
# Empty state — valid contract-shaped zero/null/empty response.
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_empty_state_shape(principal, migrated: None) -> None:
    token, uid = principal
    await _ensure_user(uid)
    resp = await _home(token, {"month": "2026-06"})
    assert resp.status_code == 200
    body = resp.json()
    assert set(body.keys()) == HOME_FIELDS
    assert body["month"] == "2026-06"
    assert body["currency"] == "ILS"
    assert body["spent_so_far_minor"] == 0
    assert body["top_category"] is None
    assert body["category_totals"] == []
    assert body["recent_transactions"] == []
    assert body["uncategorized_count"] == 0
    assert body["upcoming_commitments"] == []
    assert body["committed_amount_minor"] == 0
    assert body["known_this_month"] == {
        "spent_actual_minor": 0, "committed_projected_minor": 0
    }
    assert body["warnings"] == []


# --------------------------------------------------------------------------- #
# Happy path — totals, ranking, top category, uncategorized, recent.
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_happy_path_dashboard(principal, migrated: None) -> None:
    token, uid = principal
    await _ensure_user(uid)
    groceries = await _cat_id("groceries")
    eating_out = await _cat_id("eating_out")

    await _insert_txn(uid, -78000, "2026-06-03", category_id=groceries)
    await _insert_txn(uid, -51000, "2026-06-14", category_id=eating_out)
    await _insert_txn(uid, -5000, "2026-06-14")  # uncategorized expense

    body = (await _home(token, {"month": "2026-06"})).json()

    # spent_so_far includes the uncategorized expense (magnitude sum).
    assert body["spent_so_far_minor"] == 78000 + 51000 + 5000

    # category_totals ranked DESC; uncategorized excluded.
    totals = body["category_totals"]
    assert [t["category_key"] for t in totals] == ["groceries", "eating_out"]
    assert totals[0]["total_minor"] == 78000
    assert set(totals[0].keys()) == CAT_TOTAL_FIELDS

    # top_category = the single largest.
    assert body["top_category"]["category_key"] == "groceries"
    assert body["top_category"]["total_minor"] == 78000

    # uncategorized_count = the one null-category row.
    assert body["uncategorized_count"] == 1

    # recent_transactions shape + the uncategorized flag.
    assert len(body["recent_transactions"]) == 3
    for r in body["recent_transactions"]:
        assert set(r.keys()) == RECENT_FIELDS
    flagged = [r for r in body["recent_transactions"] if r["is_uncategorized"]]
    assert len(flagged) == 1 and flagged[0]["amount_minor"] == -5000


# --------------------------------------------------------------------------- #
# Signed-money / filter semantics for the Layer-A spend headline.
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_spend_excludes_income_refund_settlement_and_bank_movement(
    principal, migrated: None
) -> None:
    token, uid = principal
    await _ensure_user(uid)
    groceries = await _cat_id("groceries")
    # A bank_movement category (excluded from actual spending).
    bank_mv = await _cat_id("interest_bank_fee")

    await _insert_txn(uid, -10000, "2026-06-05", category_id=groceries)  # counts
    await _insert_txn(uid, 20000, "2026-06-05", ttype="income")          # excluded
    await _insert_txn(uid, 3000, "2026-06-05", ttype="refund")           # excluded
    await _insert_txn(uid, -7000, "2026-06-05", category_id=groceries,
                      is_card_settlement=True)                            # excluded
    await _insert_txn(uid, -9000, "2026-06-05", category_id=bank_mv)     # excluded

    body = (await _home(token, {"month": "2026-06"})).json()
    assert body["spent_so_far_minor"] == 10000  # only the manual grocery expense
    # bank_movement total never pollutes category_totals.
    assert [t["category_key"] for t in body["category_totals"]] == ["groceries"]
    assert body["category_totals"][0]["total_minor"] == 10000


# --------------------------------------------------------------------------- #
# Month boundaries — occurred_on, inclusive start / exclusive next month.
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_month_boundaries(principal, migrated: None) -> None:
    token, uid = principal
    await _ensure_user(uid)
    groceries = await _cat_id("groceries")
    await _insert_txn(uid, -100, "2026-05-31", category_id=groceries)  # before
    await _insert_txn(uid, -200, "2026-06-01", category_id=groceries)  # first day in
    await _insert_txn(uid, -300, "2026-06-30", category_id=groceries)  # last day in
    await _insert_txn(uid, -400, "2026-07-01", category_id=groceries)  # after

    body = (await _home(token, {"month": "2026-06"})).json()
    assert body["spent_so_far_minor"] == 200 + 300
    assert body["uncategorized_count"] == 0


# --------------------------------------------------------------------------- #
# Recent recall list is ALL-TIME (schema §10 query 3 has no month filter).
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_recent_is_all_time_not_month_scoped(principal, migrated: None) -> None:
    token, uid = principal
    await _ensure_user(uid)
    out_id = await _insert_txn(uid, -100, "2026-03-15")  # different month
    in_id = await _insert_txn(uid, -200, "2026-06-15")

    body = (await _home(token, {"month": "2026-06"})).json()
    recent_ids = {r["id"] for r in body["recent_transactions"]}
    assert out_id in recent_ids and in_id in recent_ids
    # ...but the out-of-month row does NOT count toward the month's spend.
    assert body["spent_so_far_minor"] == 200


# --------------------------------------------------------------------------- #
# Layer-B projection + actual/projected separation (NEVER blended).
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_actual_and_projected_never_blended(principal, migrated: None) -> None:
    """API_CONTRACT §13 test: ₪33 expense + ₪120 template -> 3300 & 12000, never 15300."""
    token, uid = principal
    await _ensure_user(uid)
    groceries = await _cat_id("groceries")
    health = await _cat_id("health")

    await _insert_txn(uid, -3300, "2026-06-10", category_id=groceries)
    tpl = await _insert_template(uid, -12000, "2026-06-20", health)

    body = (await _home(token, {"month": "2026-06"})).json()
    assert body["spent_so_far_minor"] == 3300
    assert body["committed_amount_minor"] == 12000
    assert body["known_this_month"] == {
        "spent_actual_minor": 3300, "committed_projected_minor": 12000
    }
    # No field anywhere equals the blended 15300.
    assert 15300 not in _all_ints(body)

    # upcoming_commitments item shape; raw signed amount echoed; name not echoed.
    assert len(body["upcoming_commitments"]) == 1
    item = body["upcoming_commitments"][0]
    assert set(item.keys()) == UPCOMING_FIELDS
    assert item["template_id"] == tpl
    assert item["name_present"] is True
    assert item["amount_minor"] == -12000
    assert item["category_key"] == "health"
    assert item["next_expected_date"] == "2026-06-20"


@pytest.mark.asyncio
async def test_projection_excludes_inactive_and_out_of_month(
    principal, migrated: None
) -> None:
    token, uid = principal
    await _ensure_user(uid)
    health = await _cat_id("health")
    await _insert_template(uid, -12000, "2026-06-20", health)                 # counts
    await _insert_template(uid, -50000, "2026-06-20", health, is_active=False)  # excl
    await _insert_template(uid, -50000, "2026-06-20", health,
                           counts_in_projection=False)                        # excl
    await _insert_template(uid, -50000, "2026-07-20", health)                 # excl (month)

    body = (await _home(token, {"month": "2026-06"})).json()
    assert body["committed_amount_minor"] == 12000
    assert len(body["upcoming_commitments"]) == 1


# --------------------------------------------------------------------------- #
# User isolation — another user's data never affects this dashboard.
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_user_isolation(principal, migrated: None) -> None:
    token, uid = principal
    await _ensure_user(uid)
    groceries = await _cat_id("groceries")
    health = await _cat_id("health")
    mine = await _insert_txn(uid, -1000, "2026-06-05", category_id=groceries)

    other = str(uuid.uuid4())
    await _ensure_user(other)
    await _insert_txn(other, -99999, "2026-06-05", category_id=groceries)
    await _insert_txn(other, -88888, "2026-06-05")  # uncategorized
    await _insert_template(other, -77777, "2026-06-20", health)

    body = (await _home(token, {"month": "2026-06"})).json()
    assert body["spent_so_far_minor"] == 1000
    assert body["uncategorized_count"] == 0
    assert body["committed_amount_minor"] == 0
    assert {r["id"] for r in body["recent_transactions"]} == {mine}
    assert body["category_totals"][0]["total_minor"] == 1000


# --------------------------------------------------------------------------- #
# Default month + invalid month param.
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_default_month_is_current(principal, migrated: None) -> None:
    token, uid = principal
    await _ensure_user(uid)
    groceries = await _cat_id("groceries")
    today = date.today()
    await _insert_txn(uid, -1234, today.isoformat(), category_id=groceries)

    body = (await _home(token)).json()  # no month param
    assert body["month"] == today.strftime("%Y-%m")
    assert body["spent_so_far_minor"] == 1234


@pytest.mark.asyncio
async def test_invalid_month_returns_422(principal, migrated: None) -> None:
    token, uid = principal
    await _ensure_user(uid)
    resp = await _home(token, {"month": "2026-13"})
    assert resp.status_code == 422
    err = resp.json()["error"]
    assert err["code"] == "validation_error"
    assert any(fe["field"] == "month" for fe in err["field_errors"])


# --------------------------------------------------------------------------- #
# Privacy — no amount / note / merchant text in logs.
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_no_pii_in_logs(principal, migrated: None) -> None:
    token, uid = principal
    await _ensure_user(uid)
    groceries = await _cat_id("groceries")
    await _insert_txn(uid, -424242, "2026-06-09", category_id=groceries)

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
        resp = await _home(token, {"month": "2026-06"})
    finally:
        logger.removeHandler(handler)
        logger.setLevel(prev)

    assert resp.status_code == 200
    assert records
    for r in records:
        rendered = r.getMessage() + " " + " ".join(str(v) for v in (r.args or ()))
        assert "424242" not in rendered
        assert "4242.42" not in rendered


def _all_ints(obj) -> set[int]:
    """Every integer value anywhere in the response (blend-detection helper)."""
    found: set[int] = set()
    if isinstance(obj, bool):
        return found
    if isinstance(obj, int):
        found.add(obj)
    elif isinstance(obj, dict):
        for v in obj.values():
            found |= _all_ints(v)
    elif isinstance(obj, list):
        for v in obj:
            found |= _all_ints(v)
    return found
