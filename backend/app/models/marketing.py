"""Marketing email to our own users: who opted out, who must never be mailed, and a log of what was sent."""

from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, new_id, utcnow


class MarketingPref(Base, TimestampMixin):
    """One row per person we have marketed to (made on the first send). `token` is the secret in their unsubscribe link."""

    __tablename__ = "marketing_prefs"
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), primary_key=True)
    token: Mapped[str] = mapped_column(String(64), unique=True)
    opted_out_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    source: Mapped[str] = mapped_column(String(30), default="")  # link | one_click | operator


class MarketingSuppression(Base, TimestampMixin):
    """Addresses that must not get marketing mail whatever their preference says (hard bounce, spam complaint)."""

    __tablename__ = "marketing_suppressions"
    email: Mapped[str] = mapped_column(String(320), primary_key=True)
    reason: Mapped[str] = mapped_column(String(100), default="")


class MarketingSend(Base):
    """Every marketing email we sent or decided not to send. Drives the frequency cap, the daily cap, and "why did I get this?"."""

    __tablename__ = "marketing_sends"
    __table_args__ = (UniqueConstraint("idempotency_key"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), index=True)
    kind: Mapped[str] = mapped_column(String(30), default="")  # campaign | workflow | test
    ref: Mapped[str] = mapped_column(String(64), default="")  # the campaign or workflow it came from
    subject: Mapped[str] = mapped_column(Text, default="")
    status: Mapped[str] = mapped_column(String(10), index=True)  # sent | skipped | failed | dry_run
    skip_reason: Mapped[str] = mapped_column(String(40), default="")
    idempotency_key: Mapped[str | None] = mapped_column(
        String(120), nullable=True
    )  # a retry of the same send does nothing
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
