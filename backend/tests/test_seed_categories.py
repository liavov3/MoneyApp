"""Seed verification — QA-13-01..05 (requires DB + migrations).

Also covers the in-process seed-data invariants without a DB.
"""

from __future__ import annotations

import pytest
from sqlalchemy import text

from app.seed_data import SEED_CATEGORIES

CANONICAL_KEYS = {
    "groceries", "eating_out", "transport", "car_fuel", "shopping", "entertainment",
    "subscriptions", "health", "education", "home", "gifts", "travel", "personal_care",
    "other_spending",
    "income", "incoming_transfer", "outgoing_transfer", "credit_card_settlement",
    "loan_payment", "interest_bank_fee", "cash_deposit_withdrawal", "other_bank_movement",
}


def test_seed_data_is_canonical_22() -> None:
    """No DB needed: the seed list itself is exactly the 22 canonical rows."""
    keys = {c.key for c in SEED_CATEGORIES}
    assert keys == CANONICAL_KEYS
    assert "bank_fee_interest" not in keys
    assert "cash_movement" not in keys
    consumer = [c for c in SEED_CATEGORIES if c.layer == "consumer_spending"]
    bank = [c for c in SEED_CATEGORIES if c.layer == "bank_movement"]
    assert len(consumer) == 14
    assert len(bank) == 8
    assert all(c.included_in_actual_spending and not c.included_in_cash_flow for c in consumer)
    assert all(not c.included_in_actual_spending and c.included_in_cash_flow for c in bank)


@pytest.mark.asyncio
async def test_db_exactly_22_seeded(engine) -> None:
    """QA-13-01: exactly 22 system categories; all is_system=true, user_id NULL."""
    async with engine.connect() as conn:
        count = (
            await conn.execute(text("SELECT count(*) FROM categories WHERE is_system = true"))
        ).scalar_one()
        assert count == 22
        nulls = (
            await conn.execute(
                text("SELECT count(*) FROM categories WHERE is_system = true AND user_id IS NOT NULL")
            )
        ).scalar_one()
        assert nulls == 0


@pytest.mark.asyncio
async def test_db_consumer_and_bank_flags(engine) -> None:
    """QA-13-02 / QA-13-03: consumer and bank flags correct."""
    async with engine.connect() as conn:
        consumer = (
            await conn.execute(
                text(
                    "SELECT count(*) FROM categories WHERE layer='consumer_spending' "
                    "AND included_in_actual_spending=true AND included_in_cash_flow=false"
                )
            )
        ).scalar_one()
        assert consumer == 14
        bank = (
            await conn.execute(
                text(
                    "SELECT count(*) FROM categories WHERE layer='bank_movement' "
                    "AND included_in_actual_spending=false AND included_in_cash_flow=true"
                )
            )
        ).scalar_one()
        assert bank == 8


@pytest.mark.asyncio
async def test_db_canonical_keys_present(engine) -> None:
    """QA-13-04: canonical keys incl. interest_bank_fee / cash_deposit_withdrawal."""
    async with engine.connect() as conn:
        rows = (
            await conn.execute(text("SELECT key FROM categories WHERE is_system = true"))
        ).scalars().all()
        keys = set(rows)
        assert keys == CANONICAL_KEYS
        assert "interest_bank_fee" in keys
        assert "cash_deposit_withdrawal" in keys


@pytest.mark.asyncio
async def test_db_committed_projection_always_false(engine) -> None:
    """QA-13-05: included_in_committed_projection is false for every row."""
    async with engine.connect() as conn:
        bad = (
            await conn.execute(
                text("SELECT count(*) FROM categories WHERE included_in_committed_projection = true")
            )
        ).scalar_one()
        assert bad == 0
