"""SQLAlchemy ORM models for the v0.0.1 active tables plus deferred FK targets.

This is the single source of metadata that Alembic autogenerate targets. It
encodes EXACTLY the frozen DATABASE_SCHEMA_V0_0_1.md: 7 active tables
(users, transactions, merchants, merchant_aliases, categories, category_rules,
recurring_expense_templates) plus the deferred-but-present FK targets
(accounts, import_batches) so that transactions' nullable account_id /
import_batch_id have real targets.

Conventions (schema §3):
- uuid PKs via gen_random_uuid() (pgcrypto; available in modern PostgreSQL core).
- Money is signed bigint amount_minor + text currency (CHECK len 3).
- Enumerated fields are text + CHECK (not native enums).
- Metadata timestamps are timestamptz default now() (UTC).
- Financial dates are DATE.

Same-user integrity (schema §13): merchants and transactions carry a
UNIQUE (id, user_id) so referencing tables can use composite FKs
(merchant_id, user_id) -> merchants(id, user_id) to make same-user structural.
The category same-user-or-system rule is enforced at the application layer
(system categories have user_id IS NULL and a pure composite FK cannot express
"same user OR null"); plain FKs to categories(id) are declared here.
"""

from __future__ import annotations

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    Date,
    ForeignKey,
    ForeignKeyConstraint,
    Index,
    SmallInteger,
    String,
    Text,
    UniqueConstraint,
    func,
    text,
)
from sqlalchemy.dialects.postgresql import JSONB, TIMESTAMP, UUID
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column

UUID_PK = text("gen_random_uuid()")


class Base(DeclarativeBase):
    pass


def _uuid_pk() -> Mapped[str]:
    return mapped_column(
        UUID(as_uuid=False),
        primary_key=True,
        server_default=UUID_PK,
    )


def _created_at() -> Mapped[object]:
    return mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )


def _updated_at() -> Mapped[object]:
    return mapped_column(
        TIMESTAMP(timezone=True), nullable=False, server_default=func.now()
    )


# ---------------------------------------------------------------------------
# users (schema §3.1)
# ---------------------------------------------------------------------------
class User(Base):
    __tablename__ = "users"

    id: Mapped[str] = _uuid_pk()
    email: Mapped[str | None] = mapped_column(Text, nullable=True)
    credential_ref: Mapped[str | None] = mapped_column(Text, nullable=True)
    base_currency: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'ILS'")
    )
    locale: Mapped[str | None] = mapped_column(
        Text, nullable=True, server_default=text("'en'")
    )
    settings: Mapped[dict | None] = mapped_column(
        JSONB, nullable=True, server_default=text("'{}'::jsonb")
    )
    created_at: Mapped[object] = _created_at()
    updated_at: Mapped[object] = _updated_at()

    __table_args__ = (
        CheckConstraint("char_length(base_currency) = 3", name="ck_users_base_currency_len"),
        # Partial unique on lower(email) where email is not null (schema §3.1/§12).
        Index(
            "uq_users_email_lower",
            text("lower(email)"),
            unique=True,
            postgresql_where=text("email IS NOT NULL"),
        ),
    )


# ---------------------------------------------------------------------------
# accounts (deferred FK target — schema §4; created empty now)
# ---------------------------------------------------------------------------
class Account(Base):
    __tablename__ = "accounts"

    id: Mapped[str] = _uuid_pk()
    user_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    created_at: Mapped[object] = _created_at()
    updated_at: Mapped[object] = _updated_at()


# ---------------------------------------------------------------------------
# import_batches (deferred FK target — schema §4; created empty now)
# ---------------------------------------------------------------------------
class ImportBatch(Base):
    __tablename__ = "import_batches"

    id: Mapped[str] = _uuid_pk()
    user_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    created_at: Mapped[object] = _created_at()
    updated_at: Mapped[object] = _updated_at()


# ---------------------------------------------------------------------------
# categories (schema §3.5)
# ---------------------------------------------------------------------------
class Category(Base):
    __tablename__ = "categories"

    id: Mapped[str] = _uuid_pk()
    user_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=True,
    )
    key: Mapped[str | None] = mapped_column(Text, nullable=True)
    label_en: Mapped[str] = mapped_column(Text, nullable=False)
    label_he: Mapped[str | None] = mapped_column(Text, nullable=True)
    layer: Mapped[str] = mapped_column(Text, nullable=False)
    included_in_actual_spending: Mapped[bool] = mapped_column(Boolean, nullable=False)
    included_in_committed_projection: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    included_in_cash_flow: Mapped[bool] = mapped_column(Boolean, nullable=False)
    is_system: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    parent_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("categories.id"),
        nullable=True,
    )
    created_at: Mapped[object] = _created_at()
    updated_at: Mapped[object] = _updated_at()

    __table_args__ = (
        CheckConstraint(
            "layer IN ('consumer_spending','bank_movement')",
            name="ck_categories_layer",
        ),
        CheckConstraint(
            "included_in_committed_projection = false",
            name="ck_categories_no_projection",
        ),
        CheckConstraint(
            "(is_system AND user_id IS NULL) OR (NOT is_system AND user_id IS NOT NULL)",
            name="ck_categories_system_owner",
        ),
        # Partial unique on key where key is not null (schema §3.5/§12).
        Index(
            "uq_categories_key",
            "key",
            unique=True,
            postgresql_where=text("key IS NOT NULL"),
        ),
        Index("ix_categories_user_id", "user_id"),
        Index("ix_categories_layer", "layer"),
    )


# ---------------------------------------------------------------------------
# merchants (schema §3.3)
# ---------------------------------------------------------------------------
class Merchant(Base):
    __tablename__ = "merchants"

    id: Mapped[str] = _uuid_pk()
    user_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    normalized_merchant_name: Mapped[str] = mapped_column(Text, nullable=False)
    display_name: Mapped[str] = mapped_column(Text, nullable=False)
    default_category_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("categories.id", ondelete="SET NULL"),
        nullable=True,
    )
    created_at: Mapped[object] = _created_at()
    updated_at: Mapped[object] = _updated_at()

    __table_args__ = (
        UniqueConstraint(
            "user_id", "normalized_merchant_name", name="uq_merchants_user_normalized"
        ),
        # Composite-unique target enabling same-user composite FKs (schema §13).
        UniqueConstraint("id", "user_id", name="uq_merchants_id_user"),
        Index("ix_merchants_user_updated_at", "user_id", text("updated_at DESC")),
    )


# ---------------------------------------------------------------------------
# merchant_aliases (schema §3.4)
# ---------------------------------------------------------------------------
class MerchantAlias(Base):
    __tablename__ = "merchant_aliases"

    id: Mapped[str] = _uuid_pk()
    user_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    merchant_id: Mapped[str] = mapped_column(UUID(as_uuid=False), nullable=False)
    alias_text: Mapped[str] = mapped_column(Text, nullable=False)
    normalized_alias_key: Mapped[str] = mapped_column(Text, nullable=False)
    source: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'user_confirmed'")
    )
    confidence: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[object] = _created_at()
    last_seen_at: Mapped[object | None] = mapped_column(
        TIMESTAMP(timezone=True), nullable=True
    )

    __table_args__ = (
        # user FK with cascade (schema §13).
        ForeignKeyConstraint(["user_id"], ["users.id"], ondelete="CASCADE"),
        # Composite same-user FK to merchants(id, user_id) with cascade on merchant
        # delete (aliases have no meaning without their merchant — schema §13).
        ForeignKeyConstraint(
            ["merchant_id", "user_id"],
            ["merchants.id", "merchants.user_id"],
            ondelete="CASCADE",
            name="fk_merchant_aliases_merchant_user",
        ),
        UniqueConstraint(
            "user_id", "normalized_alias_key", name="uq_merchant_aliases_user_key"
        ),
        CheckConstraint(
            "source IN ('user_confirmed','import_parsed','system_suggested')",
            name="ck_merchant_aliases_source",
        ),
        Index("ix_merchant_aliases_merchant_id", "merchant_id"),
        Index(
            "ix_merchant_aliases_user_last_seen",
            "user_id",
            text("last_seen_at DESC"),
        ),
    )


# ---------------------------------------------------------------------------
# category_rules (schema §3.6)
# ---------------------------------------------------------------------------
class CategoryRule(Base):
    __tablename__ = "category_rules"

    id: Mapped[str] = _uuid_pk()
    user_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    match_type: Mapped[str] = mapped_column(Text, nullable=False)
    match_value: Mapped[str] = mapped_column(Text, nullable=False)
    category_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("categories.id", ondelete="CASCADE"),
        nullable=False,
    )
    priority: Mapped[int] = mapped_column(
        SmallInteger, nullable=False, server_default=text("100")
    )
    source: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'user_correction'")
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    created_at: Mapped[object] = _created_at()
    updated_at: Mapped[object] = _updated_at()

    __table_args__ = (
        CheckConstraint(
            "match_type IN ('merchant_exact','merchant_contains')",
            name="ck_category_rules_match_type",
        ),
        CheckConstraint(
            "source IN ('system','user_correction')",
            name="ck_category_rules_source",
        ),
        UniqueConstraint(
            "user_id", "match_type", "match_value", name="uq_category_rules_user_match"
        ),
        Index("ix_category_rules_user_priority", "user_id", "priority"),
    )


# ---------------------------------------------------------------------------
# transactions (schema §3.2 / §5)
# ---------------------------------------------------------------------------
class Transaction(Base):
    __tablename__ = "transactions"

    id: Mapped[str] = _uuid_pk()
    user_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'ILS'")
    )
    transaction_type: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'expense'")
    )
    source: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'manual'")
    )
    merchant_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True)
    category_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("categories.id", ondelete="SET NULL"),
        nullable=True,
    )
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    occurred_on: Mapped[object] = mapped_column(
        Date, nullable=False, server_default=text("CURRENT_DATE")
    )
    raw_merchant_input: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_description: Mapped[str | None] = mapped_column(Text, nullable=True)
    value_date: Mapped[object | None] = mapped_column(Date, nullable=True)
    reference: Mapped[str | None] = mapped_column(Text, nullable=True)
    operation_type: Mapped[str | None] = mapped_column(Text, nullable=True)
    is_card_settlement: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("false")
    )
    account_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("accounts.id", ondelete="SET NULL"),
        nullable=True,
    )
    import_batch_id: Mapped[str | None] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("import_batches.id", ondelete="SET NULL"),
        nullable=True,
    )
    dedup_hash: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[object] = _created_at()
    updated_at: Mapped[object] = _updated_at()

    __table_args__ = (
        # Composite same-user FK to merchants(id, user_id); SET NULL on merchant
        # delete preserves the transaction as history (schema §5/§13). The
        # composite FK sets only merchant_id to NULL (user_id is never nulled).
        ForeignKeyConstraint(
            ["merchant_id", "user_id"],
            ["merchants.id", "merchants.user_id"],
            ondelete="SET NULL",
            name="fk_transactions_merchant_user",
        ),
        # Same-user composite target so referencing tables could point at a
        # transaction within the same user (future-compatible; schema §13).
        UniqueConstraint("id", "user_id", name="uq_transactions_id_user"),
        CheckConstraint("amount_minor <> 0", name="ck_transactions_amount_nonzero"),
        CheckConstraint("char_length(currency) = 3", name="ck_transactions_currency_len"),
        CheckConstraint(
            "transaction_type IN ('expense','income','refund','adjustment')",
            name="ck_transactions_type",
        ),
        CheckConstraint(
            "source IN ('manual','bank_import','card_import')",
            name="ck_transactions_source",
        ),
        # Imports must carry a dedup_hash; manual rows need not (schema §5/§13).
        CheckConstraint(
            "source = 'manual' OR dedup_hash IS NOT NULL",
            name="ck_transactions_import_dedup",
        ),
        # Partial unique import-dedup; null dedup_hash (manual) never blocked.
        Index(
            "uq_transactions_user_dedup",
            "user_id",
            "dedup_hash",
            unique=True,
            postgresql_where=text("dedup_hash IS NOT NULL"),
        ),
        Index("ix_transactions_user_occurred_on", "user_id", "occurred_on"),
        Index("ix_transactions_user_category", "user_id", "category_id"),
        Index("ix_transactions_user_merchant", "user_id", "merchant_id"),
    )


# ---------------------------------------------------------------------------
# recurring_expense_templates (schema §3.7 / §9)
# ---------------------------------------------------------------------------
class RecurringExpenseTemplate(Base):
    __tablename__ = "recurring_expense_templates"

    id: Mapped[str] = _uuid_pk()
    user_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("users.id", ondelete="CASCADE"),
        nullable=False,
    )
    name: Mapped[str] = mapped_column(Text, nullable=False)
    amount_minor: Mapped[int] = mapped_column(BigInteger, nullable=False)
    currency: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'ILS'")
    )
    # ON DELETE RESTRICT: a template must always keep a category (schema §3.7/§13).
    category_id: Mapped[str] = mapped_column(
        UUID(as_uuid=False),
        ForeignKey("categories.id", ondelete="RESTRICT"),
        nullable=False,
    )
    merchant_id: Mapped[str | None] = mapped_column(UUID(as_uuid=False), nullable=True)
    cadence: Mapped[str] = mapped_column(
        Text, nullable=False, server_default=text("'monthly'")
    )
    next_expected_date: Mapped[object] = mapped_column(Date, nullable=False)
    counts_in_projection: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    is_active: Mapped[bool] = mapped_column(
        Boolean, nullable=False, server_default=text("true")
    )
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    created_at: Mapped[object] = _created_at()
    updated_at: Mapped[object] = _updated_at()

    __table_args__ = (
        # Same-user composite FK to merchants; SET NULL on merchant delete (optional link).
        ForeignKeyConstraint(
            ["merchant_id", "user_id"],
            ["merchants.id", "merchants.user_id"],
            ondelete="SET NULL",
            name="fk_recurring_templates_merchant_user",
        ),
        CheckConstraint(
            "cadence IN ('weekly','monthly','yearly')",
            name="ck_recurring_templates_cadence",
        ),
        CheckConstraint(
            "amount_minor <> 0", name="ck_recurring_templates_amount_nonzero"
        ),
        CheckConstraint(
            "char_length(currency) = 3", name="ck_recurring_templates_currency_len"
        ),
        Index(
            "ix_recurring_templates_user_active_next",
            "user_id",
            "is_active",
            "next_expected_date",
        ),
    )
