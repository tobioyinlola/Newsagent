"""Persist payment ownership context and confirmation/verification state without card data."""

import sqlalchemy as sa

from alembic import op

revision = "0023"
down_revision = "0022"
branch_labels = None
depends_on = None


def upgrade():
    with op.batch_alter_table("checkouts") as batch:
        batch.add_column(sa.Column("payment_context", sa.JSON(), nullable=False, server_default="{}"))
        batch.add_column(sa.Column("confirmation_started_at", sa.DateTime(timezone=True), nullable=True))
        batch.add_column(sa.Column("last_verified_at", sa.DateTime(timezone=True), nullable=True))


def downgrade():
    with op.batch_alter_table("checkouts") as batch:
        batch.drop_column("last_verified_at")
        batch.drop_column("confirmation_started_at")
        batch.drop_column("payment_context")
