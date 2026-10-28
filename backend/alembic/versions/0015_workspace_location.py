"""workspace city and country (the press release dateline), collected at sign-up

Revision ID: 0015
Revises: 0014
"""

import sqlalchemy as sa

from alembic import op

revision = "0015"
down_revision = "0014"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table in ("workspaces", "auth_codes"):
        op.add_column(table, sa.Column("city", sa.String(120), nullable=True))
        op.add_column(table, sa.Column("country", sa.String(120), nullable=True))


def downgrade() -> None:
    for table in ("workspaces", "auth_codes"):
        op.drop_column(table, "country")
        op.drop_column(table, "city")
