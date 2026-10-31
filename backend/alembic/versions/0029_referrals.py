"""Unique share links, signup attribution, and one reward per referred business."""

import sqlalchemy as sa

from alembic import op

revision = "0029"
down_revision = "0028"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "referral_links",
        sa.Column("code", sa.String(24), primary_key=True),
        sa.Column("user_id", sa.String(32), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_table(
        "referral_rewards",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("referrer_user_id", sa.String(32), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("referrer_workspace_id", sa.String(32), sa.ForeignKey("workspaces.id"), nullable=False),
        sa.Column("referred_user_id", sa.String(32), sa.ForeignKey("users.id", ondelete="SET NULL"), nullable=True),
        sa.Column("referred_workspace_id", sa.String(32), sa.ForeignKey("workspaces.id"), nullable=False, unique=True),
        sa.Column("credits", sa.Numeric(12, 4), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_referral_rewards_referrer_user_id", "referral_rewards", ["referrer_user_id"])
    op.create_index("ix_referral_rewards_referrer_workspace_id", "referral_rewards", ["referrer_workspace_id"])
    with op.batch_alter_table("auth_codes") as batch:
        batch.add_column(sa.Column("referral_code", sa.String(24), nullable=True))


def downgrade():
    with op.batch_alter_table("auth_codes") as batch:
        batch.drop_column("referral_code")
    op.drop_table("referral_rewards")
    op.drop_table("referral_links")
