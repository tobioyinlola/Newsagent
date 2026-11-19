"""Several contacts per outlet (copied on every email), and where each placement is in outreach."""

import sqlalchemy as sa

from alembic import op

revision = "0052"
down_revision = "0051"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("distribution_placements") as b:
        b.add_column(sa.Column("cc_emails", sa.JSON, nullable=False, server_default="[]"))
        b.add_column(sa.Column("outreach_state", sa.String(20), nullable=False, server_default=""))
        b.create_index("ix_distribution_placements_outreach_state", ["outreach_state"])
    with op.batch_alter_table("distribution_mail") as b:
        b.add_column(sa.Column("cc", sa.JSON, nullable=False, server_default="[]"))
    with op.batch_alter_table("outreach_threads") as b:
        b.add_column(sa.Column("cc_emails", sa.JSON, nullable=False, server_default="[]"))


def downgrade():
    with op.batch_alter_table("outreach_threads") as b:
        b.drop_column("cc_emails")
    with op.batch_alter_table("distribution_mail") as b:
        b.drop_column("cc")
    with op.batch_alter_table("distribution_placements") as b:
        b.drop_index("ix_distribution_placements_outreach_state")
        b.drop_column("outreach_state")
        b.drop_column("cc_emails")
