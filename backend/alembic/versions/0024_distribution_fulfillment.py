"""Persist per-outlet fulfilment, notification outbox and activity history."""

import uuid

import sqlalchemy as sa

from alembic import op

revision = "0024"
down_revision = "0023"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "distribution_placements",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column(
            "request_id", sa.String(32), sa.ForeignKey("distribution_requests.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column("outlet_id", sa.String(32), nullable=False),
        sa.Column("data", sa.JSON(), nullable=False),
        sa.Column("status", sa.String(30), nullable=False),
        sa.Column("internal_status", sa.String(30), nullable=False),
        sa.Column("internal_notes", sa.Text(), nullable=False),
        sa.Column("published_url", sa.String(2000), nullable=False),
        sa.Column("published_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("contact_email", sa.String(320), nullable=False),
        sa.Column("outreach_subject", sa.String(300), nullable=False),
        sa.Column("outreach_body", sa.Text(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("request_id", "outlet_id"),
    )
    op.create_index("ix_distribution_placements_request_id", "distribution_placements", ["request_id"])
    op.create_table(
        "distribution_mail",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column(
            "request_id", sa.String(32), sa.ForeignKey("distribution_requests.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "placement_id",
            sa.String(32),
            sa.ForeignKey("distribution_placements.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("dedupe_key", sa.String(250), nullable=False, unique=True),
        sa.Column("kind", sa.String(30), nullable=False),
        sa.Column("recipient", sa.String(320), nullable=False),
        sa.Column("subject", sa.String(300), nullable=False),
        sa.Column("body", sa.Text(), nullable=False),
        sa.Column("status", sa.String(20), nullable=False),
        sa.Column("attempts", sa.Integer(), nullable=False),
        sa.Column("claimed_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("claim_token", sa.String(32), nullable=True),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("error", sa.String(300), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_distribution_mail_request_id", "distribution_mail", ["request_id"])
    op.create_table(
        "distribution_activity",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column(
            "request_id", sa.String(32), sa.ForeignKey("distribution_requests.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "placement_id",
            sa.String(32),
            sa.ForeignKey("distribution_placements.id", ondelete="CASCADE"),
            nullable=True,
        ),
        sa.Column("actor", sa.String(320), nullable=False),
        sa.Column("kind", sa.String(40), nullable=False),
        sa.Column("detail", sa.JSON(), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_distribution_activity_request_id", "distribution_activity", ["request_id"])

    # Backfill existing paid orders without triggering any historical emails or publisher outreach.
    bind = op.get_bind()
    requests = sa.table(
        "distribution_requests",
        sa.column("id", sa.String()),
        sa.column("data", sa.JSON()),
        sa.column("status", sa.String()),
        sa.column("paid_at", sa.DateTime(timezone=True)),
    )
    placements = sa.Table("distribution_placements", sa.MetaData(), autoload_with=bind)
    for request in bind.execute(sa.select(requests).where(requests.c.paid_at.is_not(None))).mappings():
        for outlet in request["data"].get("outlets", []):
            line = {
                **outlet,
                "base_credits": outlet["credits"],
                "logo_fee": "0",
                "picture_fee": "0",
                "logo_key": request["data"].get("logo_key"),
                "picture_keys": request["data"].get("picture_keys", []),
            }
            bind.execute(
                placements.insert().values(
                    id=uuid.uuid4().hex,
                    request_id=request["id"],
                    outlet_id=outlet["id"],
                    data=line,
                    status={"submitted": "pending", "in_progress": "in_progress", "completed": "published"}.get(
                        request["status"], "pending"
                    ),
                    internal_status="not_started",
                    internal_notes="Legacy request; publisher contact and publication URL may need to be added.",
                    published_url="",
                    published_at=None,
                    contact_email="",
                    outreach_subject="",
                    outreach_body="",
                    created_at=request["paid_at"],
                    updated_at=request["paid_at"],
                )
            )


def downgrade():
    op.drop_table("distribution_activity")
    op.drop_table("distribution_mail")
    op.drop_table("distribution_placements")
