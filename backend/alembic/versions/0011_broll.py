"""product b-roll: video measurements on brand assets, the owner's b-roll choices on projects

Revision ID: 0011
Revises: 0010
"""

import sqlalchemy as sa

from alembic import op

revision = "0011"
down_revision = "0010"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("brand_assets", sa.Column("duration_s", sa.Float(), nullable=True))
    op.add_column("brand_assets", sa.Column("width", sa.Integer(), nullable=True))
    op.add_column("brand_assets", sa.Column("height", sa.Integer(), nullable=True))
    op.add_column("projects", sa.Column("broll", sa.JSON(), nullable=True))


def downgrade() -> None:
    op.drop_column("projects", "broll")
    op.drop_column("brand_assets", "height")
    op.drop_column("brand_assets", "width")
    op.drop_column("brand_assets", "duration_s")
