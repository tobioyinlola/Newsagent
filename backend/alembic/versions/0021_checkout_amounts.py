"""credits are bought as fixed dollar amounts: a checkout no longer points at a credit pack

Revision ID: 0021
Revises: 0020
"""

import sqlalchemy as sa

from alembic import op

revision = "0021"
down_revision = "0020"
branch_labels = None
depends_on = None


def upgrade() -> None:
    with op.batch_alter_table("checkouts") as batch:
        batch.alter_column("pack_id", existing_type=sa.String(32), nullable=True)


def downgrade() -> None:
    # packs are gone, so rows made after this have none: give them a placeholder before making the column required again
    op.execute("UPDATE checkouts SET pack_id = (SELECT id FROM credit_packs LIMIT 1) WHERE pack_id IS NULL")
    with op.batch_alter_table("checkouts") as batch:
        batch.alter_column("pack_id", existing_type=sa.String(32), nullable=False)
