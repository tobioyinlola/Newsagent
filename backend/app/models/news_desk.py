from datetime import datetime

from sqlalchemy import JSON, DateTime, ForeignKey, Integer, String, Text, UniqueConstraint
from sqlalchemy.orm import Mapped, mapped_column

from app.models.base import Base, TimestampMixin, new_id, utcnow


class NewsStory(Base, TimestampMixin):
    __tablename__ = "news_desk_stories"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    slug: Mapped[str] = mapped_column(String(100), unique=True)
    status: Mapped[str] = mapped_column(String(20), default="draft", index=True)
    revision: Mapped[int] = mapped_column(Integer, default=1)
    data: Mapped[dict] = mapped_column(JSON, default=dict)
    published_data: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    created_by: Mapped[str] = mapped_column(String(320))
    updated_by: Mapped[str] = mapped_column(String(320))
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
    published_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True, index=True)


class NewsImage(Base, TimestampMixin):
    __tablename__ = "news_desk_images"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    story_id: Mapped[str] = mapped_column(ForeignKey("news_desk_stories.id"), index=True)
    key: Mapped[str] = mapped_column(String(500), unique=True)
    content_type: Mapped[str] = mapped_column(String(80))
    size_bytes: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default="pending")
    filename: Mapped[str] = mapped_column(Text)


class NewsVideo(Base, TimestampMixin):
    """A standalone editorial render. Never joins customer Projects, Jobs or wallet ledgers."""

    __tablename__ = "news_desk_videos"
    __table_args__ = (UniqueConstraint("story_id", "story_revision"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    story_id: Mapped[str] = mapped_column(ForeignKey("news_desk_stories.id"), index=True)
    story_revision: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(30), default="queued", index=True)
    snapshot: Mapped[dict] = mapped_column(JSON)
    progress: Mapped[int] = mapped_column(Integer, default=0)
    provider_name: Mapped[str] = mapped_column(String(40), default="")
    provider_id: Mapped[str] = mapped_column(String(200), default="")
    renderer_id: Mapped[str] = mapped_column(String(100), default="")
    media: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str] = mapped_column(Text, default="")
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)
