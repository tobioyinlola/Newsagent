from datetime import datetime
from decimal import Decimal
from typing import Annotated

from pydantic import BaseModel, EmailStr, Field


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
    founder_name: str = Field(default="", max_length=200)  # the AI interviewer greets this person by name
    founder_title: str = Field(default="", max_length=200)
    anchor_id: str | None = Field(default=None, max_length=100)  # the chosen presenter look (from GET /v1/presenters)
    flow: str = Field(default="classic", pattern="^(classic|guided)$")
    announcement_type: str | None = Field(
        default=None, pattern="^(product_launch|funding_round|partnership|hiring|milestone|other)$"
    )


class PresenterOut(BaseModel):
    id: str
    name: str
    gender: str
    preview_image_url: str | None = None
    orientation: str | None = None


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
    interview_mode: str = "invite"
    founder_name: str = ""
    founder_title: str = ""
    anchor_id: str | None = None
    flow: str = "classic"
    announcement_type: str | None = None
    keep_raw_takes: bool = False
    created_at: datetime
    assets: list[AssetOut] = []
    model_config = {"from_attributes": True}


class BrollItemIn(BaseModel):
    key: str
    caption: str = Field(default="", max_length=80)
    seconds: float = Field(ge=2, le=8)


class BrollPutIn(BaseModel):
    items: list[BrollItemIn] = Field(max_length=5)


class BrollCandidate(BaseModel):
    key: str
    kind: str  # image | video
    source: str  # upload | generated
    synthetic: bool
    duration_s: float | None = None
    url: str | None = None


class BrollItemOut(BaseModel):
    key: str
    kind: str
    caption: str
    seconds: float
    synthetic: bool


class BrollOut(BaseModel):
    items: list[BrollItemOut]
    candidates: list[BrollCandidate]
    ai_available: bool
    note: str | None = None


class BrollGenerateIn(BaseModel):
    prompt: str = Field(min_length=10, max_length=300)
    seconds: float = Field(default=5, ge=3, le=8)


class ProgressStage(BaseModel):
    key: str
    label: str
    status: str  # done | working | waiting | pending | failed | paused | cancelled
    detail: str | None = None


class ProgressOut(BaseModel):
    state: str
    percent: int
    stages: list[ProgressStage]
    retryable: bool
    cancellable: bool
    failure_category: str | None = None  # why the last step failed, in plain categories (auth, rate_limited, ...)
    vendor_jobs_in_flight: int = 0
    queue_ahead: int = (
        0  # other videos in the same step that started waiting earlier (about how many are in front of this one)
    )


class ScriptOut(BaseModel):
    id: str
    version: int
    segments: list[dict]
    ticker_lines: list[str]
    lower_thirds: list[dict]
    interview_questions: list[str]
    claim_flags: list[dict]
    story: dict | None = None
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
    emailed: bool = False  # true once the invitation email was sent to the startup


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
    kind: str = Field(pattern="^(logo_light|logo_dark|guide_pdf|product_image|product_video)$")
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
    duration_s: float | None = None  # product videos


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
    snapshot_url: str | None = None
    attempts: int = 1


class InterviewStatusOut(BaseModel):
    active: bool
    mode: str = "invite"
    consent_text: str | None = None  # shown before a live interview starts
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
    layout: str | None = None  # this answer's own layout; otherwise the video's


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
    interview_mode: str = Field(default="invite", pattern="^(invite|live)$")  # live = the AI interviewer, now


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
    mode: str = "invite"
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
    take_id: str | None = None  # a snapshot of this answer rather than the founder's profile photo


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


# ---------- sign-in / sign-up ----------
class InvitePreview(BaseModel):
    workspace_name: str
    email_hint: str  # e.g. a***@startup.com


Password = Annotated[str, Field(min_length=10, max_length=128)]
Otp = Annotated[str, Field(min_length=6, max_length=6, pattern=r"^\d{6}$")]


class SignupStartIn(BaseModel):
    """Sign up with an invitation (invite_code + password), or on your own (email + business_name + password)."""

    invite_code: str | None = Field(default=None, min_length=8, max_length=100)
    email: EmailStr | None = None
    business_name: str | None = Field(default=None, min_length=2, max_length=200)
    city: str | None = Field(default=None, min_length=2, max_length=120)  # the press release dateline
    country: str | None = Field(default=None, min_length=2, max_length=120)
    password: Password


class SignupVerifyIn(BaseModel):
    invite_code: str | None = Field(default=None, min_length=8, max_length=100)
    email: EmailStr | None = None
    code: Otp


class LoginIn(BaseModel):
    email: EmailStr
    password: str = Field(min_length=1, max_length=128)


class OtpIn(BaseModel):
    code: Otp


class ForgotIn(BaseModel):
    email: EmailStr


class ResetIn(BaseModel):
    email: EmailStr
    code: Otp
    new_password: Password


class ChangePasswordIn(BaseModel):
    current_password: str = Field(min_length=1, max_length=128)
    new_password: Password


class CodeSentOut(BaseModel):
    sent: bool = True
    email_hint: str | None = None
    expires_in_s: int


class SessionOut(BaseModel):
    token: str
    expires_at: datetime
    otp_required: bool  # operators confirm every sign-in with an emailed code (call /auth/login/otp)


class SessionInfo(BaseModel):
    id: str
    created_at: datetime
    last_used_at: datetime
    user_agent: str | None
    ip: str | None
    current: bool


# ---------- live AI interview (dashboard) ----------
class LiveStartIn(BaseModel):
    founder_name: str = Field(min_length=1, max_length=200)
    founder_title: str = Field(default="", max_length=200)
    consent: bool  # the owner ticked "I understand and agree" for their own recording


class LiveStartOut(BaseModel):
    token: str  # scopes the recorder to this one interview (the same credential a founder link carries)
    company: str
    founder_name: str
    expires_at: datetime
    consent_text: str
    questions: list[str]
    max_total_s: int
    max_answer_s: int
    min_answer_s: int


class VoiceLine(BaseModel):
    key: str  # greeting | q0.. | thanks | closing
    text: str
    audio_url: str | None = None  # None: the browser speaks it with its own voice


class VoicePrepareOut(BaseModel):
    lines: list[VoiceLine]


class RealtimeOut(BaseModel):
    url: str  # the LiveKit server to connect to
    token: str  # join token for this interview's room only
    room: str


class LinesOut(BaseModel):
    lines: dict[str, str]  # key (greeting, q0.., thanks, closing) -> what the interviewer says


class BriefUnderstandingOut(BaseModel):
    company: str = ""
    announcement: str = ""
    problem: str = ""
    key_facts: list[str] = []
    founder_name: str = ""
    founder_title: str = ""


# ---------- scene editor ----------
class SceneOut(BaseModel):
    id: str
    order: int
    type: str
    label: str
    duration_s: float
    narration: str | None = None
    caption: str | None = None
    layout: str | None = None
    question_index: int | None = None
    trim_start_s: float | None = None
    trim_end_s: float | None = None
    synthetic: bool = False
    editable: list[str]  # which of narration, layout, include, trim, caption, seconds this scene allows


class ScenesOut(BaseModel):
    plan_hash: str | None
    revision_pending: bool
    scenes: list[SceneOut]
    excluded_answers: list[dict] = []  # answers left out of the video, which can be put back
    can_revise: bool


class ScenePatch(BaseModel):
    narration: str | None = Field(default=None, max_length=2000)
    layout: str | None = None
    include: bool | None = None
    trim_start_s: float | None = Field(default=None, ge=0)
    trim_end_s: float | None = Field(default=None, ge=0)
    caption: str | None = Field(default=None, max_length=80)
    seconds: float | None = Field(default=None, ge=2, le=8)
    confirmed_claims: list[str] = []


class ScenePatchOut(BaseModel):
    regenerates: list[str]  # what the next re-render will make again
    revision_pending: bool
