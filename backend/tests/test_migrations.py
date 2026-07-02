"""Migrations apply cleanly and the expected tables/extensions exist (requires DB)."""

from __future__ import annotations

import pytest
from sqlalchemy import text

pytestmark = pytest.mark.asyncio

EXPECTED_TABLES = {
    "users",
    "transactions",
    "merchants",
    "merchant_aliases",
    "categories",
    "category_rules",
    "recurring_expense_templates",
    "accounts",
    "import_batches",
    "alembic_version",
}


async def test_all_tables_created(engine) -> None:
    async with engine.connect() as conn:
        rows = (
            await conn.execute(
                text(
                    "SELECT table_name FROM information_schema.tables "
                    "WHERE table_schema = 'public'"
                )
            )
        ).scalars().all()
    present = set(rows)
    assert EXPECTED_TABLES.issubset(present), f"missing: {EXPECTED_TABLES - present}"


async def test_pgvector_installed_zero_vector_tables(engine) -> None:
    """pgvector extension installed, but ZERO vector columns/tables in v0.0.1."""
    async with engine.connect() as conn:
        has_vector = (
            await conn.execute(
                text("SELECT count(*) FROM pg_extension WHERE extname = 'vector'")
            )
        ).scalar_one()
        assert has_vector == 1
        vector_cols = (
            await conn.execute(
                text(
                    "SELECT count(*) FROM information_schema.columns "
                    "WHERE udt_name = 'vector'"
                )
            )
        ).scalar_one()
        assert vector_cols == 0


async def test_migration_version_at_head(engine) -> None:
    async with engine.connect() as conn:
        version = (
            await conn.execute(text("SELECT version_num FROM alembic_version"))
        ).scalar_one()
        assert version == "0005_monthly_goals_types_scopes"


async def test_dev_user_seeded(engine) -> None:
    """0003 seeds exactly the single dev principal (settings.dev_user_id)."""
    from app.config import get_settings

    dev_user_id = get_settings().dev_user_id
    async with engine.connect() as conn:
        count = (
            await conn.execute(
                text("SELECT count(*) FROM users WHERE id = :uid"),
                {"uid": dev_user_id},
            )
        ).scalar_one()
        assert count == 1
