"""Campaign sending hours: only email people during the day where they live."""

import sqlalchemy as sa

from alembic import op

revision = "0048"
down_revision = "0047"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("marketing_campaigns") as b:
        b.add_column(sa.Column("hours", sa.JSON, nullable=True))
    with op.batch_alter_table("marketing_recipients") as b:
        b.add_column(sa.Column("send_after", sa.DateTime(timezone=True), nullable=True))
        b.create_index("ix_marketing_recipients_send_after", ["send_after"])


def downgrade():
    with op.batch_alter_table("marketing_recipients") as b:
        b.drop_index("ix_marketing_recipients_send_after")
        b.drop_column("send_after")
    with op.batch_alter_table("marketing_campaigns") as b:
        b.drop_column("hours")
