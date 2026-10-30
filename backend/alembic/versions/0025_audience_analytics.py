"""Daily first-party analytics and publisher cumulative snapshots. No historical counts are invented."""

import sqlalchemy as sa

from alembic import op

revision = "0025"
down_revision = "0024"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "audience_events",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("project_id", sa.String(32), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        sa.Column("kind", sa.String(30), nullable=False),
        sa.Column("session_hash", sa.String(64), nullable=False),
        sa.UniqueConstraint("project_id", "day", "kind", "session_hash"),
    )
    op.create_index("ix_audience_events_project_id", "audience_events", ["project_id"])
    op.create_index("ix_audience_events_day", "audience_events", ["day"])
    op.create_table(
        "audience_daily",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("project_id", sa.String(32), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False),
        sa.Column("day", sa.Date(), nullable=False),
        *[
            sa.Column(name, sa.BigInteger(), nullable=False)
            for name in ["impressions", "story_visits", "share_visits", "video_views", "video_completions"]
        ],
        sa.UniqueConstraint("project_id", "day"),
    )
    op.create_index("ix_audience_daily_project_id", "audience_daily", ["project_id"])
    op.create_index("ix_audience_daily_day", "audience_daily", ["day"])
    op.create_table(
        "publisher_snapshots",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("workspace_id", sa.String(32), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column(
            "request_id", sa.String(32), sa.ForeignKey("distribution_requests.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "placement_id",
            sa.String(32),
            sa.ForeignKey("distribution_placements.id", ondelete="CASCADE"),
            nullable=False,
        ),
        sa.Column("project_id", sa.String(32), sa.ForeignKey("projects.id", ondelete="SET NULL"), nullable=True),
        sa.Column("as_of", sa.Date(), nullable=False),
        sa.Column("views", sa.BigInteger(), nullable=True),
        sa.Column("impressions", sa.BigInteger(), nullable=True),
        sa.Column("source_note", sa.Text(), nullable=False),
        sa.Column("updated_by", sa.String(320), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("placement_id", "as_of"),
    )
    for column in ["workspace_id", "request_id", "placement_id", "project_id"]:
        op.create_index("ix_publisher_snapshots_" + column, "publisher_snapshots", [column])


def downgrade():
    op.drop_table("publisher_snapshots")
    op.drop_table("audience_daily")
    op.drop_table("audience_events")
