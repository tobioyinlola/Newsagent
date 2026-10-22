from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel, EmailStr, Field


class RedeemInvite(BaseModel):
    code: str


class MeOut(BaseModel):
    email: str
    workspace_id: str
    workspace_name: str
    credit_balance: Decimal
    is_operator: bool


class ProjectCreate(BaseModel):
    brief_text: str = Field(min_length=20, max_length=8000)
    website_url: str | None = None
    region: str = "NG"
    voice_accent: str = "british"
    accent_override: str | None = Field(default=None, pattern=r"^#[0-9a-fA-F]{6}$")


class AssetOut(BaseModel):
    id: str
    type: str
    format: str | None
    storage_key: str
    model_config = {"from_attributes": True}


class ProjectOut(BaseModel):
    id: str
    state: str
    region: str
    voice_accent: str
    cost_total: Decimal
    failure_reason: str | None
    failure_retryable: bool
    interview_enabled: bool = False
    keep_raw_takes: bool = False
    created_at: datetime
    assets: list[AssetOut] = []
    model_config = {"from_attributes": True}


class ScriptOut(BaseModel):
    id: str
    version: int
    segments: list[dict]
    ticker_lines: list[str]
    lower_thirds: list[dict]
    interview_questions: list[str]
    claim_flags: list[dict]
    approved: bool
    model_config = {"from_attributes": True}


class ScriptUpdate(BaseModel):
    segments: list[dict]
    ticker_lines: list[str]
    lower_thirds: list[dict]
    interview_questions: list[str] = []
    confirmed_claims: list[str] = []  # claim texts the owner confirms


class InviteCreate(BaseModel):
    email: EmailStr
    workspace_name: str
    credits: Decimal = Decimal("20")
    spend_cap: Decimal = Decimal("50")


class InviteOut(BaseModel):
    code: str
    workspace_id: str
    expires_at: datetime


class WorkspacePatch(BaseModel):
    credit_balance: Decimal | None = None
    spend_cap: Decimal | None = None
    max_videos_per_day: int | None = None
    max_video_seconds: int | None = None
    suspended: bool | None = None
    share_disabled: bool | None = None


class VendorBudgetSet(BaseModel):
    vendor: str
    limit: Decimal


# ---------- brand kit ----------
FONTS = ["Inter", "Poppins", "Montserrat", "Roboto", "Lato", "Open Sans", "Playfair Display"]
TONES = ["confident", "friendly", "authoritative", "playful", "serious"]
Hex = Field(pattern=r"^#[0-9a-fA-F]{6}$")


class BrandKitIn(BaseModel):
    primary_color: str = Field(pattern=r"^#[0-9a-fA-F]{6}$")
    accent_color: str = Field(pattern=r"^#[0-9a-fA-F]{6}$")
    secondary_colors: list[str] = Field(default=[], max_length=4)
    fonts: dict[str, str] = {}  # {"heading": "Inter", "body": "Inter"}
    pronunciation_glossary: dict[str, str] = Field(default={}, max_length=100)
    tone: str = "confident"
    logo_light_key: str | None = None
    logo_dark_key: str | None = None
    source_url: str | None = None


class ContrastCheck(BaseModel):
    background: str
    text: str
    ratio: float
    passes: bool
    suggested_background: str | None = None


class BrandKitOut(BaseModel):
    id: str
    version: int
    primary_color: str
    accent_color: str
    secondary_colors: list[str]
    fonts: dict[str, str]
    pronunciation_glossary: dict[str, str]
    tone: str
    logo_light_key: str | None
    logo_dark_key: str | None
    source_url: str | None
    contrast: list[ContrastCheck] = []
    accent_alternatives: list[str] = []
    model_config = {"from_attributes": True}


class BrandImportIn(BaseModel):
    url: str


class BrandDraft(BaseModel):
    company_name: str | None
    primary_color: str | None
    accent_color: str | None
    logo_url: str | None
    source_url: str
    confirmed: bool = False


class VoiceOut(BaseModel):
    id: str
    accent: str
    preview_url: str | None = None


# ---------- delivery ----------
class DownloadItem(BaseModel):
    type: str
    format: str | None
    filename: str
    url: str
    expires_in_s: int


class DownloadsOut(BaseModel):
    items: list[DownloadItem]
    disclosure: str


class CaptionsOut(BaseModel):
    captions: dict[str, str]
    disclosure: str
    has_active_share: bool


class ShareCreated(BaseModel):
    url: str


class SharePublic(BaseModel):
    title: str
    video_url: str
    thumbnail_url: str | None
    disclosure: str
    tag: str


class CostLine(BaseModel):
    stage: str
    vendor: str | None
    status: str
    attempts: int
    cost: Decimal
    duration_s: Decimal | None


class CostsOut(BaseModel):
    total: Decimal
    lines: list[CostLine]


# ---------- admin listings ----------
class WorkspaceAdminOut(BaseModel):
    id: str
    name: str
    credit_balance: Decimal
    spend_cap: Decimal
    spent_total: Decimal
    max_videos_per_day: int
    max_video_seconds: int
    suspended: bool
    share_disabled: bool
    model_config = {"from_attributes": True}


class VendorBudgetOut(BaseModel):
    vendor: str
    period: str
    limit: Decimal
    spent: Decimal
    model_config = {"from_attributes": True}


# ---------- brand asset uploads ----------
class UploadIn(BaseModel):
    kind: str = Field(pattern="^(logo_light|logo_dark|guide_pdf|product_image)$")
    content_type: str
    size_bytes: int = Field(gt=0)


class UploadOut(BaseModel):
    upload_url: str
    key: str
    max_bytes: int


class UploadConfirmIn(BaseModel):
    key: str


class BrandAssetOut(BaseModel):
    key: str
    kind: str
    content_type: str
    size_bytes: int
    url: str | None = None


# ---------- founder interview ----------
class InterviewInviteIn(BaseModel):
    founder_name: str = Field(min_length=1, max_length=200)
    founder_title: str = Field(default="", max_length=200)
    founder_email: EmailStr | None = None


class InterviewInviteOut(BaseModel):
    url: str  # shown once; only a hash is stored for lookups
    expires_at: datetime
    emailed: bool


class TakeOut(BaseModel):
    id: str
    question_index: int
    kind: str
    status: str
    flags: list[str]
    messages: list[str] = []
    duration_s: Decimal | None = None
    transcript: str | None = None
    video_url: str | None = None
    audio_url: str | None = None
    attempts: int = 1


class InterviewStatusOut(BaseModel):
    active: bool
    founder_name: str | None = None
    founder_title: str | None = None
    founder_email: str | None = None
    expires_at: datetime | None = None
    submitted: bool = False
    consented: bool = False
    reminders_sent: int = 0
    questions: list[str] = []
    takes: list[TakeOut] = []
    plan: dict | None = None
    photo_url: str | None = None


class PlanAnswer(BaseModel):
    question_index: int
    include: bool = True
    trim_start_s: float = 0
    trim_end_s: float = 0


class MergePlanIn(BaseModel):
    layout: str = "pip"
    order: list[int] | None = None
    answers: list[PlanAnswer] = []


class RetakeIn(BaseModel):
    question_index: int
    note: str = Field(default="", max_length=300)


class KeepRawIn(BaseModel):
    keep: bool


class ApproveIn(BaseModel):
    with_interview: bool = False


# ---------- founder (guest) ----------
class GuestTake(BaseModel):
    id: str
    status: str
    kind: str
    flags: list[str] = []
    messages: list[str] = []
    chunks_received: list[int] = []
    duration_s: Decimal | None = None


class GuestQuestion(BaseModel):
    index: int
    text: str
    clip_url: str | None = None
    take: GuestTake | None = None
    attempts_left: int


class GuestView(BaseModel):
    company: str
    founder_name: str
    expires_at: datetime
    consent_text: str
    consented: bool
    can_record: bool
    submitted: bool
    has_photo: bool
    questions: list[GuestQuestion]
    max_chunks: int
    max_chunk_bytes: int


class GuestTakeIn(BaseModel):
    question_index: int = Field(ge=0, le=4)
    kind: str = Field(pattern="^(video|audio)$")
    mime: str = Field(max_length=100)


class ChunkUrlsIn(BaseModel):
    indexes: list[int] = Field(min_length=1, max_length=20)


class ChunkUrlsOut(BaseModel):
    urls: dict[str, str]


class CompleteIn(BaseModel):
    chunk_count: int = Field(ge=1, le=80)


class UploadSlot(BaseModel):
    key: str
    upload_url: str


class PhotoIn(BaseModel):
    content_type: str


class PhotoConfirmIn(BaseModel):
    key: str


# ---------- billing ----------
class PackOut(BaseModel):
    id: str
    name: str
    credits: Decimal
    price_usd: Decimal
    model_config = {"from_attributes": True}


class PackIn(BaseModel):
    name: str = Field(min_length=1, max_length=100)
    credits: Decimal = Field(gt=0)
    price_usd: Decimal = Field(ge=0)


class BillingSummary(BaseModel):
    credit_balance: Decimal
    spend_cap: Decimal
    spent_total: Decimal
    low_balance_threshold: Decimal
    max_videos_per_day: int


class CheckoutIn(BaseModel):
    pack_id: str


class CheckoutOut(BaseModel):
    checkout_id: str
    url: str


class LedgerEntry(BaseModel):
    id: str
    created_at: datetime
    kind: str
    amount: Decimal
    balance_after: Decimal
    project_id: str | None
    stage: str | None
    description: str | None
    model_config = {"from_attributes": True}


class UsageLine(BaseModel):
    project_id: str | None
    stage: str | None
    credits: Decimal


class UsageStatement(BaseModel):
    month: str
    total_credits: Decimal
    lines: list[UsageLine]


class ManualCreditsIn(BaseModel):
    credits: Decimal = Field(gt=0)
    ref: str = Field(min_length=1, max_length=100)  # e.g. the invoice or bank transfer reference
    note: str = Field(default="", max_length=300)


class PackPatch(BaseModel):
    active: bool


# ---------- operator console ----------
class ModerationCaseOut(BaseModel):
    id: str
    project_id: str
    workspace_id: str
    workspace_name: str | None = None
    stage: str
    status: str
    reasons: list[str]
    excerpt: str
    note: str | None
    created_at: datetime
    reviewed_by: str | None = None


class ModerationDecisionIn(BaseModel):
    decision: str = Field(pattern="^(approve|reject)$")
    note: str = Field(default="", max_length=500)


class ProjectModerationOut(BaseModel):
    stage: str
    status: str
    note: str | None = None
    created_at: datetime


class JobOut(BaseModel):
    id: str
    project_id: str
    workspace_name: str | None = None
    stage: str
    vendor: str | None
    status: str
    attempts: int
    cost: Decimal
    duration_s: Decimal | None
    error: str | None
    created_at: datetime
    stuck: bool = False


class QueueOut(BaseModel):
    jobs: dict[str, int]
    takes: dict[str, int]
    projects: dict[str, int]
    moderation_pending: int
    paused: bool


class SettingsOut(BaseModel):
    paused: bool = False
    pause_reason: str = ""
    moderation_mode: str = "enforce"
    moderation_llm: bool = False
    avatar_primary: str = "heygen"
    avatar_secondary: str | None = None
    avatar_failover: bool = False


class SettingsPatch(BaseModel):
    paused: bool | None = None
    pause_reason: str | None = Field(default=None, max_length=200)
    moderation_mode: str | None = Field(default=None, pattern="^(enforce|log_only)$")
    moderation_llm: bool | None = None
    avatar_primary: str | None = Field(default=None, pattern="^(heygen|synthesia|mock)$")
    avatar_secondary: str | None = Field(default=None, pattern="^(heygen|synthesia|mock|none)$")
    avatar_failover: bool | None = None


class CostRow(BaseModel):
    project_id: str
    workspace_name: str | None
    state: str
    interview: bool
    vendor_cost: Decimal
    credits_charged: Decimal
    margin: Decimal  # credits charged x USD per credit - vendor cost
    by_vendor: dict[str, Decimal]


class CostSummary(BaseModel):
    videos: int  # completed (final_ready) videos in the window
    avg_vendor_cost: Decimal
    avg_credits_charged: Decimal
    avg_margin: Decimal
    usd_per_credit: Decimal
    markup: Decimal


class CostReport(BaseModel):
    summary: CostSummary
    rows: list[CostRow]


class AuditOut(BaseModel):
    id: str
    created_at: datetime
    actor: str
    action: str
    target_type: str | None
    target_id: str | None
    detail: dict
    model_config = {"from_attributes": True}
