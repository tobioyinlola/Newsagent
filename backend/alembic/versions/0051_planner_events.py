"""Outlet planner events, to measure whether suggested plans help."""

import sqlalchemy as sa

from alembic import op

revision = "0051"
down_revision = "0050"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "planner_events",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("kind", sa.String(12), nullable=False),
        sa.Column("source", sa.String(14), nullable=False),
        sa.Column("plan_key", sa.String(10), nullable=False, server_default=""),
        sa.Column("outlets", sa.Integer, nullable=False, server_default="0"),
        sa.Column("credits", sa.Numeric(14, 4), nullable=False, server_default="0"),
        sa.Column("unchanged", sa.Boolean, nullable=True),
        sa.Column("workspace_id", sa.String(32), sa.ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=True),
    )
    op.create_index("ix_planner_events_created_at", "planner_events", ["created_at"])
    op.create_index("ix_planner_events_kind", "planner_events", ["kind"])
    op.create_index("ix_planner_events_workspace_id", "planner_events", ["workspace_id"])


def downgrade():
    op.drop_table("planner_events")
