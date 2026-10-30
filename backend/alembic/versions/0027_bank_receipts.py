"""Persist verified bank receipts for reconciliation and globally unique allocation."""

import sqlalchemy as sa

from alembic import op

revision = "0027"
down_revision = "0026"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "bank_receipts",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("api_url", sa.String(200), nullable=False),
        sa.Column("transfer_id", sa.String(100), nullable=False),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.Column("checkout_id", sa.String(32), sa.ForeignKey("checkouts.id", ondelete="SET NULL"), nullable=True),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("matched_by", sa.String(320), nullable=True),
        sa.Column("matched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("api_url", "transfer_id"),
    )
    for key in ["transfer_id", "checkout_id", "status"]:
        op.create_index("ix_bank_receipts_" + key, "bank_receipts", [key])


def downgrade():
    op.drop_table("bank_receipts")
