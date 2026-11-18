"""Campaigns can go out as one Resend Broadcast instead of one email each."""

import sqlalchemy as sa

from alembic import op

revision = "0050"
down_revision = "0049"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("marketing_campaigns") as b:
        b.add_column(sa.Column("channel", sa.String(10), nullable=False, server_default="direct"))
        b.add_column(sa.Column("broadcast_id", sa.String(64), nullable=False, server_default=""))


def downgrade():
    with op.batch_alter_table("marketing_campaigns") as b:
        b.drop_column("broadcast_id")
        b.drop_column("channel")
