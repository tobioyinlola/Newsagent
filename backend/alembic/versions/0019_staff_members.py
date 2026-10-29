"""back-office team: staff members with roles and permissions

Revision ID: 0019
Revises: 0018
"""

import sqlalchemy as sa

from alembic import op

revision = "0019"
down_revision = "0018"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "staff_members",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("email", sa.String(320), nullable=False, unique=True),
        sa.Column("name", sa.String(200), nullable=False),
        sa.Column("role", sa.String(20), nullable=False),
        sa.Column("permissions", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(12), nullable=False),
        sa.Column("workspace_id", sa.String(32), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("user_id", sa.String(32), sa.ForeignKey("users.id"), nullable=True),
        sa.Column("invited_by", sa.String(320), nullable=False),
        sa.Column("token_hash", sa.String(64), nullable=True, unique=True),
        sa.Column("invite_expires_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("accepted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )


def downgrade() -> None:
    op.drop_table("staff_members")
