"""open sign-up: remember the business name chosen at sign-up until the emailed code is verified

Revision ID: 0014
Revises: 0013
"""

import sqlalchemy as sa

from alembic import op

revision = "0014"
down_revision = "0013"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("auth_codes", sa.Column("workspace_name", sa.String(200), nullable=True))


def downgrade() -> None:
    op.drop_column("auth_codes", "workspace_name")
