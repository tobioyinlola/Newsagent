"""What people did with an announcement: saw it, clicked it, closed it."""

import sqlalchemy as sa

from alembic import op

revision = "0055"
down_revision = "0054"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "announcement_events",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("announcement_id", sa.String(32), sa.ForeignKey("announcements.id", ondelete="CASCADE"), nullable=False),
        sa.Column("user_id", sa.String(32), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("kind", sa.String(10), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("announcement_id", "user_id", "kind"),
    )
    op.create_index("ix_announcement_events_announcement_id", "announcement_events", ["announcement_id"])
    op.create_index("ix_announcement_events_user_id", "announcement_events", ["user_id"])


def downgrade():
    op.drop_index("ix_announcement_events_user_id", table_name="announcement_events")
    op.drop_index("ix_announcement_events_announcement_id", table_name="announcement_events")
    op.drop_table("announcement_events")
