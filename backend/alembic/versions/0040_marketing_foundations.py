"""Marketing email foundations: per-person opt-out, suppression list, send log."""

import sqlalchemy as sa

from alembic import op

revision = "0040"
down_revision = "0039"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "marketing_prefs",
        sa.Column("user_id", sa.String(32), sa.ForeignKey("users.id", ondelete="CASCADE"), primary_key=True),
        sa.Column("token", sa.String(64), nullable=False, unique=True),
        sa.Column("opted_out_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("source", sa.String(30), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "marketing_suppressions",
        sa.Column("email", sa.String(320), primary_key=True),
        sa.Column("reason", sa.String(100), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "marketing_sends",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("user_id", sa.String(32), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(30), nullable=False, server_default=""),
        sa.Column("ref", sa.String(64), nullable=False, server_default=""),
        sa.Column("subject", sa.Text, nullable=False, server_default=""),
        sa.Column("status", sa.String(10), nullable=False),
        sa.Column("skip_reason", sa.String(40), nullable=False, server_default=""),
        sa.Column("idempotency_key", sa.String(120), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("idempotency_key"),
    )
    op.create_index("ix_marketing_sends_user_id", "marketing_sends", ["user_id"])
    op.create_index("ix_marketing_sends_status", "marketing_sends", ["status"])
    op.create_index("ix_marketing_sends_created_at", "marketing_sends", ["created_at"])


def downgrade():
    op.drop_table("marketing_sends")
    op.drop_table("marketing_suppressions")
    op.drop_table("marketing_prefs")
