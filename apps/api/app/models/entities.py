from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, new_id

Money = Numeric(12, 4)


class Workspace(Base, TimestampMixin):
    __tablename__ = "workspaces"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(200))
    region: Mapped[str] = mapped_column(String(50), default="NG")
    plan: Mapped[str] = mapped_column(String(50), default="pilot")
    brand_kit_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    credit_balance: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"))
    spend_cap: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"))  # lifetime/period cap
    spent_total: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"))
    max_videos_per_day: Mapped[int] = mapped_column(Integer, default=3)
    max_video_seconds: Mapped[int] = mapped_column(Integer, default=300)
    suspended: Mapped[bool] = mapped_column(Boolean, default=False)
    share_disabled: Mapped[bool] = mapped_column(Boolean, default=False)


class Invite(Base, TimestampMixin):
    __tablename__ = "invites"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(String(320))
    code: Mapped[str] = mapped_column(String(64), unique=True)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"))
    used_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))


class User(Base, TimestampMixin):
    __tablename__ = "users"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(String(320), unique=True)
    role: Mapped[str] = mapped_column(String(20), default="owner")
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"))


class BrandKit(Base, TimestampMixin):
    __tablename__ = "brand_kits"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"))
    version: Mapped[int] = mapped_column(Integer, default=1)
    logo_light_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    logo_dark_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    primary_color: Mapped[str] = mapped_column(String(9), default="#0B3D91")
    accent_color: Mapped[str] = mapped_column(String(9), default="#F5A623")
    secondary_colors: Mapped[list] = mapped_column(JSON, default=list)
    fonts: Mapped[dict] = mapped_column(JSON, default=dict)
    pronunciation_glossary: Mapped[dict] = mapped_column(JSON, default=dict)
    tone: Mapped[str] = mapped_column(String(50), default="confident")
    source_url: Mapped[str | None] = mapped_column(String(500), nullable=True)


class Project(Base, TimestampMixin):
    __tablename__ = "projects"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    state: Mapped[str] = mapped_column(String(32), default="draft")
    region: Mapped[str] = mapped_column(String(50), default="NG")
    anchor_id: Mapped[str | None] = mapped_column(String(100), nullable=True)
    voice_accent: Mapped[str] = mapped_column(String(50), default="british")
    studio_id: Mapped[str] = mapped_column(String(50), default="default")
    layout: Mapped[str] = mapped_column(String(30), default="pip")
    accent_override: Mapped[str | None] = mapped_column(String(9), nullable=True)
    cost_total: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"))
    failure_reason: Mapped[str | None] = mapped_column(Text, nullable=True)
    failure_retryable: Mapped[bool] = mapped_column(Boolean, default=False)
    failed_from: Mapped[str | None] = mapped_column(String(32), nullable=True)

    brief: Mapped["Brief | None"] = relationship(uselist=False, lazy="selectin")


class Brief(Base):
    __tablename__ = "briefs"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), unique=True)
    raw_text: Mapped[str] = mapped_column(Text)
    structured_facts: Mapped[dict] = mapped_column(JSON, default=dict)
    website_url: Mapped[str | None] = mapped_column(String(500), nullable=True)


class ScriptVersion(Base, TimestampMixin):
    __tablename__ = "script_versions"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    version: Mapped[int] = mapped_column(Integer, default=1)
    segments: Mapped[list] = mapped_column(JSON, default=list)
    ticker_lines: Mapped[list] = mapped_column(JSON, default=list)
    lower_thirds: Mapped[list] = mapped_column(JSON, default=list)
    interview_questions: Mapped[list] = mapped_column(JSON, default=list)
    claim_flags: Mapped[list] = mapped_column(JSON, default=list)
    approved: Mapped[bool] = mapped_column(Boolean, default=False)
    approved_by: Mapped[str | None] = mapped_column(String(320), nullable=True)
    approved_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Asset(Base, TimestampMixin):
    __tablename__ = "assets"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    type: Mapped[str] = mapped_column(String(30))  # anchor, founder_take, overlay, render, caption, thumbnail
    storage_key: Mapped[str] = mapped_column(String(500))
    format: Mapped[str | None] = mapped_column(String(20), nullable=True)  # 16x9 / 9x16
    duration: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    hash: Mapped[str | None] = mapped_column(String(64), nullable=True)


class InterviewSession(Base, TimestampMixin):
    __tablename__ = "interview_sessions"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    founder_name: Mapped[str] = mapped_column(String(200), default="")
    expiry: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    question_status: Mapped[dict] = mapped_column(JSON, default=dict)
    consent_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class Job(Base, TimestampMixin):
    __tablename__ = "jobs"
    __table_args__ = (UniqueConstraint("project_id", "stage", "input_hash"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    stage: Mapped[str] = mapped_column(String(50))
    vendor: Mapped[str | None] = mapped_column(String(50), nullable=True)
    input_hash: Mapped[str] = mapped_column(String(64))
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending|running|succeeded|failed
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    started_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    cost: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"))
    duration_s: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)


class VendorBudget(Base):
    __tablename__ = "vendor_budgets"
    __table_args__ = (UniqueConstraint("vendor", "period"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    vendor: Mapped[str] = mapped_column(String(50))
    period: Mapped[str] = mapped_column(String(7))  # YYYY-MM
    limit: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"))
    spent: Mapped[Decimal] = mapped_column(Money, default=Decimal("0"))
    alerted_80: Mapped[bool] = mapped_column(Boolean, default=False)


class ShareLink(Base, TimestampMixin):
    __tablename__ = "share_links"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
