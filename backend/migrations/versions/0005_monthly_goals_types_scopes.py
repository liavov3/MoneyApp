"""Evolve `monthly_goals` -> goal types + default/override scopes.

Outside the frozen v0.0.1 contract. A goal was one positive-agorot expense cap
per (user, month). This adds:
  - goal_type ('expense'|'income'|'savings')
  - scope ('default' | 'month_override'); default rows carry month=NULL
  - month becomes NULLABLE (NULL for default, 'YYYY-MM' for override)

Existing rows were month-specific expense caps, so they backfill to
expense/month_override keeping their `month`. Two partial unique indexes replace
the old (user_id, month) unique constraint: one default per (user, goal_type),
one override per (user, goal_type, month).

Revision ID: 0005_monthly_goals_types_scopes
Revises: 0004_monthly_goals
Create Date: 2026-07-01
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

revision: str = "0005_monthly_goals_types_scopes"
down_revision: Union[str, None] = "0004_monthly_goals"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # 1. Drop the old (user_id, month) unique + old month-format check (which
    #    assumed month NOT NULL).
    op.drop_constraint(
        "uq_monthly_goals_user_month", "monthly_goals", type_="unique"
    )
    op.drop_constraint(
        "ck_monthly_goals_month_format", "monthly_goals", type_="check"
    )

    # 2. Add goal_type + scope NOT NULL with temporary server_defaults so existing
    #    rows backfill (expense / month_override), then strip the defaults so
    #    future inserts must be explicit.
    op.add_column(
        "monthly_goals",
        sa.Column(
            "goal_type",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'expense'"),
        ),
    )
    op.add_column(
        "monthly_goals",
        sa.Column(
            "scope",
            sa.Text(),
            nullable=False,
            server_default=sa.text("'month_override'"),
        ),
    )
    op.alter_column("monthly_goals", "goal_type", server_default=None)
    op.alter_column("monthly_goals", "scope", server_default=None)

    # 3. month is NULL for default goals.
    op.alter_column("monthly_goals", "month", nullable=True)

    # 4. New check constraints.
    op.create_check_constraint(
        "ck_monthly_goals_goal_type",
        "monthly_goals",
        "goal_type IN ('expense', 'income', 'savings')",
    )
    op.create_check_constraint(
        "ck_monthly_goals_scope",
        "monthly_goals",
        "scope IN ('default', 'month_override')",
    )
    op.create_check_constraint(
        "ck_monthly_goals_scope_month",
        "monthly_goals",
        "(scope = 'default' AND month IS NULL) "
        "OR (scope = 'month_override' AND month IS NOT NULL)",
    )
    op.create_check_constraint(
        "ck_monthly_goals_month_format",
        "monthly_goals",
        "month IS NULL OR month ~ '^[0-9]{4}-(0[1-9]|1[0-2])$'",
    )

    # 5. Partial unique indexes: one default per (user, goal_type); one override
    #    per (user, goal_type, month).
    op.create_index(
        "uq_monthly_goals_default",
        "monthly_goals",
        ["user_id", "goal_type"],
        unique=True,
        postgresql_where=sa.text("scope = 'default'"),
    )
    op.create_index(
        "uq_monthly_goals_override",
        "monthly_goals",
        ["user_id", "goal_type", "month"],
        unique=True,
        postgresql_where=sa.text("scope = 'month_override'"),
    )


def downgrade() -> None:
    # Dev-only, best-effort reverse. Collapsing default+override back to a single
    # (user_id, month) unique can lose rows (a default has month=NULL and can't
    # satisfy the restored NOT NULL); acceptable for dev.
    op.drop_index("uq_monthly_goals_override", table_name="monthly_goals")
    op.drop_index("uq_monthly_goals_default", table_name="monthly_goals")
    op.drop_constraint(
        "ck_monthly_goals_month_format", "monthly_goals", type_="check"
    )
    op.drop_constraint(
        "ck_monthly_goals_scope_month", "monthly_goals", type_="check"
    )
    op.drop_constraint("ck_monthly_goals_scope", "monthly_goals", type_="check")
    op.drop_constraint("ck_monthly_goals_goal_type", "monthly_goals", type_="check")

    # Drop default rows that can't satisfy the restored NOT NULL month.
    op.execute("DELETE FROM monthly_goals WHERE month IS NULL")

    op.drop_column("monthly_goals", "scope")
    op.drop_column("monthly_goals", "goal_type")
    op.alter_column("monthly_goals", "month", nullable=False)

    op.create_check_constraint(
        "ck_monthly_goals_month_format",
        "monthly_goals",
        "month ~ '^[0-9]{4}-(0[1-9]|1[0-2])$'",
    )
    op.create_unique_constraint(
        "uq_monthly_goals_user_month", "monthly_goals", ["user_id", "month"]
    )
