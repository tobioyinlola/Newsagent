"""workspace industry, chosen at sign-up

Revision ID: 0016
Revises: 0015
"""

import sqlalchemy as sa

from alembic import op

revision = "0016"
down_revision = "0015"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table in ("workspaces", "auth_codes"):
        op.add_column(table, sa.Column("industry", sa.String(30), nullable=True))


def downgrade() -> None:
    for table in ("workspaces", "auth_codes"):
        op.drop_column(table, "industry")
