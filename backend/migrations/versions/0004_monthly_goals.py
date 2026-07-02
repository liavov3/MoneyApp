"""Additive `monthly_goals` table — monthly spending goal (budget cap) per user.

Outside the frozen v0.0.1 contract. One positive-agorot budget cap per
(user, month); a goal is NOT an expense, so amount_minor is CHECK > 0. Month is
stored as 'YYYY-MM' text with a format CHECK. Unique per (user_id, month) so a
PUT is an idempotent upsert.

Revision ID: 0004_monthly_goals
Revises: 0003_seed_dev_user
Create Date: 2026-07-01
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op
from sqlalchemy.dialects import postgresql

revision: str = "0004_monthly_goals"
down_revision: Union[str, None] = "0003_seed_dev_user"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None

UUID = postgresql.UUID(as_uuid=False)
TS = postgresql.TIMESTAMP(timezone=True)


def upgrade() -> None:
    op.create_table(
        "monthly_goals",
        sa.Column(
            "id", UUID, primary_key=True, server_default=sa.text("gen_random_uuid()")
        ),
        sa.Column(
            "user_id",
            UUID,
            sa.ForeignKey("users.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("month", sa.Text(), nullable=False),
        sa.Column("amount_minor", sa.BigInteger(), nullable=False),
        sa.Column(
            "currency", sa.Text(), nullable=False, server_default=sa.text("'ILS'")
        ),
        sa.Column(
            "created_at", TS, nullable=False, server_default=sa.text("now()")
        ),
        sa.Column(
            "updated_at", TS, nullable=False, server_default=sa.text("now()")
        ),
        sa.CheckConstraint(
            "month ~ '^[0-9]{4}-(0[1-9]|1[0-2])$'",
            name="ck_monthly_goals_month_format",
        ),
        sa.CheckConstraint("amount_minor > 0", name="ck_monthly_goals_amount_positive"),
        sa.CheckConstraint(
            "char_length(currency) = 3", name="ck_monthly_goals_currency_len"
        ),
        sa.UniqueConstraint("user_id", "month", name="uq_monthly_goals_user_month"),
    )


def downgrade() -> None:
    op.drop_table("monthly_goals")
