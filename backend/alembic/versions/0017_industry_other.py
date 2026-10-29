"""industry "other": the business's own words for it, collected at sign-up

Revision ID: 0017
Revises: 0016
"""

import sqlalchemy as sa

from alembic import op

revision = "0017"
down_revision = "0016"
branch_labels = None
depends_on = None


def upgrade() -> None:
    for table in ("workspaces", "auth_codes"):
        op.add_column(table, sa.Column("industry_other", sa.String(100), nullable=True))


def downgrade() -> None:
    for table in ("workspaces", "auth_codes"):
        op.drop_column(table, "industry_other")
