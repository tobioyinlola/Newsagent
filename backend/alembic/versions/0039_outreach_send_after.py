"""Outreach emails can be held until a time (a reply goes out some minutes after the outlet wrote)."""

import sqlalchemy as sa

from alembic import op

revision = "0039"
down_revision = "0038"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("distribution_mail", sa.Column("send_after", sa.DateTime(timezone=True), nullable=True))


def downgrade():
    op.drop_column("distribution_mail", "send_after")
