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


class VendorBudgetSet(BaseModel):
    vendor: str
    limit: Decimal
