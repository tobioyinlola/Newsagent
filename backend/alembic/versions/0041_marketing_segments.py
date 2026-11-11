"""Marketing segments: saved rule sets that pick out groups of users."""

import sqlalchemy as sa

from alembic import op

revision = "0041"
down_revision = "0040"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "marketing_segments",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("description", sa.Text, nullable=False, server_default=""),
        sa.Column("rules", sa.JSON, nullable=False),
        sa.Column("created_by", sa.String(320), nullable=False, server_default=""),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade():
    op.drop_table("marketing_segments")
