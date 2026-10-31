"""Bank transfer receipt review and durable notification outbox."""

import sqlalchemy as sa

from alembic import op

revision = "0031"
down_revision = "0030"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "payment_proofs",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("checkout_id", sa.String(32), sa.ForeignKey("checkouts.id"), nullable=False),
        sa.Column("key", sa.String(500), nullable=False, unique=True),
        sa.Column("filename", sa.String(200), nullable=False),
        sa.Column("content_type", sa.String(80), nullable=False),
        sa.Column("size_bytes", sa.Integer, nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("sha256", sa.String(64), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_payment_proofs_checkout_id", "payment_proofs", ["checkout_id"])
    op.create_table(
        "transfer_reviews",
        sa.Column("checkout_id", sa.String(32), sa.ForeignKey("checkouts.id"), primary_key=True),
        sa.Column("proof_id", sa.String(32), sa.ForeignKey("payment_proofs.id"), nullable=True),
        sa.Column("status", sa.String(24), nullable=False),
        sa.Column("revision", sa.Integer, nullable=False),
        sa.Column("submitted_by", sa.String(320), nullable=True),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reviewed_by", sa.String(320), nullable=True),
        sa.Column("reviewed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("reason", sa.Text, nullable=False),
        sa.Column("receiving_key", sa.String(64), nullable=False),
        sa.Column("payment_reference", sa.String(100), nullable=True),
        sa.Column("approved_proof_hash", sa.String(64), nullable=True, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("receiving_key", "payment_reference"),
    )
    op.create_index("ix_transfer_reviews_status", "transfer_reviews", ["status"])
    op.create_table(
        "transfer_mail",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("checkout_id", sa.String(32), sa.ForeignKey("checkouts.id"), nullable=False),
        sa.Column("revision", sa.Integer, nullable=False),
        sa.Column("kind", sa.String(30), nullable=False),
        sa.Column("recipient", sa.String(320), nullable=False),
        sa.Column("subject", sa.String(300), nullable=False),
        sa.Column("body", sa.Text, nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("attempts", sa.Integer, nullable=False),
        sa.Column("last_attempt_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("checkout_id", "revision", "kind", "recipient"),
    )
    op.create_index("ix_transfer_mail_checkout_id", "transfer_mail", ["checkout_id"])
    op.create_index("ix_transfer_mail_status", "transfer_mail", ["status"])


def downgrade():
    op.drop_table("transfer_mail")
    op.drop_table("transfer_reviews")
    op.drop_table("payment_proofs")
