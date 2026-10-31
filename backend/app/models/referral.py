"""Per-user public referral codes and the one-time rewards for verified new businesses."""

from decimal import Decimal

from sqlalchemy import ForeignKey, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, new_id


class ReferralLink(Base, TimestampMixin):
    __tablename__ = "referral_links"
    code: Mapped[str] = mapped_column(String(24), primary_key=True)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id", ondelete="CASCADE"), unique=True)


class ReferralReward(Base, TimestampMixin):
    __tablename__ = "referral_rewards"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    referrer_user_id: Mapped[str | None] = mapped_column(
        ForeignKey("users.id", ondelete="SET NULL"), nullable=True, index=True
    )
    referrer_workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    referred_user_id: Mapped[str | None] = mapped_column(ForeignKey("users.id", ondelete="SET NULL"), nullable=True)
    referred_workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), unique=True)
    credits: Mapped[Decimal] = mapped_column(Numeric(12, 4), default=Decimal("1"))
