"""Marketing copies: reusable email copy, kept as numbered versions."""

import sqlalchemy as sa

from alembic import op

revision = "0042"
down_revision = "0041"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "marketing_copies",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("category", sa.String(20), nullable=False, server_default="product"),
        sa.Column("current_version", sa.Integer, nullable=False, server_default="1"),
        sa.Column("created_by", sa.String(320), nullable=False, server_default=""),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "marketing_copy_versions",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("copy_id", sa.String(32), sa.ForeignKey("marketing_copies.id", ondelete="CASCADE"), nullable=False),
        sa.Column("version", sa.Integer, nullable=False),
        sa.Column("subject", sa.String(200), nullable=False),
        sa.Column("preheader", sa.String(200), nullable=False, server_default=""),
        sa.Column("body", sa.Text, nullable=False),
        sa.Column("button_label", sa.String(60), nullable=False, server_default=""),
        sa.Column("button_url", sa.String(500), nullable=False, server_default=""),
        sa.Column("created_by", sa.String(320), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("copy_id", "version"),
    )
    op.create_index("ix_marketing_copy_versions_copy_id", "marketing_copy_versions", ["copy_id"])


def downgrade():
    op.drop_table("marketing_copy_versions")
    op.drop_table("marketing_copies")
