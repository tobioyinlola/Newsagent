from datetime import datetime
from decimal import Decimal

from sqlalchemy import JSON, Boolean, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, new_id, utcnow


class DistributionRequest(Base, TimestampMixin):
    __tablename__ = "distribution_requests"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    created_by: Mapped[str] = mapped_column(String(320))
    status: Mapped[str] = mapped_column(String(30), default="draft")
    stage: Mapped[str] = mapped_column(String(30), default="outlets")
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    total_credits: Mapped[Decimal] = mapped_column(Numeric(12, 4), default=Decimal("0"))
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    email_sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class DistributionPlacement(Base, TimestampMixin):
    __tablename__ = "distribution_placements"
    __table_args__ = (UniqueConstraint("request_id", "outlet_id"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    request_id: Mapped[str] = mapped_column(ForeignKey("distribution_requests.id", ondelete="CASCADE"), index=True)
    outlet_id: Mapped[str] = mapped_column(String(32))
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    status: Mapped[str] = mapped_column(String(30), default="pending")
    internal_status: Mapped[str] = mapped_column(String(30), default="not_started")
    internal_notes: Mapped[str] = mapped_column(Text, default="")
    published_url: Mapped[str] = mapped_column(String(2000), default="")
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    contact_email: Mapped[str] = mapped_column(String(320), default="")
    cc_emails: Mapped[list] = mapped_column(JSON, default=list)  # the outlet's other contacts, copied on every email
    # "" (not applicable) | needs_contact (nobody to write to yet) | waiting_mailbox (no mailbox connected yet) | started | skipped
    outreach_state: Mapped[str] = mapped_column(String(20), default="", server_default="", index=True)
    outreach_subject: Mapped[str] = mapped_column(String(300), default="")
    outreach_body: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class DistributionMail(Base, TimestampMixin):
    __tablename__ = "distribution_mail"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    request_id: Mapped[str] = mapped_column(ForeignKey("distribution_requests.id", ondelete="CASCADE"), index=True)
    placement_id: Mapped[str | None] = mapped_column(
        ForeignKey("distribution_placements.id", ondelete="CASCADE"), nullable=True
    )
    dedupe_key: Mapped[str] = mapped_column(String(250), unique=True)
    kind: Mapped[str] = mapped_column(String(30))
    recipient: Mapped[str] = mapped_column(String(320))
    subject: Mapped[str] = mapped_column(String(300))
    body: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    claimed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    claim_token: Mapped[str | None] = mapped_column(String(32), nullable=True)
    thread_id: Mapped[str | None] = mapped_column(String(32), nullable=True)  # an outreach conversation this mail belongs to
    reply_to: Mapped[str | None] = mapped_column(String(320), nullable=True)  # where the outlet's reply should come back to
    cc: Mapped[list] = mapped_column(JSON, default=list)  # copied on this email
    message_id: Mapped[str | None] = mapped_column(String(300), nullable=True)  # the RFC Message-ID it is sent with
    in_reply_to: Mapped[str | None] = mapped_column(String(300), nullable=True)
    send_after: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)  # not before this time (outreach waits a while, like a person would)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    error: Mapped[str] = mapped_column(String(300), default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class DistributionActivity(Base):
    __tablename__ = "distribution_activity"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    request_id: Mapped[str] = mapped_column(ForeignKey("distribution_requests.id", ondelete="CASCADE"), index=True)
    placement_id: Mapped[str | None] = mapped_column(
        ForeignKey("distribution_placements.id", ondelete="CASCADE"), nullable=True
    )
    actor: Mapped[str] = mapped_column(String(320))
    kind: Mapped[str] = mapped_column(String(40))
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class DistributionPackage(Base, TimestampMixin):
    """A ready-made media package: a named bundle of outlets (or services) sold at one price. Editable from the admin."""

    __tablename__ = "distribution_packages"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    slug: Mapped[str] = mapped_column(String(80), unique=True)
    kind: Mapped[str] = mapped_column(String(20), default="regional")  # regional | organisation | campaign
    region: Mapped[str] = mapped_column(String(30), default="", index=True)
    campaign: Mapped[str] = mapped_column(String(20), default="")  # black_friday | cyber_monday | ""
    name: Mapped[str] = mapped_column(String(200))
    usd_price: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)  # none = a custom quote, not sold in the app
    standard_usd: Mapped[Decimal | None] = mapped_column(Numeric(12, 2), nullable=True)  # the usual price, for "33% off"
    local_prices: Mapped[dict] = mapped_column(JSON, default=dict)  # {"NGN": "912203.49"}: shown beside the price, never charged
    outlet_names: Mapped[list] = mapped_column(JSON, default=list)  # as promised to the customer
    outlet_ids: Mapped[list] = mapped_column(JSON, default=list)  # the ones we hold in the outlet catalogue (we write to these)
    includes: Mapped[list] = mapped_column(JSON, default=list)  # what else comes with it
    ideal_for: Mapped[str] = mapped_column(String(400), default="")
    note: Mapped[str] = mapped_column(String(600), default="")
    slots_total: Mapped[int | None] = mapped_column(Integer, nullable=True)  # none = no limit
    slots_taken: Mapped[int] = mapped_column(Integer, default=0)
    starts_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ends_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    sort: Mapped[int] = mapped_column(Integer, default=0)
