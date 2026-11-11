"""Marketing workflows: sequences of emails and waits, and each person's place in one."""

import sqlalchemy as sa

from alembic import op

revision = "0044"
down_revision = "0043"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "marketing_workflows",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("name", sa.String(120), nullable=False),
        sa.Column("status", sa.String(10), nullable=False, server_default="draft"),
        sa.Column("trigger_segment_id", sa.String(32), sa.ForeignKey("marketing_segments.id"), nullable=False),
        sa.Column("rules", sa.JSON, nullable=False),
        sa.Column("steps", sa.JSON, nullable=False),
        sa.Column("goal_segment_id", sa.String(32), sa.ForeignKey("marketing_segments.id"), nullable=True),
        sa.Column("goal_rules", sa.JSON, nullable=True),
        sa.Column("settings", sa.JSON, nullable=False),
        sa.Column("activated_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_by", sa.String(320), nullable=False, server_default=""),
        sa.Column("archived_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_marketing_workflows_status", "marketing_workflows", ["status"])
    op.create_table(
        "marketing_enrollments",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column(
            "workflow_id", sa.String(32), sa.ForeignKey("marketing_workflows.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("user_id", sa.String(32), sa.ForeignKey("users.id", ondelete="CASCADE"), nullable=False),
        sa.Column("status", sa.String(10), nullable=False, server_default="active"),
        sa.Column("exit_reason", sa.String(40), nullable=False, server_default=""),
        sa.Column("step_index", sa.Integer, nullable=False, server_default="0"),
        sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
        sa.Column("next_run_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("entered_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("finished_at", sa.DateTime(timezone=True), nullable=True),
        sa.UniqueConstraint("workflow_id", "user_id"),
    )
    op.create_index("ix_marketing_enrollments_workflow_id", "marketing_enrollments", ["workflow_id"])
    op.create_index("ix_marketing_enrollments_user_id", "marketing_enrollments", ["user_id"])
    op.create_index("ix_marketing_enrollments_next_run_at", "marketing_enrollments", ["next_run_at"])


def downgrade():
    op.drop_table("marketing_enrollments")
    op.drop_table("marketing_workflows")
