"""Anonymous daily platform measurements and publisher-reported cumulative snapshots."""

from datetime import date, datetime

from sqlalchemy import BigInteger, Date, DateTime, ForeignKey, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, new_id, utcnow


class AudienceEvent(Base):
    __tablename__ = "audience_events"
    __table_args__ = (UniqueConstraint("project_id", "day", "kind", "session_hash"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    day: Mapped[date] = mapped_column(Date, index=True)
    kind: Mapped[str] = mapped_column(String(30))
    session_hash: Mapped[str] = mapped_column(String(64))


class AudienceDaily(Base):
    __tablename__ = "audience_daily"
    __table_args__ = (UniqueConstraint("project_id", "day"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id", ondelete="CASCADE"), index=True)
    day: Mapped[date] = mapped_column(Date, index=True)
    impressions: Mapped[int] = mapped_column(BigInteger, default=0)
    story_visits: Mapped[int] = mapped_column(BigInteger, default=0)
    share_visits: Mapped[int] = mapped_column(BigInteger, default=0)
    video_views: Mapped[int] = mapped_column(BigInteger, default=0)
    video_completions: Mapped[int] = mapped_column(BigInteger, default=0)


class PublisherSnapshot(Base):
    __tablename__ = "publisher_snapshots"
    __table_args__ = (UniqueConstraint("placement_id", "as_of"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    request_id: Mapped[str] = mapped_column(ForeignKey("distribution_requests.id", ondelete="CASCADE"), index=True)
    placement_id: Mapped[str] = mapped_column(ForeignKey("distribution_placements.id", ondelete="CASCADE"), index=True)
    project_id: Mapped[str | None] = mapped_column(
        ForeignKey("projects.id", ondelete="SET NULL"), nullable=True, index=True
    )
    as_of: Mapped[date] = mapped_column(Date)
    views: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    impressions: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    source_note: Mapped[str] = mapped_column(Text, default="")
    updated_by: Mapped[str] = mapped_column(String(320))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
