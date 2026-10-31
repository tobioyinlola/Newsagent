"""Private payment proofs, finance decisions and durable notification delivery."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, new_id


class PaymentProof(Base, TimestampMixin):
    __tablename__ = "payment_proofs"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    checkout_id: Mapped[str] = mapped_column(ForeignKey("checkouts.id"), index=True)
    key: Mapped[str] = mapped_column(String(500), unique=True)
    filename: Mapped[str] = mapped_column(String(200))
    content_type: Mapped[str] = mapped_column(String(80))
    size_bytes: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    sha256: Mapped[str | None] = mapped_column(String(64), nullable=True)


class TransferReview(Base, TimestampMixin):
    __tablename__ = "transfer_reviews"
    __table_args__ = (UniqueConstraint("receiving_key", "payment_reference"),)
    checkout_id: Mapped[str] = mapped_column(ForeignKey("checkouts.id"), primary_key=True)
    proof_id: Mapped[str | None] = mapped_column(ForeignKey("payment_proofs.id"), nullable=True)
    status: Mapped[str] = mapped_column(String(24), default="awaiting_receipt", index=True)
    revision: Mapped[int] = mapped_column(Integer, default=0)
    submitted_by: Mapped[str | None] = mapped_column(String(320), nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reviewed_by: Mapped[str | None] = mapped_column(String(320), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reason: Mapped[str] = mapped_column(Text, default="")
    receiving_key: Mapped[str] = mapped_column(String(64))
    payment_reference: Mapped[str | None] = mapped_column(String(100), nullable=True)
    approved_proof_hash: Mapped[str | None] = mapped_column(String(64), nullable=True, unique=True)


class TransferMail(Base, TimestampMixin):
    __tablename__ = "transfer_mail"
    __table_args__ = (UniqueConstraint("checkout_id", "revision", "kind", "recipient"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    checkout_id: Mapped[str] = mapped_column(ForeignKey("checkouts.id"), index=True)
    revision: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(30))
    recipient: Mapped[str] = mapped_column(String(320))
    subject: Mapped[str] = mapped_column(String(300))
    body: Mapped[str] = mapped_column(Text)
    status: Mapped[str] = mapped_column(String(20), default="pending", index=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    last_attempt_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    sent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
