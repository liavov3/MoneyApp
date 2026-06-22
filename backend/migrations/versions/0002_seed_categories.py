"""Seed the 22 system categories (CATEGORY_TAXONOMY §10).

Idempotent: inserts only keys not already present, so re-running is safe.
All rows: is_system=true, user_id=NULL, parent_id=NULL,
included_in_committed_projection=false.

Revision ID: 0002_seed_categories
Revises: 0001_initial_schema
Create Date: 2026-06-14
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from app.seed_data import SEED_CATEGORIES

revision: str = "0002_seed_categories"
down_revision: Union[str, None] = "0001_initial_schema"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    insert_sql = sa.text(
        """
        INSERT INTO categories
            (id, user_id, key, label_en, label_he, layer,
             included_in_actual_spending, included_in_committed_projection,
             included_in_cash_flow, is_system, parent_id)
        SELECT gen_random_uuid(), NULL, :key, :label_en, :label_he, :layer,
               :in_actual, false, :in_cash_flow, true, NULL
        WHERE NOT EXISTS (
            SELECT 1 FROM categories WHERE key = :key
        )
        """
    )
    bind = op.get_bind()
    for cat in SEED_CATEGORIES:
        bind.execute(
            insert_sql,
            {
                "key": cat.key,
                "label_en": cat.label_en,
                "label_he": cat.label_he,
                "layer": cat.layer,
                "in_actual": cat.included_in_actual_spending,
                "in_cash_flow": cat.included_in_cash_flow,
            },
        )


def downgrade() -> None:
    keys = [c.key for c in SEED_CATEGORIES]
    op.get_bind().execute(
        sa.text("DELETE FROM categories WHERE is_system = true AND key = ANY(:keys)"),
        {"keys": keys},
    )
