"""First-run questions (kept on the business) and onboarding / guided-tour progress (kept on the person)."""

import sqlalchemy as sa

from alembic import op

revision = "0053"
down_revision = "0052"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("workspaces") as b:
        b.add_column(sa.Column("profile", sa.JSON, nullable=False, server_default="{}"))
    with op.batch_alter_table("users") as b:
        b.add_column(sa.Column("onboarding", sa.JSON, nullable=False, server_default="{}"))


def downgrade():
    with op.batch_alter_table("users") as b:
        b.drop_column("onboarding")
    with op.batch_alter_table("workspaces") as b:
        b.drop_column("profile")
