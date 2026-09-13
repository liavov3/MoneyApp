"""Private owner login and revocable sessions (PRIVATE_AUTH_V0_0_2)."""
from alembic import op
import sqlalchemy as sa
from sqlalchemy.dialects import postgresql

revision = "0006_private_auth"
down_revision = "0005_monthly_goals_types_scopes"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "private_accounts",
        sa.Column("user_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("username", sa.Text(), nullable=False, unique=True),
        sa.Column("password_hash", sa.Text(), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("updated_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
    )
    op.create_table(
        "private_sessions",
        sa.Column("token_hash", sa.String(64), primary_key=True),
        sa.Column("user_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("private_accounts.user_id", ondelete="CASCADE"), nullable=False),
        sa.Column("created_at", sa.TIMESTAMP(timezone=True), nullable=False, server_default=sa.func.now()),
        sa.Column("expires_at", sa.TIMESTAMP(timezone=True), nullable=False),
    )
    op.create_index("ix_private_sessions_user_expiry", "private_sessions", ["user_id", "expires_at"])
    op.create_table(
        "private_login_windows",
        sa.Column("user_id", postgresql.UUID(as_uuid=False), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("window_started_at", sa.TIMESTAMP(timezone=True), nullable=False),
        sa.Column("attempts", sa.SmallInteger(), nullable=False),
        sa.CheckConstraint("attempts >= 0", name="ck_private_login_attempts"),
    )


def downgrade():
    op.drop_table("private_login_windows")
    op.drop_index("ix_private_sessions_user_expiry", table_name="private_sessions")
    op.drop_table("private_sessions")
    op.drop_table("private_accounts")
