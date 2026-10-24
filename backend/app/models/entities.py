from datetime import datetime
from decimal import Decimal

from sqlalchemy import (
    JSON,
    Boolean,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Numeric,
    String,
    Text,
    UniqueConstraint,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.models.base import Base, TimestampMixin, new_id, utcnow

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
    low_balance_alerted: Mapped[bool] = mapped_column(Boolean, default=False)
    deleted_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )  # tombstone: ledger is kept


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
    last_login_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    password_hash: Mapped[str | None] = mapped_column(Text, nullable=True)  # scrypt; None until the user sets one


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
    interview_enabled: Mapped[bool] = mapped_column(Boolean, default=False)
    # "invite": a founder records from a private link after the anchor is made. "live": the owner is interviewed by the
    # AI interviewer on the dashboard BEFORE anything paid runs, then the anchor and the merge follow.
    interview_mode: Mapped[str] = mapped_column(String(10), default="invite")
    founder_name: Mapped[str] = mapped_column(String(200), default="")  # who the AI interviewer greets by name
    founder_title: Mapped[str] = mapped_column(String(200), default="")
    keep_raw_takes: Mapped[bool] = mapped_column(Boolean, default=False)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    merge_plan: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # owner's layout/order/trim/drop choices
    # the validated scene plan the last render was built from (asset keys, never signed URLs), and its content hash
    scene_plan: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    scene_plan_hash: Mapped[str | None] = mapped_column(String(64), nullable=True)
    state_changed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # product footage the owner chose to show: [{key, caption, seconds, synthetic}] (brand assets or generated clips)
    broll: Mapped[list | None] = mapped_column(JSON, nullable=True)

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
    consent_version: Mapped[str | None] = mapped_column(String(20), nullable=True)
    founder_title: Mapped[str] = mapped_column(String(200), default="")
    founder_email: Mapped[str | None] = mapped_column(String(320), nullable=True)
    invited_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    reminders_sent: Mapped[int] = mapped_column(Integer, default=0)
    last_reminder_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    # Encrypted copy of the raw token so reminder emails can re-send the same link. Cleared once the
    # session is submitted, revoked or expired. Lookups always use token_hash.
    token_enc: Mapped[str | None] = mapped_column(Text, nullable=True)
    photo_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    mode: Mapped[str] = mapped_column(String(10), default="invite")  # invite | live (AI interviewer on the dashboard)


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
    failure_category: Mapped[str | None] = mapped_column(String(20), nullable=True)  # see integrations/errors.py


class ProviderRequest(Base, TimestampMixin):
    """One paid generation at a vendor, written the moment it is submitted. A crash, retry or duplicate delivery finds
    this row and resumes polling the same vendor id instead of paying for a second video."""

    __tablename__ = "provider_requests"
    __table_args__ = (UniqueConstraint("project_id", "provider", "slot", "request_hash"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    provider: Mapped[str] = mapped_column(String(50))
    slot: Mapped[str] = mapped_column(String(500))  # which clip this is for (its storage key)
    request_hash: Mapped[str] = mapped_column(String(64))
    vendor_video_id: Mapped[str | None] = mapped_column(String(200), nullable=True, index=True)
    status: Mapped[str] = mapped_column(String(20), default="new")  # new | submitted | completed | failed
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    submitted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    completed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    result: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # video_url, duration_s, cost
    hold: Mapped[dict | None] = mapped_column(JSON, nullable=True)  # the credit hold made for this job, until settled
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    last_webhook_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class WebhookEvent(Base):
    """Every provider callback we acted on, so a duplicate delivery is recognised and ignored."""

    __tablename__ = "webhook_events"
    __table_args__ = (UniqueConstraint("provider", "event_id"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    provider: Mapped[str] = mapped_column(String(50))
    event_id: Mapped[str] = mapped_column(String(200))
    received_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


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


class BrandAsset(Base, TimestampMixin):
    """A file the workspace uploaded for its brand. Only status="clean" files may be used."""

    __tablename__ = "brand_assets"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    key: Mapped[str] = mapped_column(String(500), unique=True)
    kind: Mapped[str] = mapped_column(String(30))  # logo_light, logo_dark, guide_pdf, product_image
    content_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending | clean | rejected
    duration_s: Mapped[float | None] = mapped_column(Float, nullable=True)  # product videos only
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)


class PresenterClip(Base, TimestampMixin):
    """A clip of a TV-style presenter the operator uploaded. Merged videos mix these in around the AI presenter."""

    __tablename__ = "presenter_clips"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    title: Mapped[str] = mapped_column(String(200))
    role: Mapped[str] = mapped_column(String(20))  # intro | cutaway | outro
    key: Mapped[str] = mapped_column(String(500), unique=True)
    content_type: Mapped[str] = mapped_column(String(100))
    size_bytes: Mapped[int] = mapped_column(Integer)
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending | clean | rejected
    active: Mapped[bool] = mapped_column(Boolean, default=True)
    duration_s: Mapped[float | None] = mapped_column(Float, nullable=True)
    width: Mapped[int | None] = mapped_column(Integer, nullable=True)
    height: Mapped[int | None] = mapped_column(Integer, nullable=True)
    has_audio: Mapped[bool] = mapped_column(Boolean, default=False)
    rights_confirmed_by: Mapped[str] = mapped_column(String(320))  # the operator who confirmed the rights
    rights_confirmed_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class Take(Base, TimestampMixin):
    """One recording attempt for one interview question. Chunks upload straight to storage and resume by index."""

    __tablename__ = "takes"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    session_id: Mapped[str] = mapped_column(ForeignKey("interview_sessions.id"), index=True)
    project_id: Mapped[str] = mapped_column(ForeignKey("projects.id"), index=True)
    question_index: Mapped[int] = mapped_column(Integer)
    kind: Mapped[str] = mapped_column(String(10), default="video")  # video | audio
    ext: Mapped[str] = mapped_column(String(5), default="webm")
    # recording -> uploaded -> processing -> ready | needs_retake | failed ; superseded when retaken
    status: Mapped[str] = mapped_column(String(20), default="recording")
    chunks: Mapped[dict] = mapped_column(JSON, default=dict)  # {"0": size_bytes, ...} confirmed by the server
    processed_video_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    processed_audio_key: Mapped[str | None] = mapped_column(String(500), nullable=True)
    duration_s: Mapped[Decimal | None] = mapped_column(Numeric(10, 2), nullable=True)
    transcript: Mapped[str | None] = mapped_column(Text, nullable=True)
    srt: Mapped[str | None] = mapped_column(Text, nullable=True)
    flags: Mapped[list] = mapped_column(JSON, default=list)
    stats: Mapped[dict] = mapped_column(JSON, default=dict)
    error: Mapped[str | None] = mapped_column(Text, nullable=True)
    raw_deleted_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    snapshot_key: Mapped[str | None] = mapped_column(String(500), nullable=True)  # camera still taken mid-answer


class SystemSetting(Base):
    """Operator-controlled switches (pause paid steps, provider failover, moderation mode...)."""

    __tablename__ = "system_settings"
    key: Mapped[str] = mapped_column(String(100), primary_key=True)
    value: Mapped[dict] = mapped_column(JSON, default=dict)
    updated_by: Mapped[str | None] = mapped_column(String(320), nullable=True)
    updated_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)


class AuditLog(Base):
    """Who did what, for every operator and sensitive action. Append-only."""

    __tablename__ = "audit_logs"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    actor: Mapped[str] = mapped_column(String(320))
    action: Mapped[str] = mapped_column(String(100), index=True)
    target_type: Mapped[str | None] = mapped_column(String(50), nullable=True)
    target_id: Mapped[str | None] = mapped_column(String(64), nullable=True)
    detail: Mapped[dict] = mapped_column(JSON, default=dict)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)


class CreditTransaction(Base):
    """Append-only ledger. The sum of a workspace's amounts always equals its credit_balance."""

    __tablename__ = "credit_transactions"
    __table_args__ = (UniqueConstraint("workspace_id", "ref"),)
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    created_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow, index=True)
    workspace_id: Mapped[str] = mapped_column(String(32), index=True)  # no FK: rows outlive a deleted workspace
    kind: Mapped[str] = mapped_column(
        String(20)
    )  # grant | purchase | adjustment | usage | usage_adjust | usage_release
    amount: Mapped[Decimal] = mapped_column(Money)  # + adds credits, - spends
    balance_after: Mapped[Decimal] = mapped_column(Money)
    project_id: Mapped[str | None] = mapped_column(String(32), nullable=True, index=True)
    stage: Mapped[str | None] = mapped_column(String(50), nullable=True)
    vendor: Mapped[str | None] = mapped_column(String(50), nullable=True)
    vendor_cost: Mapped[Decimal | None] = mapped_column(Money, nullable=True)  # what the vendor charges us (for margin)
    ref: Mapped[str | None] = mapped_column(String(100), nullable=True)  # idempotency key, e.g. a payment id
    description: Mapped[str | None] = mapped_column(String(300), nullable=True)


class CreditPack(Base):
    __tablename__ = "credit_packs"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    name: Mapped[str] = mapped_column(String(100))
    credits: Mapped[Decimal] = mapped_column(Money)
    price_usd: Mapped[Decimal] = mapped_column(Money)
    active: Mapped[bool] = mapped_column(Boolean, default=True)


class Checkout(Base, TimestampMixin):
    __tablename__ = "checkouts"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    workspace_id: Mapped[str] = mapped_column(ForeignKey("workspaces.id"), index=True)
    pack_id: Mapped[str] = mapped_column(ForeignKey("credit_packs.id"))
    credits: Mapped[Decimal] = mapped_column(Money)
    amount_usd: Mapped[Decimal] = mapped_column(Money)
    provider: Mapped[str] = mapped_column(String(30))
    provider_ref: Mapped[str | None] = mapped_column(String(200), nullable=True)
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending | paid | failed | expired
    paid_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class ModerationCase(Base, TimestampMixin):
    __tablename__ = "moderation_cases"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    project_id: Mapped[str] = mapped_column(String(32), index=True)
    workspace_id: Mapped[str] = mapped_column(String(32), index=True)
    stage: Mapped[str] = mapped_column(String(20))  # brief | script | interview
    subject_id: Mapped[str | None] = mapped_column(String(64), nullable=True)  # script version id / take ids hash
    status: Mapped[str] = mapped_column(String(20), default="pending")  # pending | approved | rejected | blocked
    reasons: Mapped[list] = mapped_column(JSON, default=list)
    excerpt: Mapped[str] = mapped_column(Text, default="")
    note: Mapped[str | None] = mapped_column(Text, nullable=True)
    reviewed_by: Mapped[str | None] = mapped_column(String(320), nullable=True)
    reviewed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)


class AuthCode(Base, TimestampMixin):
    """A one-time sign-in / sign-up code sent by email. Only an HMAC of the code is stored."""

    __tablename__ = "auth_codes"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    email: Mapped[str] = mapped_column(String(320), index=True)
    purpose: Mapped[str] = mapped_column(String(10))  # signup | login (operator 2nd step) | reset
    code_hash: Mapped[str] = mapped_column(String(64))
    invite_id: Mapped[str | None] = mapped_column(String(32), nullable=True)
    password_hash: Mapped[str | None] = mapped_column(
        Text, nullable=True
    )  # signup: the chosen password, held until the code is verified
    attempts: Mapped[int] = mapped_column(Integer, default=0)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))
    consumed_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)


class UserSession(Base, TimestampMixin):
    """A signed-in device. The bearer token is random and only its SHA-256 is stored, so sessions are revocable."""

    __tablename__ = "sessions"
    id: Mapped[str] = mapped_column(String(32), primary_key=True, default=new_id)
    user_id: Mapped[str] = mapped_column(ForeignKey("users.id"), index=True)
    token_hash: Mapped[str] = mapped_column(String(64), unique=True)
    expires_at: Mapped[datetime] = mapped_column(DateTime(timezone=True))  # absolute lifetime
    last_used_at: Mapped[datetime] = mapped_column(DateTime(timezone=True), default=utcnow)  # idle timeout
    revoked_at: Mapped[datetime | None] = mapped_column(DateTime(timezone=True), nullable=True)
    otp_verified: Mapped[bool] = mapped_column(Boolean, default=False)
    user_agent: Mapped[str | None] = mapped_column(String(300), nullable=True)
    ip: Mapped[str | None] = mapped_column(String(64), nullable=True)
