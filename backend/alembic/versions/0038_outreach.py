"""AI outreach to distribution outlets: conversations, their messages, opt-outs (used only when OUTREACH_AI=on)."""

import sqlalchemy as sa

from alembic import op

revision = "0038"
down_revision = "0037"
branch_labels = None
depends_on = None


def upgrade():
    op.create_table(
        "outreach_threads",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column(
            "request_id", sa.String(32), sa.ForeignKey("distribution_requests.id", ondelete="CASCADE"), nullable=False
        ),
        sa.Column(
            "placement_id",
            sa.String(32),
            sa.ForeignKey("distribution_placements.id", ondelete="CASCADE"),
            nullable=False,
            unique=True,
        ),
        sa.Column("outlet_id", sa.String(32), nullable=False),
        sa.Column("outlet_name", sa.String(200), nullable=False, server_default=""),
        sa.Column("contact_name", sa.String(200), nullable=False, server_default=""),
        sa.Column("contact_email", sa.String(320), nullable=False),
        sa.Column("template_id", sa.String(40), nullable=False, server_default=""),
        sa.Column("reply_token", sa.String(40), nullable=False, unique=True),
        sa.Column("status", sa.String(30), nullable=False, server_default="awaiting_reply"),
        sa.Column("ai_paused", sa.Boolean, nullable=False, server_default=sa.false()),
        sa.Column("ai_turns", sa.Integer, nullable=False, server_default="0"),
        sa.Column("facts", sa.JSON, nullable=False),
        sa.Column("last_inbound_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("last_outbound_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("updated_at", sa.DateTime(timezone=True), nullable=False),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.create_index("ix_outreach_threads_request_id", "outreach_threads", ["request_id"])
    op.create_index("ix_outreach_threads_contact_email", "outreach_threads", ["contact_email"])
    op.create_index("ix_outreach_threads_status", "outreach_threads", ["status"])
    op.create_table(
        "outreach_messages",
        sa.Column("id", sa.String(32), primary_key=True),
        sa.Column("thread_id", sa.String(32), sa.ForeignKey("outreach_threads.id", ondelete="CASCADE"), nullable=False),
        sa.Column("direction", sa.String(3), nullable=False),
        sa.Column("kind", sa.String(20), nullable=False, server_default="human"),
        sa.Column("status", sa.String(20), nullable=False, server_default="received"),
        sa.Column("subject", sa.String(300), nullable=False, server_default=""),
        sa.Column("body", sa.Text, nullable=False, server_default=""),
        sa.Column("message_id", sa.String(300), nullable=True),
        sa.Column("in_reply_to", sa.String(300), nullable=True),
        sa.Column("mail_id", sa.String(32), nullable=True),
        sa.Column("sender", sa.String(320), nullable=False, server_default=""),
        sa.Column("ai", sa.JSON, nullable=False),
        sa.Column("actor", sa.String(320), nullable=False, server_default=""),
        sa.Column("sent_at", sa.DateTime(timezone=True), nullable=True),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
        sa.UniqueConstraint("thread_id", "message_id"),
    )
    op.create_index("ix_outreach_messages_thread_id", "outreach_messages", ["thread_id"])
    op.create_table(
        "outreach_optouts",
        sa.Column("email", sa.String(320), primary_key=True),
        sa.Column("reason", sa.String(300), nullable=False, server_default=""),
        sa.Column("created_at", sa.DateTime(timezone=True), nullable=False),
    )
    op.add_column("distribution_mail", sa.Column("thread_id", sa.String(32), nullable=True))
    op.add_column("distribution_mail", sa.Column("reply_to", sa.String(320), nullable=True))
    op.add_column("distribution_mail", sa.Column("message_id", sa.String(300), nullable=True))
    op.add_column("distribution_mail", sa.Column("in_reply_to", sa.String(300), nullable=True))


def downgrade():
    for col in ("in_reply_to", "message_id", "reply_to", "thread_id"):
        op.drop_column("distribution_mail", col)
    op.drop_table("outreach_optouts")
    op.drop_index("ix_outreach_messages_thread_id", table_name="outreach_messages")
    op.drop_table("outreach_messages")
    for ix in ("ix_outreach_threads_status", "ix_outreach_threads_contact_email", "ix_outreach_threads_request_id"):
        op.drop_index(ix, table_name="outreach_threads")
    op.drop_table("outreach_threads")
