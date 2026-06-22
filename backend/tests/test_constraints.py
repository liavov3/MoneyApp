"""Database constraint enforcement tests (requires DB + migrations).

Each test exercises a frozen schema constraint and maps to QA IDs:
- amount_minor <> 0 rejected ............................ QA-02-06 basis
- partial-unique dedup_hash behavior ................... schema §15 case 11
- UNIQUE(user_id, normalized_merchant_name) ............ QA-03-13 basis
- UNIQUE(user_id, normalized_alias_key) ................ QA-04-03 basis
- UNIQUE(user_id, match_type, match_value) ............. QA-05-02 basis
- categories included_in_committed_projection=true ..... QA-13-05 basis
- categories layer CHECK ............................... schema §13

These run against the real PostgreSQL constraints, not Python validation.
"""

from __future__ import annotations

import uuid

import pytest
from sqlalchemy import text
from sqlalchemy.exc import IntegrityError

pytestmark = pytest.mark.asyncio


async def _make_user(conn) -> str:
    uid = str(uuid.uuid4())
    await conn.execute(
        text(
            "INSERT INTO users (id, base_currency) VALUES (:id, 'ILS')"
        ),
        {"id": uid},
    )
    return uid


async def _make_merchant(conn, user_id: str, normalized: str) -> str:
    mid = str(uuid.uuid4())
    await conn.execute(
        text(
            "INSERT INTO merchants (id, user_id, normalized_merchant_name, display_name) "
            "VALUES (:id, :u, :n, :d)"
        ),
        {"id": mid, "u": user_id, "n": normalized, "d": normalized},
    )
    return mid


async def _any_consumer_category_id(conn) -> str:
    return (
        await conn.execute(
            text("SELECT id FROM categories WHERE key = 'eating_out'")
        )
    ).scalar_one()


async def test_amount_minor_zero_rejected(engine) -> None:
    """QA-02-06 basis: CHECK (amount_minor <> 0) rejects a zero amount."""
    async with engine.begin() as conn:
        uid = await _make_user(conn)
    with pytest.raises(IntegrityError):
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO transactions (user_id, amount_minor, currency, "
                    "transaction_type, source) VALUES (:u, 0, 'ILS', 'expense', 'manual')"
                ),
                {"u": uid},
            )


async def test_dedup_hash_partial_unique(engine) -> None:
    """schema §15 case 11: duplicate non-null dedup_hash rejected; nulls allowed."""
    async with engine.begin() as conn:
        uid = await _make_user(conn)
        # Two NULL dedup_hash manual rows are both accepted.
        for _ in range(2):
            await conn.execute(
                text(
                    "INSERT INTO transactions (user_id, amount_minor, source) "
                    "VALUES (:u, -100, 'manual')"
                ),
                {"u": uid},
            )
        # An import row with a dedup_hash is accepted.
        await conn.execute(
            text(
                "INSERT INTO transactions (user_id, amount_minor, source, dedup_hash) "
                "VALUES (:u, -200, 'bank_import', 'h1')"
            ),
            {"u": uid},
        )
    # A second import row with the SAME dedup_hash for the same user is rejected.
    with pytest.raises(IntegrityError):
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO transactions (user_id, amount_minor, source, dedup_hash) "
                    "VALUES (:u, -300, 'bank_import', 'h1')"
                ),
                {"u": uid},
            )


async def test_import_requires_dedup_hash(engine) -> None:
    """CHECK (source='manual' OR dedup_hash IS NOT NULL): import without hash rejected."""
    async with engine.begin() as conn:
        uid = await _make_user(conn)
    with pytest.raises(IntegrityError):
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO transactions (user_id, amount_minor, source) "
                    "VALUES (:u, -100, 'bank_import')"
                ),
                {"u": uid},
            )


async def test_duplicate_merchant_rejected(engine) -> None:
    """QA-03-13 basis: UNIQUE(user_id, normalized_merchant_name)."""
    async with engine.begin() as conn:
        uid = await _make_user(conn)
        await _make_merchant(conn, uid, "aroma")
    with pytest.raises(IntegrityError):
        async with engine.begin() as conn:
            await _make_merchant(conn, uid, "aroma")


async def test_duplicate_alias_key_rejected(engine) -> None:
    """QA-04-03 basis: UNIQUE(user_id, normalized_alias_key)."""
    async with engine.begin() as conn:
        uid = await _make_user(conn)
        mid = await _make_merchant(conn, uid, "golda")
        await conn.execute(
            text(
                "INSERT INTO merchant_aliases (user_id, merchant_id, alias_text, "
                "normalized_alias_key, source) VALUES (:u, :m, 'גולדה', 'golda_he', 'user_confirmed')"
            ),
            {"u": uid, "m": mid},
        )
    with pytest.raises(IntegrityError):
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO merchant_aliases (user_id, merchant_id, alias_text, "
                    "normalized_alias_key, source) VALUES (:u, :m, 'x', 'golda_he', 'user_confirmed')"
                ),
                {"u": uid, "m": mid},
            )


async def test_duplicate_rule_key_rejected(engine) -> None:
    """QA-05-02 basis: UNIQUE(user_id, match_type, match_value) — update-not-stack."""
    async with engine.begin() as conn:
        uid = await _make_user(conn)
        cat = await _any_consumer_category_id(conn)
        await conn.execute(
            text(
                "INSERT INTO category_rules (user_id, match_type, match_value, category_id) "
                "VALUES (:u, 'merchant_exact', 'wolt', :c)"
            ),
            {"u": uid, "c": cat},
        )
    with pytest.raises(IntegrityError):
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO category_rules (user_id, match_type, match_value, category_id) "
                    "VALUES (:u, 'merchant_exact', 'wolt', :c)"
                ),
                {"u": uid, "c": cat},
            )


async def test_category_projection_true_rejected(engine) -> None:
    """QA-13-05 basis: CHECK (included_in_committed_projection = false)."""
    async with engine.begin() as conn:
        uid = await _make_user(conn)
    with pytest.raises(IntegrityError):
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO categories (user_id, label_en, layer, "
                    "included_in_actual_spending, included_in_committed_projection, "
                    "included_in_cash_flow, is_system) "
                    "VALUES (:u, 'X', 'consumer_spending', true, true, false, false)"
                ),
                {"u": uid},
            )


async def test_category_bad_layer_rejected(engine) -> None:
    """schema §13: CHECK layer IN ('consumer_spending','bank_movement')."""
    async with engine.begin() as conn:
        uid = await _make_user(conn)
    with pytest.raises(IntegrityError):
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO categories (user_id, label_en, layer, "
                    "included_in_actual_spending, included_in_cash_flow, is_system) "
                    "VALUES (:u, 'X', 'not_a_layer', true, false, false)"
                ),
                {"u": uid},
            )


async def test_category_system_owner_check(engine) -> None:
    """schema §13: system rows must have user_id NULL; non-system must have a user."""
    async with engine.begin() as conn:
        uid = await _make_user(conn)
    # is_system=true with a user_id set -> rejected.
    with pytest.raises(IntegrityError):
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO categories (user_id, label_en, layer, "
                    "included_in_actual_spending, included_in_cash_flow, is_system) "
                    "VALUES (:u, 'X', 'consumer_spending', true, false, true)"
                ),
                {"u": uid},
            )


async def test_recurring_amount_zero_rejected(engine) -> None:
    """schema §13: recurring_expense_templates.amount_minor <> 0."""
    async with engine.begin() as conn:
        uid = await _make_user(conn)
        cat = await _any_consumer_category_id(conn)
    with pytest.raises(IntegrityError):
        async with engine.begin() as conn:
            await conn.execute(
                text(
                    "INSERT INTO recurring_expense_templates "
                    "(user_id, name, amount_minor, category_id, cadence, next_expected_date) "
                    "VALUES (:u, 'Gym', 0, :c, 'monthly', CURRENT_DATE)"
                ),
                {"u": uid, "c": cat},
            )


async def test_amount_only_transaction_succeeds(engine) -> None:
    """schema §15 case 1: amount-only manual expense (null merchant/category) persists."""
    async with engine.begin() as conn:
        uid = await _make_user(conn)
        await conn.execute(
            text(
                "INSERT INTO transactions (user_id, amount_minor, transaction_type, source) "
                "VALUES (:u, -3300, 'expense', 'manual')"
            ),
            {"u": uid},
        )
        row = (
            await conn.execute(
                text(
                    "SELECT amount_minor, merchant_id, category_id, occurred_on, currency "
                    "FROM transactions WHERE user_id = :u"
                ),
                {"u": uid},
            )
        ).one()
        assert row.amount_minor == -3300
        assert row.merchant_id is None
        assert row.category_id is None
        assert row.occurred_on is not None  # defaulted to CURRENT_DATE
        assert row.currency == "ILS"
