"""The durable line for presenter clips and renders (used only when QUEUE_MODE=dispatcher)."""

import sqlalchemy as sa

from alembic import op

revision = "0037"
down_revision = "0036"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "work_queue",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("project_id", sa.String(32), sa.ForeignKey("projects.id", ondelete="CASCADE"), nullable=False, unique=True),
        sa.Column("workspace_id", sa.String(32), nullable=False),
        sa.Column("lane", sa.String(20), nullable=False),
        sa.Column("step", sa.String(50), nullable=False),
        sa.Column("state", sa.String(10), nullable=False, server_default="waiting"),
        sa.Column("priority", sa.Integer, nullable=False, server_default="0"),
        sa.Column("enqueued_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("dispatched_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("attempts", sa.Integer, nullable=False, server_default="0"),
    )
    op.create_index("ix_work_queue_workspace_id", "work_queue", ["workspace_id"])
    op.create_index("ix_work_queue_line", "work_queue", ["lane", "state", "priority", "enqueued_at"])


def downgrade():
    op.drop_index("ix_work_queue_line", table_name="work_queue")
    op.drop_index("ix_work_queue_workspace_id", table_name="work_queue")
    op.drop_table("work_queue")
