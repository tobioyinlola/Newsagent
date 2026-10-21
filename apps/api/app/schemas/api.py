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


class LogoUploadIn(BaseModel):
    content_type: str
    size_bytes: int = Field(gt=0)
    variant: str = Field(default="light", pattern="^(light|dark)$")


class LogoUploadOut(BaseModel):
    upload_url: str
    key: str


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
