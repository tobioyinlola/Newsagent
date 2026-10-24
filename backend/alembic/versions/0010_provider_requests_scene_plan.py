"""provider requests, scene plan, job failure category

Revision ID: 0010
Revises: 0009
"""

import sqlalchemy as sa

from alembic import op

revision = "0010"
down_revision = "0009"
branch_labels = None
depends_on = None


def upgrade() -> None:
    op.create_table(
        "provider_requests",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("project_id", sa.String(length=32), nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("slot", sa.String(length=500), nullable=False),
        sa.Column("request_hash", sa.String(length=64), nullable=False),
        sa.Column("vendor_video_id", sa.String(length=200), nullable=True),
        sa.Column("status", sa.String(length=20), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("submitted_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("completed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("result", sa.JSON(), nullable=True),
        sa.Column("hold", sa.JSON(), nullable=True),
        sa.Column("error", sa.Text(), nullable=True),
        sa.Column("last_webhook_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.ForeignKeyConstraint(["project_id"], ["projects.id"]),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("project_id", "provider", "slot", "request_hash"),
    )
    op.create_index("ix_provider_requests_project_id", "provider_requests", ["project_id"])
    op.create_index("ix_provider_requests_vendor_video_id", "provider_requests", ["vendor_video_id"])
    op.create_table(
        "webhook_events",
        sa.Column("id", sa.String(length=32), nullable=False),
        sa.Column("provider", sa.String(length=50), nullable=False),
        sa.Column("event_id", sa.String(length=200), nullable=False),
        sa.Column("received_at", sa.DateTime(timezone=True), nullable=False),
        sa.PrimaryKeyConstraint("id"),
        sa.UniqueConstraint("provider", "event_id"),
    )
    op.add_column("projects", sa.Column("scene_plan", sa.JSON(), nullable=True))
    op.add_column("projects", sa.Column("scene_plan_hash", sa.String(length=64), nullable=True))
    op.add_column("projects", sa.Column("state_changed_at", sa.DateTime(timezone=True), nullable=True))
    op.add_column("jobs", sa.Column("failure_category", sa.String(length=20), nullable=True))


def downgrade() -> None:
    op.drop_column("jobs", "failure_category")
    op.drop_column("projects", "state_changed_at")
    op.drop_column("projects", "scene_plan_hash")
    op.drop_column("projects", "scene_plan")
    op.drop_table("webhook_events")
    op.drop_table("provider_requests")
