"""Behaviour events for segments, and workflow re-entry."""

import sqlalchemy as sa

from alembic import op

revision = "0047"
down_revision = "0046"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "user_events",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("user_id", sa.String(32), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("name", sa.String(40), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_user_events_user_id", "user_events", ["user_id"])
    op.create_index("ix_user_events_name", "user_events", ["name"])
    op.create_index("ix_user_events_created_at", "user_events", ["created_at"])
    with op.batch_alter_table("marketing_enrollments") as b:
        b.add_column(sa.Column("runs", sa.Integer, nullable=False, server_default="1"))


def downgrade():
    with op.batch_alter_table("marketing_enrollments") as b:
        b.drop_column("runs")
    op.drop_table("user_events")
