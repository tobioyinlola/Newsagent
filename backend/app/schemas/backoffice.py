from datetime import datetime
from decimal import Decimal

from pydantic import BaseModel


class Kpis(BaseModel):
    customers: int
    signups_7d: int
    signups_30d: int
    paying_companies: int
    revenue_usd_total: Decimal
    revenue_usd_30d: Decimal
    vendor_cost_usd_30d: Decimal  # what the vendors charged us for videos started in the last 30 days
    videos_total: int
    videos_30d: int
    videos_ready: int
    active_30d: int  # customers who started a video in the last 30 days
    credits_outstanding: Decimal  # credits customers hold and haven't used


class DayCount(BaseModel):
    date: str
    count: int = 0
    usd: Decimal = Decimal("0")


class Funnel(BaseModel):
    invites_sent: int
    accepted: int
    pending: int
    expired: int


class Attention(BaseModel):
    pending_reviews: int
    failed_videos: int
    suspended_workspaces: int
    paused: bool


class SignupRow(BaseModel):
    workspace_id: str
    company: str
    email: str
    signed_up_at: datetime
    last_login_at: datetime | None
    credits: Decimal
    videos: int
    paid: bool


class TopCustomer(BaseModel):
    workspace_id: str
    company: str
    revenue_usd: Decimal
    videos: int
    last_video_at: datetime | None


class Overview(BaseModel):
    kpis: Kpis
    funnel: Funnel
    attention: Attention
    signups_by_day: list[DayCount]
    revenue_by_day: list[DayCount]
    videos_by_state: dict[str, int]
    recent_signups: list[SignupRow]
    top_customers: list[TopCustomer]


class CustomerRow(BaseModel):
    workspace_id: str
    company: str
    owner_email: str
    signed_up_at: datetime
    last_login_at: datetime | None
    status: str  # active | suspended
    credits: Decimal
    paid_usd: Decimal
    purchases: int
    videos: int
    last_video_at: datetime | None


class CustomerList(BaseModel):
    total: int
    items: list[CustomerRow]


class CustomerUser(BaseModel):
    email: str
    role: str
    created_at: datetime
    last_login_at: datetime | None


class CustomerProject(BaseModel):
    id: str
    state: str
    created_at: datetime
    completed_at: datetime | None
    cost_usd: Decimal
    interview: str  # none | live | invite


class PaymentRow(BaseModel):
    when: datetime
    workspace_id: str
    company: str
    kind: str  # card | offline
    usd: Decimal | None  # None for an offline payment: only the credits are recorded
    credits: Decimal
    provider: str | None = None
    status: str = "paid"


class CustomerDetail(BaseModel):
    workspace_id: str
    company: str
    plan: str
    status: str
    signed_up_at: datetime
    credits: Decimal
    spent_credits: Decimal
    spend_cap: Decimal
    users: list[CustomerUser]
    projects: list[CustomerProject]
    payments: list[PaymentRow]


class PayingCompany(BaseModel):
    workspace_id: str
    company: str
    payments: int
    usd: Decimal
    last_paid_at: datetime | None


class Payments(BaseModel):
    total_usd: Decimal
    total_usd_30d: Decimal
    offline_credits: Decimal
    paying_companies: list[PayingCompany]
    items: list[PaymentRow]
