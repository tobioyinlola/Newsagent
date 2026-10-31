"""Project-specific founder broadcast location, with safe defaults for existing projects."""

import sqlalchemy as sa

from alembic import op

revision = "0033"
down_revision = "0032"
branch_labels = None
depends_on = None


def upgrade():
    op.add_column("projects", sa.Column("founder_location", sa.String(200), nullable=False, server_default=""))


def downgrade():
    op.drop_column("projects", "founder_location")
