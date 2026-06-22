"""Initial schema: 7 active tables + deferred FK targets, all constraints/indexes.

Faithful to docs/DATABASE_SCHEMA_V0_0_1.md. Installs pgcrypto (for
gen_random_uuid) and pgvector (extension only — ZERO vector tables/rows in
v0.0.1).

Revision ID: 0001_initial_schema
Revises:
Create Date: 2026-06-14
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0001_initial_schema"
down_revision: Union[str, None] = None
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

UUID = postgresql.UUID(as_uuid=False)
TS = postgresql.TIMESTAMP(timezone=True)


def upgrade() -> None:
    # Extensions: pgcrypto (gen_random_uuid), pgvector (installed, unused).
    op.execute("CREATE EXTENSION IF NOT EXISTS pgcrypto")
    op.execute("CREATE EXTENSION IF NOT EXISTS vector")

    # ----- users -----------------------------------------------------------
    op.create_table(
        "users",
        sa.Column("id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("email", sa.Text(), nullable=True),
        sa.Column("credential_ref", sa.Text(), nullable=True),
        sa.Column("base_currency", sa.Text(), nullable=False, server_default=sa.text("'ILS'")),
        sa.Column("locale", sa.Text(), nullable=True, server_default=sa.text("'en'")),
        sa.Column("settings", postgresql.JSONB(), nullable=True, server_default=sa.text("'{}'::jsonb")),
        sa.Column("created_at", TS, nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", TS, nullable=False, server_default=sa.text("now()")),
        sa.CheckConstraint("char_length(base_currency) = 3", name="ck_users_base_currency_len"),
    )
    op.create_index(
        "uq_users_email_lower",
        "users",
        [sa.text("lower(email)")],
        unique=True,
        postgresql_where=sa.text("email IS NOT NULL"),
    )

    # ----- accounts (deferred FK target, empty) ----------------------------
    op.create_table(
        "accounts",
        sa.Column("id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID, nullable=False),
        sa.Column("created_at", TS, nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", TS, nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )

    # ----- import_batches (deferred FK target, empty) ----------------------
    op.create_table(
        "import_batches",
        sa.Column("id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID, nullable=False),
        sa.Column("created_at", TS, nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", TS, nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
    )

    # ----- categories ------------------------------------------------------
    op.create_table(
        "categories",
        sa.Column("id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID, nullable=True),
        sa.Column("key", sa.Text(), nullable=True),
        sa.Column("label_en", sa.Text(), nullable=False),
        sa.Column("label_he", sa.Text(), nullable=True),
        sa.Column("layer", sa.Text(), nullable=False),
        sa.Column("included_in_actual_spending", sa.Boolean(), nullable=False),
        sa.Column(
            "included_in_committed_projection",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("included_in_cash_flow", sa.Boolean(), nullable=False),
        sa.Column("is_system", sa.Boolean(), nullable=False, server_default=sa.text("false")),
        sa.Column("parent_id", UUID, nullable=True),
        sa.Column("created_at", TS, nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", TS, nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["parent_id"], ["categories.id"]),
        sa.CheckConstraint(
            "layer IN ('consumer_spending','bank_movement')", name="ck_categories_layer"
        ),
        sa.CheckConstraint(
            "included_in_committed_projection = false", name="ck_categories_no_projection"
        ),
        sa.CheckConstraint(
            "(is_system AND user_id IS NULL) OR (NOT is_system AND user_id IS NOT NULL)",
            name="ck_categories_system_owner",
        ),
    )
    op.create_index(
        "uq_categories_key",
        "categories",
        ["key"],
        unique=True,
        postgresql_where=sa.text("key IS NOT NULL"),
    )
    op.create_index("ix_categories_user_id", "categories", ["user_id"])
    op.create_index("ix_categories_layer", "categories", ["layer"])

    # ----- merchants -------------------------------------------------------
    op.create_table(
        "merchants",
        sa.Column("id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID, nullable=False),
        sa.Column("normalized_merchant_name", sa.Text(), nullable=False),
        sa.Column("display_name", sa.Text(), nullable=False),
        sa.Column("default_category_id", UUID, nullable=True),
        sa.Column("created_at", TS, nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", TS, nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["default_category_id"], ["categories.id"], ondelete="SET NULL"
        ),
        sa.UniqueConstraint(
            "user_id", "normalized_merchant_name", name="uq_merchants_user_normalized"
        ),
        sa.UniqueConstraint("id", "user_id", name="uq_merchants_id_user"),
    )
    op.create_index(
        "ix_merchants_user_updated_at",
        "merchants",
        ["user_id", sa.text("updated_at DESC")],
    )

    # ----- merchant_aliases ------------------------------------------------
    op.create_table(
        "merchant_aliases",
        sa.Column("id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID, nullable=False),
        sa.Column("merchant_id", UUID, nullable=False),
        sa.Column("alias_text", sa.Text(), nullable=False),
        sa.Column("normalized_alias_key", sa.Text(), nullable=False),
        sa.Column(
            "source", sa.Text(), nullable=False, server_default=sa.text("'user_confirmed'")
        ),
        sa.Column("confidence", sa.Text(), nullable=True),
        sa.Column("created_at", TS, nullable=False, server_default=sa.text("now()")),
        sa.Column("last_seen_at", TS, nullable=True),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["merchant_id", "user_id"],
            ["merchants.id", "merchants.user_id"],
            ondelete="CASCADE",
            name="fk_merchant_aliases_merchant_user",
        ),
        sa.UniqueConstraint(
            "user_id", "normalized_alias_key", name="uq_merchant_aliases_user_key"
        ),
        sa.CheckConstraint(
            "source IN ('user_confirmed','import_parsed','system_suggested')",
            name="ck_merchant_aliases_source",
        ),
    )
    op.create_index("ix_merchant_aliases_merchant_id", "merchant_aliases", ["merchant_id"])
    op.create_index(
        "ix_merchant_aliases_user_last_seen",
        "merchant_aliases",
        ["user_id", sa.text("last_seen_at DESC")],
    )

    # ----- category_rules --------------------------------------------------
    op.create_table(
        "category_rules",
        sa.Column("id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID, nullable=False),
        sa.Column("match_type", sa.Text(), nullable=False),
        sa.Column("match_value", sa.Text(), nullable=False),
        sa.Column("category_id", UUID, nullable=False),
        sa.Column("priority", sa.SmallInteger(), nullable=False, server_default=sa.text("100")),
        sa.Column(
            "source", sa.Text(), nullable=False, server_default=sa.text("'user_correction'")
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("created_at", TS, nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", TS, nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["category_id"], ["categories.id"], ondelete="CASCADE"),
        sa.CheckConstraint(
            "match_type IN ('merchant_exact','merchant_contains')",
            name="ck_category_rules_match_type",
        ),
        sa.CheckConstraint(
            "source IN ('system','user_correction')", name="ck_category_rules_source"
        ),
        sa.UniqueConstraint(
            "user_id", "match_type", "match_value", name="uq_category_rules_user_match"
        ),
    )
    op.create_index("ix_category_rules_user_priority", "category_rules", ["user_id", "priority"])

    # ----- transactions ----------------------------------------------------
    op.create_table(
        "transactions",
        sa.Column("id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID, nullable=False),
        sa.Column("amount_minor", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.Text(), nullable=False, server_default=sa.text("'ILS'")),
        sa.Column(
            "transaction_type",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'expense'"),
        ),
        sa.Column("source", sa.Text(), nullable=False, server_default=sa.text("'manual'")),
        sa.Column("merchant_id", UUID, nullable=True),
        sa.Column("category_id", UUID, nullable=True),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column(
            "occurred_on", sa.Date(), nullable=False, server_default=sa.text("CURRENT_DATE")
        ),
        sa.Column("raw_merchant_input", sa.Text(), nullable=True),
        sa.Column("raw_description", sa.Text(), nullable=True),
        sa.Column("value_date", sa.Date(), nullable=True),
        sa.Column("reference", sa.Text(), nullable=True),
        sa.Column("operation_type", sa.Text(), nullable=True),
        sa.Column(
            "is_card_settlement",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("false"),
        ),
        sa.Column("account_id", UUID, nullable=True),
        sa.Column("import_batch_id", UUID, nullable=True),
        sa.Column("dedup_hash", sa.Text(), nullable=True),
        sa.Column("created_at", TS, nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", TS, nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(
            ["merchant_id", "user_id"],
            ["merchants.id", "merchants.user_id"],
            ondelete="SET NULL",
            name="fk_transactions_merchant_user",
        ),
        sa.ForeignKeyConstraint(["category_id"], ["categories.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(["account_id"], ["accounts.id"], ondelete="SET NULL"),
        sa.ForeignKeyConstraint(
            ["import_batch_id"], ["import_batches.id"], ondelete="SET NULL"
        ),
        sa.UniqueConstraint("id", "user_id", name="uq_transactions_id_user"),
        sa.CheckConstraint("amount_minor <> 0", name="ck_transactions_amount_nonzero"),
        sa.CheckConstraint("char_length(currency) = 3", name="ck_transactions_currency_len"),
        sa.CheckConstraint(
            "transaction_type IN ('expense','income','refund','adjustment')",
            name="ck_transactions_type",
        ),
        sa.CheckConstraint(
            "source IN ('manual','bank_import','card_import')", name="ck_transactions_source"
        ),
        sa.CheckConstraint(
            "source = 'manual' OR dedup_hash IS NOT NULL", name="ck_transactions_import_dedup"
        ),
    )
    op.create_index(
        "uq_transactions_user_dedup",
        "transactions",
        ["user_id", "dedup_hash"],
        unique=True,
        postgresql_where=sa.text("dedup_hash IS NOT NULL"),
    )
    op.create_index(
        "ix_transactions_user_occurred_on", "transactions", ["user_id", "occurred_on"]
    )
    op.create_index("ix_transactions_user_category", "transactions", ["user_id", "category_id"])
    op.create_index("ix_transactions_user_merchant", "transactions", ["user_id", "merchant_id"])

    # ----- recurring_expense_templates -------------------------------------
    op.create_table(
        "recurring_expense_templates",
        sa.Column("id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")),
        sa.Column("user_id", UUID, nullable=False),
        sa.Column("name", sa.Text(), nullable=False),
        sa.Column("amount_minor", sa.BigInteger(), nullable=False),
        sa.Column("currency", sa.Text(), nullable=False, server_default=sa.text("'ILS'")),
        sa.Column("category_id", UUID, nullable=False),
        sa.Column("merchant_id", UUID, nullable=True),
        sa.Column("cadence", sa.Text(), nullable=False, server_default=sa.text("'monthly'")),
        sa.Column("next_expected_date", sa.Date(), nullable=False),
        sa.Column(
            "counts_in_projection",
            sa.Boolean(),
            nullable=False,
            server_default=sa.text("true"),
        ),
        sa.Column("is_active", sa.Boolean(), nullable=False, server_default=sa.text("true")),
        sa.Column("note", sa.Text(), nullable=True),
        sa.Column("created_at", TS, nullable=False, server_default=sa.text("now()")),
        sa.Column("updated_at", TS, nullable=False, server_default=sa.text("now()")),
        sa.ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        sa.ForeignKeyConstraint(["category_id"], ["categories.id"], ondelete="RESTRICT"),
        sa.ForeignKeyConstraint(
            ["merchant_id", "user_id"],
            ["merchants.id", "merchants.user_id"],
            ondelete="SET NULL",
            name="fk_recurring_templates_merchant_user",
        ),
        sa.CheckConstraint(
            "cadence IN ('weekly','monthly','yearly')", name="ck_recurring_templates_cadence"
        ),
        sa.CheckConstraint("amount_minor <> 0", name="ck_recurring_templates_amount_nonzero"),
        sa.CheckConstraint(
            "char_length(currency) = 3", name="ck_recurring_templates_currency_len"
        ),
    )
    op.create_index(
        "ix_recurring_templates_user_active_next",
        "recurring_expense_templates",
        ["user_id", "is_active", "next_expected_date"],
    )


def downgrade() -> None:
    op.drop_table("recurring_expense_templates")
    op.drop_table("transactions")
    op.drop_table("category_rules")
    op.drop_table("merchant_aliases")
    op.drop_table("merchants")
    op.drop_table("categories")
    op.drop_table("import_batches")
    op.drop_table("accounts")
    op.drop_table("users")
    # Extensions left installed intentionally (harmless; may be shared).
