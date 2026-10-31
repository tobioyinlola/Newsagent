"""Isolated News Desk video jobs; customer generation tables are unchanged."""

import sqlalchemy as sa

from alembic import op

revision = "0034"
down_revision = "0033"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "news_desk_videos",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("story_id", sa.String(32), sa.ForeignKey("news_desk_stories.id"), nullable=False),
        sa.Column("story_revision", sa.Integer, nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("snapshot", sa.JSON, nullable=False),
        sa.Column("progress", sa.Integer, nullable=False),
        sa.Column("provider_name", sa.String(40), nullable=False),
        sa.Column("provider_id", sa.String(200), nullable=False),
        sa.Column("renderer_id", sa.String(100), nullable=False),
        sa.Column("media", sa.JSON, nullable=False),
        sa.Column("error", sa.Text, nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("story_id", "story_revision"),
    )
    op.create_index("ix_news_desk_videos_story_id", "news_desk_videos", ["story_id"])
    op.create_index("ix_news_desk_videos_status", "news_desk_videos", ["status"])


def downgrade():
    op.drop_table("news_desk_videos")
