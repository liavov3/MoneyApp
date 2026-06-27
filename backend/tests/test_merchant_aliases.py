"""POST /api/v1/merchants/{id}/aliases — user-confirmed alias slice (§11).

The only path that links a variant/cross-script form to an existing merchant.
Covers:
- missing/invalid token -> 401; malformed/missing/non-owned {id} -> 404 (not 403)
- empty alias_text -> 422; missing alias_text -> 422
- valid create -> 201 user_confirmed alias; alias_text/key never echoed
- re-confirm same variant -> idempotent (one row)
- key already resolving to a DIFFERENT merchant -> 409 conflict
- absorb_merchant_id: re-points the duplicate's transactions and deletes it,
  returning the count; absorb self / unknown absorb -> 422
- forged user_id ignored; alias_text never appears in logs

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
    token = "test-alias-token-6h"
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


async def _merchant_exists(mid: str) -> bool:
    async with get_sessionmaker()() as s:
        return (
            await s.execute(
                text("SELECT count(*) FROM merchants WHERE id = CAST(:id AS uuid)"),
                {"id": mid},
            )
        ).scalar_one() == 1


async def _txn_merchant(txn_id: str) -> str | None:
    async with get_sessionmaker()() as s:
        return (
            await s.execute(
                text(
                    "SELECT merchant_id::text AS m FROM transactions "
                    "WHERE id = CAST(:id AS uuid)"
                ),
                {"id": txn_id},
            )
        ).scalar_one()


async def _alias_count(uid: str) -> int:
    async with get_sessionmaker()() as s:
        return (
            await s.execute(
                text("SELECT count(*) FROM merchant_aliases WHERE user_id = :u"),
                {"u": uid},
            )
        ).scalar_one()


async def _alias_key_exists(uid: str, nk: str) -> bool:
    async with get_sessionmaker()() as s:
        return (
            await s.execute(
                text(
                    "SELECT count(*) FROM merchant_aliases "
                    "WHERE user_id = :u AND normalized_alias_key = :nk"
                ),
                {"u": uid, "nk": nk},
            )
        ).scalar_one() == 1


def _client(app):
    return AsyncClient(transport=ASGITransport(app=app), base_url="http://test")


async def _quick_add(token: str, payload: dict):
    app = create_app()
    async with _client(app) as c:
        return await c.post(
            "/api/v1/transactions/quick-add", json=payload,
            headers={"Authorization": f"Bearer {token}"},
        )


async def _post_alias(token: str | None, merchant_id: str, body: dict | None):
    app = create_app()
    headers = {}
    if token is not None:
        headers["Authorization"] = f"Bearer {token}"
    async with _client(app) as c:
        return await c.post(
            f"/api/v1/merchants/{merchant_id}/aliases", json=body, headers=headers
        )


async def _new_merchant(token: str, name: str) -> str:
    return (await _quick_add(token, {"amount": "5.00", "merchant_input": name})).json()[
        "transaction"
    ]["merchant_id"]


def _assert_401(resp) -> None:
    assert resp.status_code == 401
    assert resp.json()["error"]["code"] == "unauthorized"


def _assert_404(resp) -> None:
    assert resp.status_code == 404
    assert resp.json()["error"]["code"] == "not_found"


# --------------------------------------------------------------------------- #
# Auth / not-found — minimal DB.
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_missing_token_returns_401(principal) -> None:
    _assert_401(await _post_alias(None, str(uuid.uuid4()), {"alias_text": "x"}))


@pytest.mark.asyncio
async def test_invalid_token_returns_401(principal) -> None:
    _assert_401(await _post_alias("wrong", str(uuid.uuid4()), {"alias_text": "x"}))


@pytest.mark.asyncio
async def test_malformed_merchant_id_returns_404(principal) -> None:
    token, _ = principal
    _assert_404(await _post_alias(token, "not-a-uuid", {"alias_text": "x"}))


@pytest.mark.asyncio
async def test_missing_merchant_returns_404(principal, migrated: None) -> None:
    token, uid = principal
    await _ensure_user(uid)
    _assert_404(await _post_alias(token, str(uuid.uuid4()), {"alias_text": "x"}))


@pytest.mark.asyncio
async def test_other_users_merchant_returns_404(principal, migrated: None) -> None:
    token, uid = principal
    await _ensure_user(uid)
    other = str(uuid.uuid4())
    await _ensure_user(other)
    other_merchant = await _seed_merchant(other, "golda", "Golda")
    _assert_404(await _post_alias(token, other_merchant, {"alias_text": "גולדה"}))
    assert await _alias_count(uid) == 0
    assert await _alias_count(other) == 0  # nothing created on the other user either


# --------------------------------------------------------------------------- #
# Validation.
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_missing_alias_text_returns_422(principal, migrated: None) -> None:
    token, uid = principal
    await _ensure_user(uid)
    mid = await _new_merchant(token, "Golda")
    assert (await _post_alias(token, mid, {})).status_code == 422  # required field


@pytest.mark.asyncio
async def test_blank_alias_text_returns_422(principal, migrated: None) -> None:
    token, uid = principal
    await _ensure_user(uid)
    mid = await _new_merchant(token, "Golda")
    resp = await _post_alias(token, mid, {"alias_text": "   "})
    assert resp.status_code == 422
    assert resp.json()["error"]["field_errors"][0]["code"] == "empty_alias"


# --------------------------------------------------------------------------- #
# Create / idempotency / conflict.
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_create_alias_returns_201_and_hides_text(principal, migrated: None) -> None:
    token, uid = principal
    await _ensure_user(uid)
    mid = await _new_merchant(token, "Golda")

    resp = await _post_alias(token, mid, {"alias_text": "גולדה"})
    assert resp.status_code == 201
    body = resp.json()
    alias = body["alias"]
    assert alias["merchant_id"] == mid
    assert alias["source"] == "user_confirmed"
    assert alias["confidence"] == "user_confirmed"
    assert alias["created_at"].endswith("Z")
    assert alias["last_seen_at"] is None
    # alias text / normalized key are NOT echoed (sensitive).
    assert "alias_text" not in alias and "normalized_alias_key" not in alias
    # absorb fields absent when nothing absorbed.
    assert "absorbed_merchant_id" not in body
    assert "repointed_transaction_count" not in body
    # DB: the alias key exists for this user.
    assert await _alias_key_exists(uid, "גולדה")


@pytest.mark.asyncio
async def test_reconfirm_same_alias_is_idempotent(principal, migrated: None) -> None:
    token, uid = principal
    await _ensure_user(uid)
    mid = await _new_merchant(token, "Golda")

    first = await _post_alias(token, mid, {"alias_text": "גולדה"})
    second = await _post_alias(token, mid, {"alias_text": "גולדה"})
    assert first.status_code == 201 and second.status_code == 201
    assert first.json()["alias"]["id"] == second.json()["alias"]["id"]  # same row
    assert await _alias_count(uid) == 1  # not stacked


@pytest.mark.asyncio
async def test_key_resolving_to_other_merchant_returns_409(principal, migrated: None) -> None:
    token, uid = principal
    await _ensure_user(uid)
    golda = await _new_merchant(token, "Golda")
    wolt = await _new_merchant(token, "Wolt")

    assert (await _post_alias(token, golda, {"alias_text": "Variant"})).status_code == 201
    # Same key "variant" cannot also resolve to Wolt.
    conflict = await _post_alias(token, wolt, {"alias_text": "Variant"})
    assert conflict.status_code == 409
    assert conflict.json()["error"]["code"] == "conflict"
    assert await _alias_count(uid) == 1  # the second was rejected


# --------------------------------------------------------------------------- #
# Absorb a duplicate merchant.
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_absorb_repoints_transactions_and_deletes_merchant(
    principal, migrated: None
) -> None:
    token, uid = principal
    await _ensure_user(uid)
    golda = await _new_merchant(token, "Golda")  # canonical
    # Two transactions on a separate cross-script duplicate "גולדה".
    t1 = (await _quick_add(token, {"amount": "5.00", "merchant_input": "גולדה"})).json()[
        "transaction"
    ]
    dup = t1["merchant_id"]
    t2 = (await _quick_add(token, {"amount": "6.00", "merchant_input": "גולדה"})).json()[
        "transaction"
    ]
    assert t2["merchant_id"] == dup  # reused the same duplicate

    resp = await _post_alias(
        token, golda, {"alias_text": "גולדה", "absorb_merchant_id": dup}
    )
    assert resp.status_code == 201
    body = resp.json()
    assert body["absorbed_merchant_id"] == dup
    assert body["repointed_transaction_count"] == 2
    # The duplicate is gone; its transactions now point to the canonical merchant.
    assert not await _merchant_exists(dup)
    assert await _txn_merchant(t1["id"]) == golda
    assert await _txn_merchant(t2["id"]) == golda


@pytest.mark.asyncio
async def test_absorb_self_returns_422(principal, migrated: None) -> None:
    token, uid = principal
    await _ensure_user(uid)
    mid = await _new_merchant(token, "Golda")
    resp = await _post_alias(token, mid, {"alias_text": "גולדה", "absorb_merchant_id": mid})
    assert resp.status_code == 422
    assert resp.json()["error"]["field_errors"][0]["code"] == "invalid_absorb"


@pytest.mark.asyncio
async def test_absorb_unknown_merchant_returns_422(principal, migrated: None) -> None:
    token, uid = principal
    await _ensure_user(uid)
    mid = await _new_merchant(token, "Golda")
    resp = await _post_alias(
        token, mid, {"alias_text": "גולדה", "absorb_merchant_id": str(uuid.uuid4())}
    )
    assert resp.status_code == 422
    assert resp.json()["error"]["field_errors"][0]["code"] == "unknown_merchant"


# --------------------------------------------------------------------------- #
# Ownership / privacy.
# --------------------------------------------------------------------------- #
@pytest.mark.asyncio
async def test_forged_user_id_ignored(principal, migrated: None) -> None:
    token, uid = principal
    await _ensure_user(uid)
    other = str(uuid.uuid4())
    await _ensure_user(other)
    mid = await _new_merchant(token, "Golda")

    resp = await _post_alias(
        token, mid, {"alias_text": "גולדה", "user_id": other}
    )
    assert resp.status_code == 201
    # The alias belongs to the principal, not the forged user.
    assert await _alias_count(uid) == 1
    assert await _alias_count(other) == 0


@pytest.mark.asyncio
async def test_no_pii_in_logs(principal, migrated: None) -> None:
    token, uid = principal
    await _ensure_user(uid)
    mid = await _new_merchant(token, "Golda")
    secret = "AliasSecretVariantQQ"

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
        resp = await _post_alias(token, mid, {"alias_text": secret})
    finally:
        logger.removeHandler(handler)
        logger.setLevel(prev)

    assert resp.status_code == 201
    assert records
    for r in records:
        rendered = r.getMessage() + " " + " ".join(str(v) for v in (r.args or ()))
        assert secret not in rendered             # alias text
        assert secret.casefold() not in rendered  # normalized key
