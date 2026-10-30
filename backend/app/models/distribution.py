from datetime import datetime
from decimal import Decimal

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, Numeric, String, Text, UniqueConstraint
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
