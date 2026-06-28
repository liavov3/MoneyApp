"""/api/v1/recurring-templates — CRUD slice (API_CONTRACT §12).

Covers create/list/patch/delete; money sign + validation; consumer-category
enforcement; cadence/date validation; merchant ownership; deterministic list
order + active filter; user isolation (list/patch/delete → 404); the
projection-only invariant (NO transaction ever written); Home integration
(active template feeds committed/upcoming, never blends into actual spend); and
no-PII logging.

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

TEMPLATE_FIELDS = {
    "id", "name", "amount_minor", "currency", "category_id", "category_key",
    "merchant_id", "cadence", "next_expected_date", "counts_in_projection",
    "is_active", "note", "created_at", "updated_at",
}


@pytest_asyncio.fixture(autouse=True)
async def _fresh_global_engine():
    _db._engine = None
    _db._sessionmaker = None
    yield
    await _db.dispose_engine()


@pytest.fixture
def principal(monkeypatch) -> tuple[str, str]:
    token = "test-recurring-token-1a"
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


async def _insert_merchant(uid: str, normalized: str = "gym") -> str:
    async with get_sessionmaker()() as s:
        row = (
            await s.execute(
                text(
                    "INSERT INTO merchants (user_id, normalized_merchant_name, display_name) "
                    "VALUES (:u, :n, :d) RETURNING id::text AS id"
                ),
                {"u": uid, "n": normalized, "d": normalized.title()},
            )
        ).mappings().one()
        await s.commit()
        return row["id"]


async def _txn_count(uid: str) -> int:
    async with get_sessionmaker()() as s:
        return (
            await s.execute(
                text("SELECT COUNT(*) FROM transactions WHERE user_id = :u"), {"u": uid}
            )
        ).scalar_one()


# --------------------------------------------------------------------------- #
# HTTP helpers
# --------------------------------------------------------------------------- #
def _client():
    return AsyncClient(transport=ASGITransport(app=create_app()), base_url="http://test")


def _auth(token: str | None) -> dict:
    return {"Authorization": f"Bearer {token}"} if token is not None else {}


async def _post(token: str | None, payload: dict):
    async with _client() as c:
        return await c.post("/api/v1/recurring-templates", json=payload, headers=_auth(token))


async def _list(token: str | None, params: dict | None = None):
    async with _client() as c:
        return await c.get("/api/v1/recurring-templates", params=params, headers=_auth(token))


async def _patch(token: str, tid: str, payload: dict):
    async with _client() as c:
        return await c.patch(f"/api/v1/recurring-templates/{tid}", json=payload, headers=_auth(token))


async def _delete(token: str, tid: str):
    async with _client() as c:
        return await c.delete(f"/api/v1/recurring-templates/{tid}", headers=_auth(token))


async def _home(token: str, params: dict):
    async with _client() as c:
        return await c.get("/api/v1/home", params=params, headers=_auth(token))


async def _quick_add(token: str, payload: dict):
    async with _client() as c:
        return await c.post("/api/v1/transactions/quick-add", json=payload, headers=_auth(token))


def _valid_payload(category_id: str, **over) -> dict:
    base = {
        "name": "Gym", "amount": "120", "category_id": category_id,
        "cadence": "monthly", "next_expected_date": "2026-06-20",
    }
    base.update(over)
    return base


# --------------------------------------------------------------------------- #
# Auth — no DB.
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_missing_token_returns_401(principal) -> None:
    resp = await _list(None)
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "unauthorized"


# --------------------------------------------------------------------------- #
# Create.
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_create_happy_path(principal, migrated: None) -> None:
    token, uid = principal
    await _ensure_user(uid)
    health = await _cat_id("health")
    before = await _txn_count(uid)

    resp = await _post(token, _valid_payload(health))
    assert resp.status_code == 201
    body = resp.json()
    assert set(body.keys()) == TEMPLATE_FIELDS
    assert body["name"] == "Gym"
    assert body["amount_minor"] == -12000          # stored negative (expense sign)
    assert body["currency"] == "ILS"
    assert body["category_id"] == health
    assert body["category_key"] == "health"
    assert body["cadence"] == "monthly"
    assert body["next_expected_date"] == "2026-06-20"
    assert body["counts_in_projection"] is True    # default
    assert body["is_active"] is True               # default
    assert body["created_at"].endswith("Z")

    # Projection-only: NO transaction created.
    assert await _txn_count(uid) == before


@pytest.mark.asyncio
async def test_create_required_field_validation(principal, migrated: None) -> None:
    token, uid = principal
    await _ensure_user(uid)
    health = await _cat_id("health")
    for missing in ("name", "amount", "category_id", "next_expected_date"):
        payload = _valid_payload(health)
        del payload[missing]
        resp = await _post(token, payload)
        assert resp.status_code == 422, missing
        assert resp.json()["error"]["code"] == "validation_error"


@pytest.mark.asyncio
async def test_create_money_validation(principal, migrated: None) -> None:
    token, uid = principal
    await _ensure_user(uid)
    health = await _cat_id("health")
    cases = {"0": "zero_amount", "-5": "negative_amount", "1.999": "too_many_decimals"}
    for amount, code in cases.items():
        resp = await _post(token, _valid_payload(health, amount=amount))
        assert resp.status_code == 422, amount
        codes = {fe["code"] for fe in resp.json()["error"]["field_errors"]}
        assert code in codes, (amount, codes)


@pytest.mark.asyncio
async def test_create_cadence_and_date_validation(principal, migrated: None) -> None:
    token, uid = principal
    await _ensure_user(uid)
    health = await _cat_id("health")
    bad_cadence = await _post(token, _valid_payload(health, cadence="daily"))
    assert bad_cadence.status_code == 422
    bad_date = await _post(token, _valid_payload(health, next_expected_date="2026-13-40"))
    assert bad_date.status_code == 422
    # weekly + yearly are accepted by the frozen schema.
    for cad in ("weekly", "yearly", "monthly"):
        ok = await _post(token, _valid_payload(health, cadence=cad))
        assert ok.status_code == 201, cad


@pytest.mark.asyncio
async def test_create_category_validation(principal, migrated: None) -> None:
    token, uid = principal
    await _ensure_user(uid)
    bank_mv = await _cat_id("interest_bank_fee")  # bank_movement layer
    resp = await _post(token, _valid_payload(bank_mv))
    assert resp.status_code == 422
    codes = {fe["code"] for fe in resp.json()["error"]["field_errors"]}
    assert "not_consumer_category" in codes

    unknown = await _post(token, _valid_payload(str(uuid.uuid4())))
    assert unknown.status_code == 422
    codes = {fe["code"] for fe in unknown.json()["error"]["field_errors"]}
    assert "invalid_category" in codes


@pytest.mark.asyncio
async def test_create_merchant_ownership(principal, migrated: None) -> None:
    token, uid = principal
    await _ensure_user(uid)
    health = await _cat_id("health")
    mine = await _insert_merchant(uid)
    ok = await _post(token, _valid_payload(health, merchant_id=mine))
    assert ok.status_code == 201
    assert ok.json()["merchant_id"] == mine

    other = str(uuid.uuid4())
    await _ensure_user(other)
    foreign = await _insert_merchant(other, "foreigngym")
    bad = await _post(token, _valid_payload(health, merchant_id=foreign))
    assert bad.status_code == 422
    codes = {fe["code"] for fe in bad.json()["error"]["field_errors"]}
    assert "invalid_merchant" in codes


# --------------------------------------------------------------------------- #
# List.
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_list_empty_and_shape(principal, migrated: None) -> None:
    token, uid = principal
    await _ensure_user(uid)
    resp = await _list(token)
    assert resp.status_code == 200
    assert resp.json() == {"items": []}


@pytest.mark.asyncio
async def test_list_active_filter_and_order(principal, migrated: None) -> None:
    token, uid = principal
    await _ensure_user(uid)
    health = await _cat_id("health")
    # Insert out of date order; expect ascending next_expected_date.
    t2 = (await _post(token, _valid_payload(health, next_expected_date="2026-06-25"))).json()["id"]
    t1 = (await _post(token, _valid_payload(health, next_expected_date="2026-06-10"))).json()["id"]
    t3 = (await _post(token, _valid_payload(health, next_expected_date="2026-07-01"))).json()["id"]
    await _patch(token, t3, {"is_active": False})

    all_ids = [i["id"] for i in (await _list(token)).json()["items"]]
    assert all_ids == [t1, t2, t3]  # deterministic asc order

    active_ids = {i["id"] for i in (await _list(token, {"active": "true"})).json()["items"]}
    assert active_ids == {t1, t2}
    inactive_ids = {i["id"] for i in (await _list(token, {"active": "false"})).json()["items"]}
    assert inactive_ids == {t3}


# --------------------------------------------------------------------------- #
# Patch.
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_patch_updates_fields(principal, migrated: None) -> None:
    token, uid = principal
    await _ensure_user(uid)
    health = await _cat_id("health")
    subs = await _cat_id("subscriptions")
    tid = (await _post(token, _valid_payload(health))).json()["id"]
    before = await _txn_count(uid)

    resp = await _patch(token, tid, {
        "name": "Netflix", "amount": "45.90", "category_id": subs,
        "next_expected_date": "2026-07-05", "cadence": "yearly",
        "counts_in_projection": False, "note": "x",
    })
    assert resp.status_code == 200
    body = resp.json()
    assert body["name"] == "Netflix"
    assert body["amount_minor"] == -4590
    assert body["category_id"] == subs and body["category_key"] == "subscriptions"
    assert body["next_expected_date"] == "2026-07-05"
    assert body["cadence"] == "yearly"
    assert body["counts_in_projection"] is False
    assert body["note"] == "x"
    assert await _txn_count(uid) == before  # still no transaction


@pytest.mark.asyncio
async def test_patch_validation_and_empty(principal, migrated: None) -> None:
    token, uid = principal
    await _ensure_user(uid)
    health = await _cat_id("health")
    tid = (await _post(token, _valid_payload(health))).json()["id"]

    assert (await _patch(token, tid, {})).status_code == 422            # empty patch
    assert (await _patch(token, tid, {"amount": "0"})).status_code == 422
    assert (await _patch(token, tid, {"cadence": "daily"})).status_code == 422
    bank_mv = await _cat_id("interest_bank_fee")
    assert (await _patch(token, tid, {"category_id": bank_mv})).status_code == 422


@pytest.mark.asyncio
async def test_patch_malformed_and_missing_id(principal, migrated: None) -> None:
    token, uid = principal
    await _ensure_user(uid)
    assert (await _patch(token, "not-a-uuid", {"name": "X"})).status_code == 404
    assert (await _patch(token, str(uuid.uuid4()), {"name": "X"})).status_code == 404


# --------------------------------------------------------------------------- #
# Delete.
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_delete_hard_removes(principal, migrated: None) -> None:
    token, uid = principal
    await _ensure_user(uid)
    health = await _cat_id("health")
    tid = (await _post(token, _valid_payload(health))).json()["id"]
    before = await _txn_count(uid)

    assert (await _delete(token, tid)).status_code == 204
    assert (await _list(token)).json()["items"] == []
    assert (await _delete(token, tid)).status_code == 404   # already gone
    assert await _txn_count(uid) == before                  # no transaction touched


@pytest.mark.asyncio
async def test_delete_malformed_and_missing_id(principal, migrated: None) -> None:
    token, uid = principal
    await _ensure_user(uid)
    assert (await _delete(token, "not-a-uuid")).status_code == 404
    assert (await _delete(token, str(uuid.uuid4()))).status_code == 404


# --------------------------------------------------------------------------- #
# User isolation.
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_user_isolation(principal, migrated: None) -> None:
    token, uid = principal
    await _ensure_user(uid)
    health = await _cat_id("health")
    mine = (await _post(token, _valid_payload(health))).json()["id"]

    # Another principal owns their own template.
    other_uid = str(uuid.uuid4())
    other_token = "other-recurring-token"
    async with get_sessionmaker()() as s:  # ensure other user exists
        await s.execute(
            text("INSERT INTO users (id, base_currency, locale) SELECT :u,'ILS','en' "
                 "WHERE NOT EXISTS (SELECT 1 FROM users WHERE id=:u)"),
            {"u": other_uid},
        )
        # directly insert a template for the other user
        await s.execute(
            text(
                "INSERT INTO recurring_expense_templates "
                "(user_id, name, amount_minor, currency, category_id, cadence, next_expected_date) "
                "VALUES (:u,'Theirs',-9999,'ILS',CAST(:c AS uuid),'monthly',:d)"
            ),
            {"u": other_uid, "c": health, "d": date(2026, 6, 15)},
        )
        await s.commit()
    # Fetch the other user's template id straight from DB.
    async with get_sessionmaker()() as s:
        other_tid = (
            await s.execute(
                text("SELECT id::text FROM recurring_expense_templates WHERE user_id=:u"),
                {"u": other_uid},
            )
        ).scalar_one()

    # A's list shows only A's template.
    my_ids = {i["id"] for i in (await _list(token)).json()["items"]}
    assert my_ids == {mine}

    # A cannot PATCH/DELETE B's template -> generic 404.
    assert (await _patch(token, other_tid, {"name": "hack"})).status_code == 404
    assert (await _delete(token, other_tid)).status_code == 404


# --------------------------------------------------------------------------- #
# Home integration — planned vs actual separation (never blended).
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_home_integration_no_blend(principal, migrated: None) -> None:
    token, uid = principal
    await _ensure_user(uid)
    groceries = await _cat_id("groceries")
    health = await _cat_id("health")

    # ₪33 actual expense + ₪120 active monthly template (this month).
    await _quick_add(token, {"amount": "33", "category_id": groceries, "occurred_on": "2026-06-10"})
    tid = (await _post(token, _valid_payload(health, amount="120", next_expected_date="2026-06-20"))).json()["id"]

    home = (await _home(token, {"month": "2026-06"})).json()
    assert home["spent_so_far_minor"] == 3300            # actual only
    assert home["committed_amount_minor"] == 12000       # projected only
    assert home["known_this_month"] == {
        "spent_actual_minor": 3300, "committed_projected_minor": 12000
    }
    # Template never pollutes actual category totals.
    assert [c["category_key"] for c in home["category_totals"]] == ["groceries"]
    # Template appears in the upcoming list.
    assert {u["template_id"] for u in home["upcoming_commitments"]} == {tid}

    # Deactivate -> drops from projection, actual untouched.
    await _patch(token, tid, {"is_active": False})
    home2 = (await _home(token, {"month": "2026-06"})).json()
    assert home2["committed_amount_minor"] == 0
    assert home2["upcoming_commitments"] == []
    assert home2["spent_so_far_minor"] == 3300


# --------------------------------------------------------------------------- #
# Privacy — no name/note/amount in logs.
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_no_pii_in_logs(principal, migrated: None) -> None:
    token, uid = principal
    await _ensure_user(uid)
    health = await _cat_id("health")

    records: list[logging.LogRecord] = []

    class _Capture(logging.Handler):
        def emit(self, record: logging.LogRecord) -> None:
            records.append(record)

    handler = _Capture()
    logger = get_logger()
    prev = logger.level
    logger.addHandler(handler)
    logger.setLevel(logging.DEBUG)
    secret_name = "SecretGymZZZ"
    secret_note = "secret-note-yyy"
    try:
        resp = await _post(token, _valid_payload(
            health, name=secret_name, note=secret_note, amount="765.43"
        ))
    finally:
        logger.removeHandler(handler)
        logger.setLevel(prev)

    assert resp.status_code == 201
    assert records
    for r in records:
        rendered = r.getMessage() + " " + " ".join(str(v) for v in (r.args or ()))
        assert secret_name not in rendered
        assert secret_note not in rendered
        assert "765.43" not in rendered
        assert "76543" not in rendered
