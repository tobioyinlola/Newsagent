"""A/B test of a campaign's subject line."""

import sqlalchemy as sa

from alembic import op

revision = "0046"
down_revision = "0045"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("marketing_campaigns") as b:
        b.add_column(sa.Column("subject_b", sa.String(200), nullable=True))
        b.add_column(sa.Column("ab_mode", sa.String(8), nullable=False, server_default="split"))
        b.add_column(sa.Column("test_percent", sa.Integer, nullable=False, server_default="20"))
        b.add_column(sa.Column("wait_hours", sa.Integer, nullable=False, server_default="4"))
        b.add_column(sa.Column("metric", sa.String(8), nullable=False, server_default="opens"))
        b.add_column(sa.Column("winner", sa.String(1), nullable=True))
        b.add_column(sa.Column("decide_at", sa.DateTime(timezone=True), nullable=True))
    with op.batch_alter_table("marketing_recipients") as b:
        b.add_column(sa.Column("variant", sa.String(1), nullable=False, server_default=""))


def downgrade():
    with op.batch_alter_table("marketing_recipients") as b:
        b.drop_column("variant")
    with op.batch_alter_table("marketing_campaigns") as b:
        for c in ("decide_at", "winner", "metric", "wait_hours", "test_percent", "ab_mode", "subject_b"):
            b.drop_column(c)
