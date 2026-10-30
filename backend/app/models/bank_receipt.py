"""Verified merchant bank inflows and their one-to-one purchase allocation."""

from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, String, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, new_id, utcnow


class BankReceipt(Base, TimestampMixin):
    __tablename__ = "bank_receipts"
    __table_args__ = (UniqueConstraint("api_url", "transfer_id"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    api_url: Mapped[str] = mapped_column(String(200))
    transfer_id: Mapped[str] = mapped_column(String(100), index=True)
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    checkout_id: Mapped[str | None] = mapped_column(
        ForeignKey("checkouts.id", ondelete="SET NULL"), nullable=True, index=True
    )
    status: Mapped[str] = mapped_column(String(30), default="unmatched", index=True)
    matched_by: Mapped[str | None] = mapped_column(String(320), nullable=True)
    matched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
