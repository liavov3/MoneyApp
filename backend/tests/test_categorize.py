"""POST /api/v1/transactions/{id}/categorize — categorize + rule promotion (§10).

Covers (QA-05-*, QA-06-*, QA-09-04, QA-10-03):
- 401 missing/invalid token; 404 malformed/missing/non-owned txn (never 403)
- categorize-only: sets category, rule=null, creates no category_rules row
- only category changes (amount/note/merchant_id/source/occurred_on untouched);
  updated_at advances, created_at stable
- invalid category -> invalid_category; bank_movement -> not_consumer_category
- promote_to_rule -> one rule, source=user_correction, match_value not echoed
- repeat promote same merchant -> UPDATES the one row (update-not-stack)
- apply_to_existing default false leaves priors; true bulk-updates + counts,
  scoped to the principal only
- promote on a merchant-less txn -> unknown_merchant; generic contains -> 422
- forged user_id ignored; no PII (category/merchant text/match_value) in logs

401/malformed need no DB; the rest require a migrated DB.
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
    token = "test-cat-token-1q"
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


async def _category(layer: str, key: str | None = None) -> tuple[str, str]:
    where = "layer = :l AND user_id IS NULL"
    params: dict = {"l": layer}
    if key is not None:
        where += " AND key = :k"
        params["k"] = key
    async with get_sessionmaker()() as s:
        r = (
            await s.execute(
                text(f"SELECT id::text AS id, key FROM categories WHERE {where} LIMIT 1"),
                params,
            )
        ).mappings().one()
        return r["id"], r["key"]


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


async def _seed_txn(uid: str, merchant_id: str | None, amount_minor: int) -> str:
    async with get_sessionmaker()() as s:
        row = (
            await s.execute(
                text(
                    "INSERT INTO transactions "
                    "(user_id, amount_minor, currency, transaction_type, source, merchant_id) "
                    "VALUES (:u, :a, 'ILS', 'expense', 'manual', CAST(:m AS uuid)) "
                    "RETURNING id::text AS id"
                ),
                {"u": uid, "a": amount_minor, "m": merchant_id},
            )
        ).mappings().one()
        await s.commit()
        return row["id"]


async def _raw_txn(txn_id: str):
    async with get_sessionmaker()() as s:
        return (
            await s.execute(
                text(
                    "SELECT category_id::text AS category_id, amount_minor, note, "
                    "merchant_id::text AS merchant_id, source, occurred_on::text AS occurred_on, "
                    "created_at, updated_at "
                    "FROM transactions WHERE id = CAST(:id AS uuid)"
                ),
                {"id": txn_id},
            )
        ).mappings().one_or_none()


async def _rules_count(uid: str) -> int:
    async with get_sessionmaker()() as s:
        return (
            await s.execute(
                text("SELECT count(*) FROM category_rules WHERE user_id = :u"), {"u": uid}
            )
        ).scalar_one()


async def _rule_row(uid: str, match_type: str, match_value: str):
    async with get_sessionmaker()() as s:
        return (
            await s.execute(
                text(
                    "SELECT id::text AS id, category_id::text AS category_id, source "
                    "FROM category_rules "
                    "WHERE user_id = :u AND match_type = :mt AND match_value = :mv"
                ),
                {"u": uid, "mt": match_type, "mv": match_value},
            )
        ).mappings().one_or_none()


def _client(app):
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def _quick_add(token: str, payload: dict):
    app = create_app()
    async with _client(app) as c:
        return await c.post(
            "/api/v1/transactions/quick-add", json=payload,
            headers={"Authorization": f"Bearer {token}"},
        )


async def _categorize(token: str | None, txn_id: str, body: dict | None):
    app = create_app()
    headers = {}
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    async with _client(app) as c:
        return await c.post(
            f"/api/v1/transactions/{txn_id}/categorize", json=body, headers=headers
        )


async def _add_wolt(token: str, amount: str = "10.00") -> tuple[str, str]:
    """Return (transaction_id, merchant_id) for a 'Wolt' quick-add."""
    t = (await _quick_add(token, {"amount": amount, "merchant_input": "Wolt"})).json()[
        "transaction"
    ]
    return t["id"], t["merchant_id"]


def _assert_401(resp) -> None:
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "unauthorized"


def _assert_404(resp) -> None:
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "not_found"


def _field_code(resp) -> str:
    return resp.json()["error"]["field_errors"][0]["code"]


# --------------------------------------------------------------------------- #
# Auth / not-found.
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_missing_token_returns_401(principal) -> None:
    _assert_401(await _categorize(None, str(uuid.uuid4()), {"category_id": str(uuid.uuid4())}))


@pytest.mark.asyncio
async def test_invalid_token_returns_401(principal) -> None:
    _assert_401(await _categorize("wrong", str(uuid.uuid4()), {"category_id": str(uuid.uuid4())}))


@pytest.mark.asyncio
async def test_malformed_id_returns_404(principal) -> None:
    token, _ = principal
    _assert_404(await _categorize(token, "not-a-uuid", {"category_id": str(uuid.uuid4())}))


@pytest.mark.asyncio
async def test_missing_txn_returns_404(principal, migrated: None) -> None:
    token, uid = principal
    await _ensure_user(uid)
    cat, _ = await _category("consumer_spending")
    _assert_404(await _categorize(token, str(uuid.uuid4()), {"category_id": cat}))


@pytest.mark.asyncio
async def test_other_users_txn_returns_404(principal, migrated: None) -> None:
    token, uid = principal
    await _ensure_user(uid)
    other = str(uuid.uuid4())
    await _ensure_user(other)
    other_txn = await _seed_txn(other, None, -4242)
    cat, _ = await _category("consumer_spending")
    resp = await _categorize(token, other_txn, {"category_id": cat})
    assert resp.status_code == 404  # NOT 403
    assert (await _raw_txn(other_txn))["category_id"] is None  # untouched


# --------------------------------------------------------------------------- #
# Categorize-only.
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_categorize_only_sets_category_no_rule(principal, migrated: None) -> None:
    token, uid = principal
    await _ensure_user(uid)
    txn_id, _ = await _add_wolt(token)
    cat, cat_key = await _category("consumer_spending", "eating_out")
    before = await _raw_txn(txn_id)

    resp = await _categorize(token, txn_id, {"category_id": cat})
    assert resp.status_code == 200
    body = resp.json()
    assert body["transaction"]["category_id"] == cat
    assert body["transaction"]["category_key"] == cat_key
    assert body["rule"] is None
    assert body["applied_to_existing_count"] == 0
    assert await _rules_count(uid) == 0  # no rule created

    after = await _raw_txn(txn_id)
    assert after["category_id"] == cat
    # Only the category changed.
    assert after["amount_minor"] == before["amount_minor"]
    assert after["note"] == before["note"]
    assert after["merchant_id"] == before["merchant_id"]
    assert after["source"] == before["source"]
    assert after["occurred_on"] == before["occurred_on"]
    assert after["created_at"] == before["created_at"]   # never changes
    assert after["updated_at"] > before["updated_at"]    # advances


@pytest.mark.asyncio
async def test_invalid_category_rejected(principal, migrated: None) -> None:
    token, uid = principal
    await _ensure_user(uid)
    txn_id, _ = await _add_wolt(token)
    resp = await _categorize(token, txn_id, {"category_id": str(uuid.uuid4())})
    assert resp.status_code == 422 and _field_code(resp) == "invalid_category"


@pytest.mark.asyncio
async def test_bank_movement_category_rejected(principal, migrated: None) -> None:
    token, uid = principal
    await _ensure_user(uid)
    txn_id, _ = await _add_wolt(token)
    bank, _ = await _category("bank_movement")
    resp = await _categorize(token, txn_id, {"category_id": bank})
    assert resp.status_code == 422 and _field_code(resp) == "not_consumer_category"
    assert (await _raw_txn(txn_id))["category_id"] is None  # unchanged


# --------------------------------------------------------------------------- #
# Rule promotion (update-not-stack).
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_promote_creates_one_user_correction_rule(principal, migrated: None) -> None:
    token, uid = principal
    await _ensure_user(uid)
    txn_id, _ = await _add_wolt(token)
    cat, cat_key = await _category("consumer_spending", "eating_out")

    body = (await _categorize(token, txn_id, {"category_id": cat, "promote_to_rule": True})).json()
    rule = body["rule"]
    assert rule is not None
    assert rule["match_type"] == "merchant_exact"
    assert rule["source"] == "user_correction"
    assert rule["category_id"] == cat
    assert rule["category_key"] == cat_key
    assert rule["match_value_present"] is True
    assert "match_value" not in rule  # raw fragment never echoed
    assert await _rules_count(uid) == 1
    db_rule = await _rule_row(uid, "merchant_exact", "wolt")  # match_value = normalized
    assert db_rule is not None and db_rule["source"] == "user_correction"


@pytest.mark.asyncio
async def test_repeat_promote_updates_not_stacks(principal, migrated: None) -> None:
    token, uid = principal
    await _ensure_user(uid)
    txn_id, _ = await _add_wolt(token)
    eating, _ = await _category("consumer_spending", "eating_out")
    shopping, _ = await _category("consumer_spending", "shopping")

    await _categorize(token, txn_id, {"category_id": eating, "promote_to_rule": True})
    await _categorize(token, txn_id, {"category_id": shopping, "promote_to_rule": True})

    assert await _rules_count(uid) == 1  # one row, not stacked
    db_rule = await _rule_row(uid, "merchant_exact", "wolt")
    assert db_rule["category_id"] == shopping  # updated to the newest correction


@pytest.mark.asyncio
async def test_promote_requires_merchant(principal, migrated: None) -> None:
    token, uid = principal
    await _ensure_user(uid)
    # amount-only txn (merchant_id null)
    txn_id = (await _quick_add(token, {"amount": "5.00"})).json()["transaction"]["id"]
    cat, _ = await _category("consumer_spending")
    resp = await _categorize(token, txn_id, {"category_id": cat, "promote_to_rule": True})
    assert resp.status_code == 422 and _field_code(resp) == "unknown_merchant"
    assert await _rules_count(uid) == 0


@pytest.mark.asyncio
async def test_generic_contains_fragment_rejected(principal, migrated: None) -> None:
    token, uid = principal
    await _ensure_user(uid)
    # merchant "Cafe" -> normalized "cafe" -> generic fragment for a contains rule.
    txn_id = (await _quick_add(token, {"amount": "5.00", "merchant_input": "Cafe"})).json()[
        "transaction"
    ]["id"]
    cat, _ = await _category("consumer_spending")
    resp = await _categorize(
        token, txn_id,
        {"category_id": cat, "promote_to_rule": True, "match_type": "merchant_contains"},
    )
    assert resp.status_code == 422 and _field_code(resp) == "generic_fragment"
    assert await _rules_count(uid) == 0


# --------------------------------------------------------------------------- #
# apply_to_existing.
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_apply_to_existing_default_false(principal, migrated: None) -> None:
    token, uid = principal
    await _ensure_user(uid)
    # 3 prior Wolt txns + 1 target, all the same merchant.
    p1, _ = await _add_wolt(token)
    p2, _ = await _add_wolt(token)
    p3, _ = await _add_wolt(token)
    target, _ = await _add_wolt(token)
    cat, _ = await _category("consumer_spending", "eating_out")

    body = (await _categorize(token, target, {"category_id": cat, "promote_to_rule": True})).json()
    assert body["applied_to_existing_count"] == 0
    # Priors remain uncategorized (going-forward only).
    for p in (p1, p2, p3):
        assert (await _raw_txn(p))["category_id"] is None
    assert (await _raw_txn(target))["category_id"] == cat


@pytest.mark.asyncio
async def test_apply_to_existing_true_bulk_and_principal_scoped(principal, migrated: None) -> None:
    token, uid = principal
    await _ensure_user(uid)
    p1, my_merchant = await _add_wolt(token)
    p2, _ = await _add_wolt(token)
    target, _ = await _add_wolt(token)
    cat, _ = await _category("consumer_spending", "eating_out")

    # Another user's "Wolt" must never be touched (QA-06-08).
    other = str(uuid.uuid4())
    await _ensure_user(other)
    other_merchant = await _seed_merchant(other, "wolt", "Wolt")
    other_txn = await _seed_txn(other, other_merchant, -999)

    body = (
        await _categorize(
            token, target,
            {"category_id": cat, "promote_to_rule": True, "apply_to_existing": True},
        )
    ).json()
    assert body["applied_to_existing_count"] == 2  # p1, p2 (target handled separately)
    assert (await _raw_txn(p1))["category_id"] == cat
    assert (await _raw_txn(p2))["category_id"] == cat
    assert (await _raw_txn(target))["category_id"] == cat
    assert (await _raw_txn(other_txn))["category_id"] is None  # other user untouched


# --------------------------------------------------------------------------- #
# Ownership / privacy.
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_forged_user_id_ignored(principal, migrated: None) -> None:
    token, uid = principal
    await _ensure_user(uid)
    txn_id, _ = await _add_wolt(token)
    cat, _ = await _category("consumer_spending")
    resp = await _categorize(token, txn_id, {"category_id": cat, "user_id": str(uuid.uuid4())})
    assert resp.status_code == 200
    assert (await _raw_txn(txn_id))["category_id"] == cat  # saved under the principal


@pytest.mark.asyncio
async def test_no_pii_in_logs(principal, migrated: None) -> None:
    token, uid = principal
    await _ensure_user(uid)
    secret = "CatSecretMerchZZ"
    txn_id = (await _quick_add(token, {"amount": "5.00", "merchant_input": secret})).json()[
        "transaction"
    ]["id"]
    cat, cat_key = await _category("consumer_spending", "eating_out")

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
        resp = await _categorize(token, txn_id, {"category_id": cat, "promote_to_rule": True})
    finally:
        logger.removeHandler(handler)
        logger.setLevel(prev)

    assert resp.status_code == 200
    assert records
    for r in records:
        rendered = r.getMessage() + " " + " ".join(str(v) for v in (r.args or ()))
        assert secret not in rendered             # merchant text / match_value
        assert secret.casefold() not in rendered  # normalized key
        assert cat_key not in rendered            # category text
