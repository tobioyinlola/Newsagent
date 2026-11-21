"""Announcements: a pop-up for customers for a set time, and optionally an email to all of them."""

import sqlalchemy as sa

from alembic import op

revision = "0054"
down_revision = "0053"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "announcements",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("title", sa.String(120), nullable=False),
        sa.Column("message", sa.Text, nullable=False),
        sa.Column("button_label", sa.String(60), nullable=False, server_default=""),
        sa.Column("button_url", sa.String(500), nullable=False, server_default=""),
        sa.Column("shows_from", sa.DateTime(timezone=True), nullable=False),
        sa.Column("shows_until", sa.DateTime(timezone=True), nullable=False),
        sa.Column("ended_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("email_campaign_id", sa.String(32), nullable=True),
        sa.Column("created_by", sa.String(320), nullable=False, server_default=""),
    )
    op.create_index("ix_announcements_shows_until", "announcements", ["shows_until"])


def downgrade():
    op.drop_index("ix_announcements_shows_until", table_name="announcements")
    op.drop_table("announcements")
