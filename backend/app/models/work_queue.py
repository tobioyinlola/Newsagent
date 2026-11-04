from datetime import datetime

from sqlalchemy import DateTime, ForeignKey, Index, Integer, String
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, new_id, utcnow


class WorkItem(Base):
    """One video's place in the line for slow, capacity-limited work (presenter clips and renders). The table is the single
    source of truth for order: nothing is lost on a restart, and a video keeps its original place across retries and steps."""

    __tablename__ = "work_queue"
    __table_args__ = (Index("ix_work_queue_line", "lane", "state", "priority", "enqueued_at"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), unique=True)
    workspace_id: Mapped[str] = mapped_column(String(32), index=True)
    lane: Mapped[str] = mapped_column(String(20))  # avatar | render
    step: Mapped[str] = mapped_column(String(50))
    state: Mapped[str] = mapped_column(String(10), default="waiting")  # waiting | running
    priority: Mapped[int] = mapped_column(Integer, default=0)  # an operator can move a video to the front
    enqueued_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    dispatched_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    attempts: Mapped[int] = mapped_column(Integer, default=0)
