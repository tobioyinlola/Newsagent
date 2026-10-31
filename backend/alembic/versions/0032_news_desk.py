"""Independent editorial news drafts, publication snapshots and verified images."""

import sqlalchemy as sa

from alembic import op

revision = "0032"
down_revision = "0031"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "news_desk_stories",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("slug", sa.String(100), nullable=False, unique=True),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("revision", sa.Integer, nullable=False),
        sa.Column("data", sa.JSON, nullable=False),
        sa.Column("published_data", sa.JSON, nullable=True),
        sa.Column("created_by", sa.String(320), nullable=False),
        sa.Column("updated_by", sa.String(320), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_news_desk_stories_status", "news_desk_stories", ["status"])
    op.create_index("ix_news_desk_stories_published_at", "news_desk_stories", ["published_at"])
    op.create_table(
        "news_desk_images",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("story_id", sa.String(32), sa.ForeignKey("news_desk_stories.id"), nullable=False),
        sa.Column("key", sa.String(500), unique=True, nullable=False),
        sa.Column("content_type", sa.String(80), nullable=False),
        sa.Column("size_bytes", sa.Integer, nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("filename", sa.Text, nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_news_desk_images_story_id", "news_desk_images", ["story_id"])


def downgrade():
    op.drop_table("news_desk_images")
    op.drop_table("news_desk_stories")
