"""remove the daily video limit: workspaces no longer cap how many videos they make in a day

Revision ID: 0020
Revises: 0019
"""

import sqlalchemy as sa

from alembic import op

revision = "0020"
down_revision = "0019"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("workspaces") as batch:
        batch.drop_column("max_videos_per_day")


def downgrade() -> None:
    with op.batch_alter_table("workspaces") as batch:
        batch.add_column(sa.Column("max_videos_per_day", sa.Integer(), nullable=False, server_default="3"))
