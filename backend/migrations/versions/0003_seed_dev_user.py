"""Seed the single dev/test user required by the DEV_BEARER_TOKEN principal.

API_CONTRACT §3: v0.0.1 is single-user/dev. The dev bearer token resolves
server-side to ONE `users` row whose id is `settings.dev_user_id`. This data
migration seeds exactly that row so user-owned writes (e.g. quick-add) satisfy
the `transactions.user_id -> users(id)` foreign key.

Idempotent: inserts only when the row is absent, so re-running is safe. No real
auth, no client-supplied user_id — the id is the fixed server-side sentinel.

Revision ID: 0003_seed_dev_user
Revises: 0002_seed_categories
Create Date: 2026-06-22
"""

from typing import Sequence, Union

import sqlalchemy as sa
from alembic import op

from app.config import get_settings

revision: str = "0003_seed_dev_user"
down_revision: Union[str, None] = "0002_seed_categories"
branch_labels: Union[str, Sequence[str], None] = None
depends_on: Union[str, Sequence[str], None] = None


def upgrade() -> None:
    # Same id the auth layer resolves the dev token to (single source of truth).
    dev_user_id = get_settings().dev_user_id
    op.get_bind().execute(
        sa.text(
            """
            INSERT INTO users (id, email, base_currency, locale)
            SELECT :uid, NULL, 'ILS', 'en'
            WHERE NOT EXISTS (SELECT 1 FROM users WHERE id = :uid)
            """
        ),
        {"uid": dev_user_id},
    )


def downgrade() -> None:
    dev_user_id = get_settings().dev_user_id
    # ON DELETE CASCADE removes any dependent rows (dev-only, destructive).
    op.get_bind().execute(
        sa.text("DELETE FROM users WHERE id = :uid"),
        {"uid": dev_user_id},
    )
