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


class SiteVisitMark(Base):
    """One per visitor per day, so the same visitor isn't counted twice in a day. `visitor_hash` is a one-way code that changes every day
    (made from the day, a secret, the IP address and the browser): the IP address itself is never stored, and the code can't be followed
    from one day to the next. Removed after two days."""

    __tablename__ = "site_visit_marks"
    __table_args__ = (UniqueConstraint("day", "visitor_hash"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    day: Mapped[date] = mapped_column(Date, index=True)
    visitor_hash: Mapped[str] = mapped_column(String(64))


class SiteDaily(Base):
    """Website totals for a day: visitors (each counted once that day) and page views."""

    __tablename__ = "site_daily"
    day: Mapped[date] = mapped_column(Date, primary_key=True)
    visitors: Mapped[int] = mapped_column(BigInteger, default=0)
    pageviews: Mapped[int] = mapped_column(BigInteger, default=0)


class SitePageDaily(Base):
    __tablename__ = "site_page_daily"
    __table_args__ = (UniqueConstraint("day", "path"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    day: Mapped[date] = mapped_column(Date, index=True)
    path: Mapped[str] = mapped_column(String(120))
    views: Mapped[int] = mapped_column(BigInteger, default=0)


class SiteSourceDaily(Base):
    """Where each day's visitors came from. `source`: direct, search, social, email, referral, other. `detail`: the search engine,
    social network, website, or (for our own emails) the campaign."""

    __tablename__ = "site_source_daily"
    __table_args__ = (UniqueConstraint("day", "source", "detail"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    day: Mapped[date] = mapped_column(Date, index=True)
    source: Mapped[str] = mapped_column(String(20))
    detail: Mapped[str] = mapped_column(String(100), default="")
    visitors: Mapped[int] = mapped_column(BigInteger, default=0)
