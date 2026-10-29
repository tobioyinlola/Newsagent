"""latest stories: each finished video's public page (slug and publish time)

Revision ID: 0018
Revises: 0017
"""

import sqlalchemy as sa

from alembic import op

revision = "0018"
down_revision = "0017"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("projects", sa.Column("story_slug", sa.String(160), nullable=True))
    op.add_column("projects", sa.Column("published_at", sa.DateTime(timezone=True), nullable=True))
    op.create_index("ix_projects_story_slug", "projects", ["story_slug"], unique=True)
    op.create_index("ix_projects_published_at", "projects", ["published_at"])


def downgrade() -> None:
    op.drop_index("ix_projects_published_at", table_name="projects")
    op.drop_index("ix_projects_story_slug", table_name="projects")
    op.drop_column("projects", "published_at")
    op.drop_column("projects", "story_slug")
