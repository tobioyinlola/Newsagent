"""What happens to the outlet planner, for measuring whether it helps. Nothing here identifies a visitor: a public event carries no
workspace, no address and no cookie, and a signed-in one carries only its workspace (erased with it)."""

from datetime import datetime
from decimal import Decimal

from sqlalchemy import Boolean, DateTime, ForeignKey, Integer, Numeric, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, new_id, utcnow


class PlannerEvent(Base):
    __tablename__ = "planner_events"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    # shown (made for them without asking) | asked (they pressed the button) | used (they chose a plan) |
    # continued (took a plan on to create an account) | submitted (a request was paid for after using a plan)
    kind: Mapped[str] = mapped_column(String(12), index=True)
    source: Mapped[str] = mapped_column(String(14))  # public | request | ready_prompt | email
    plan_key: Mapped[str] = mapped_column(String(10), default="", server_default="")
    outlets: Mapped[int] = mapped_column(Integer, default=0)
    credits: Mapped[Decimal] = mapped_column(Numeric(14, 4), default=Decimal(0))
    unchanged: Mapped[bool | None] = mapped_column(Boolean, nullable=True)  # submitted: exactly the outlets the plan suggested
    workspace_id: Mapped[str | None] = mapped_column(ForeignKey("workspaces.id", ondelete="CASCADE"), nullable=True, index=True)
