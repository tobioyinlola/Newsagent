"""count how often each shared video is opened (the impressions shown on the public site)

Revision ID: 0013
Revises: 0012
"""

import sqlalchemy as sa

from alembic import op

revision = "0013"
down_revision = "0012"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("share_links", sa.Column("views", sa.Integer(), nullable=False, server_default="0"))


def downgrade() -> None:
    op.drop_column("share_links", "views")
