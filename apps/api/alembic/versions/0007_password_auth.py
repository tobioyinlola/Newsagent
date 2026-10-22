"""password sign-in; drop authenticator-app columns

Revision ID: 0007
Revises: 0006
"""

import sqlalchemy as sa

from alembic import op

revision = "0007"
down_revision = "0006"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.add_column("users", sa.Column("password_hash", sa.Text(), nullable=True))
    op.add_column("auth_codes", sa.Column("password_hash", sa.Text(), nullable=True))
    op.alter_column("sessions", "mfa_verified", new_column_name="otp_verified")
    op.drop_table("recovery_codes")
    op.drop_column("users", "totp_secret_enc")
    op.drop_column("users", "totp_enabled")
    op.drop_column("users", "totp_last_step")


def downgrade() -> None:
    op.add_column("users", sa.Column("totp_last_step", sa.Integer(), nullable=True))
    op.add_column("users", sa.Column("totp_enabled", sa.Boolean(), server_default=sa.false(), nullable=False))
    op.add_column("users", sa.Column("totp_secret_enc", sa.Text(), nullable=True))
    op.create_table(
        "recovery_codes",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("user_id", sa.String(32), sa.ForeignKey("users.id"), nullable=False, index=True),
        sa.Column("code_hash", sa.String(64), nullable=False),
        sa.Column("used_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.alter_column("sessions", "otp_verified", new_column_name="mfa_verified")
    op.drop_column("auth_codes", "password_hash")
    op.drop_column("users", "password_hash")
