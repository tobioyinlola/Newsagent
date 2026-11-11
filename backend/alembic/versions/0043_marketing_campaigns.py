"""Marketing campaigns: one-off sends of a copy to a segment, and who each one went to."""

import sqlalchemy as sa

from alembic import op

revision = "0043"
down_revision = "0042"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "marketing_campaigns",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("segment_id", sa.String(32), sa.ForeignKey("marketing_segments.id"), nullable=False),
        sa.Column("copy_id", sa.String(32), sa.ForeignKey("marketing_copies.id"), nullable=False),
        sa.Column("copy_version", sa.Integer, nullable=False),
        sa.Column("rules", sa.JSON, nullable=False),
        sa.Column("status", sa.String(12), nullable=False, server_default="draft"),
        sa.Column("send_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("started_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("audience", sa.Integer, nullable=False, server_default="0"),
        sa.Column("created_by", sa.String(320), nullable=False, server_default=""),
        sa.Column("scheduled_by", sa.String(320), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_marketing_campaigns_status", "marketing_campaigns", ["status"])
    op.create_index("ix_marketing_campaigns_send_at", "marketing_campaigns", ["send_at"])
    op.create_table(
        "marketing_recipients",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column(
            "campaign_id", sa.String(32), sa.ForeignKey("marketing_campaigns.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("user_id", sa.String(32), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(10), nullable=False, server_default="pending"),
        sa.Column("reason", sa.String(40), nullable=False, server_default=""),
        sa.Column("done_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("campaign_id", "user_id"),
    )
    op.create_index("ix_marketing_recipients_campaign_id", "marketing_recipients", ["campaign_id"])
    op.create_index("ix_marketing_recipients_status", "marketing_recipients", ["status"])


def downgrade():
    op.drop_table("marketing_recipients")
    op.drop_table("marketing_campaigns")
