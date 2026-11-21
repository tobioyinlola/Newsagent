"""An announcement's button can open a link, or let the customer share their referral link."""

import sqlalchemy as sa

from alembic import op

revision = "0055"
down_revision = "0054"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("announcements") as b:
        b.add_column(sa.Column("button_action", sa.String(20), nullable=False, server_default="link"))


def downgrade():
    with op.batch_alter_table("announcements") as b:
        b.drop_column("button_action")
