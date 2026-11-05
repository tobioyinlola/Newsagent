from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, new_id, utcnow


class OutreachThread(Base, TimestampMixin):
    """One conversation with one outlet about one placement."""

    __tablename__ = "outreach_threads"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    request_id: Mapped[str] = mapped_column(ForeignKey("distribution_requests.id", ondelete="CASCADE"), index=True)
    placement_id: Mapped[str] = mapped_column(ForeignKey("distribution_placements.id", ondelete="CASCADE"), unique=True)
    outlet_id: Mapped[str] = mapped_column(String(32))
    outlet_name: Mapped[str] = mapped_column(String(200), default="")
    contact_name: Mapped[str] = mapped_column(String(200), default="")
    contact_email: Mapped[str] = mapped_column(String(320), index=True)
    template_id: Mapped[str] = mapped_column(String(40), default="")
    reply_token: Mapped[str] = mapped_column(String(40), unique=True)  # the secret in outreach+<token>@domain
    # awaiting_reply | replied | needs_approval | agreed | closed | do_not_contact
    status: Mapped[str] = mapped_column(String(30), default="awaiting_reply", index=True)
    ai_paused: Mapped[bool] = mapped_column(default=False)  # an operator took over: the agent stays out
    ai_turns: Mapped[int] = mapped_column(Integer, default=0)
    facts: Mapped[dict] = mapped_column(
        JSON, default=dict
    )  # what the agent understood (quote, deadline, ...); account details are encrypted inside
    last_inbound_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    last_outbound_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class OutreachMessage(Base, TimestampMixin):
    __tablename__ = "outreach_messages"
    __table_args__ = (UniqueConstraint("thread_id", "message_id"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    thread_id: Mapped[str] = mapped_column(ForeignKey("outreach_threads.id", ondelete="CASCADE"), index=True)
    direction: Mapped[str] = mapped_column(String(3))  # out | in
    kind: Mapped[str] = mapped_column(String(20), default="human")  # template | ai_auto | ai_draft | human | received
    status: Mapped[str] = mapped_column(
        String(20), default="received"
    )  # draft | pending_approval | queued | sent | failed | received | ignored | discarded
    subject: Mapped[str] = mapped_column(String(300), default="")
    body: Mapped[str] = mapped_column(Text, default="")
    message_id: Mapped[str | None] = mapped_column(String(300), nullable=True)  # the RFC Message-ID
    in_reply_to: Mapped[str | None] = mapped_column(String(300), nullable=True)
    mail_id: Mapped[str | None] = mapped_column(String(32), nullable=True)  # the outbox row that carries it
    sender: Mapped[str] = mapped_column(String(320), default="")
    ai: Mapped[dict] = mapped_column(JSON, default=dict)  # intent, confidence, why it was held
    actor: Mapped[str] = mapped_column(
        String(320), default=""
    )  # who wrote or approved it (an operator's email, or "ai")
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class OutreachOptout(Base, TimestampMixin):
    """People who asked us to stop. Never emailed again."""

    __tablename__ = "outreach_optouts"
    email: Mapped[str] = mapped_column(String(320), primary_key=True)
    reason: Mapped[str] = mapped_column(String(300), default="")
