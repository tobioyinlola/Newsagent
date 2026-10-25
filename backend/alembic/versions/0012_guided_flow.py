"""guided flow: the kind of announcement, which flow a project uses, and the written story + social copy

Revision ID: 0012
Revises: 0011
"""

import sqlalchemy as sa

from alembic import op

revision = "0012"
down_revision = "0011"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("projects", sa.Column("flow", sa.String(10), nullable=False, server_default="classic"))
    op.add_column("projects", sa.Column("announcement_type", sa.String(30), nullable=True))
    op.add_column("script_versions", sa.Column("story", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("script_versions", "story")
    op.drop_column("projects", "announcement_type")
    op.drop_column("projects", "flow")
