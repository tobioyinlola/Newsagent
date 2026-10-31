"""The back office: what is going on across the whole product (sign-ups, who is paying, how videos are doing).

Operators only, and served to the separate admin app, never the customer app. Figures are computed from the
tables directly, which is right at pilot scale; move them to SQL aggregates or a warehouse before thousands of
customers. The operators' own workspace is excluded so it never counts as a customer.
"""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Query
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import Principal, require
from app.db import get_session
from app.models import Checkout, CreditTransaction, Invite, ModerationCase, Project, SystemSetting, User, Workspace
from app.schemas.backoffice import (
    Attention,
    CustomerDetail,
    CustomerList,
    CustomerProject,
    CustomerRow,
    CustomerUser,
    DayCount,
    Funnel,
    Kpis,
    Overview,
    PayingCompany,
    PaymentRow,
    Payments,
    SignupRow,
    TopCustomer,
)
from app.services import rbac

router = APIRouter(prefix="/v1/admin", tags=["backoffice"])
ZERO = Decimal("0")


def _utc(d: datetime | None) -> datetime | None:
    return None if d is None else (d if d.tzinfo else d.replace(tzinfo=UTC))


def _day(d: datetime) -> str:
    return _utc(d).strftime("%Y-%m-%d")  # type: ignore[union-attr]


class _Data:
    """One consistent read of everything the back office needs."""

    def __init__(self) -> None:
        self.workspaces: dict[str, Workspace] = {}
        self.users_by_ws: dict[str, list[User]] = {}
        self.projects_by_ws: dict[str, list[Project]] = {}
        self.paid: list[Checkout] = []
        self.offline: list[CreditTransaction] = []

    @property
    def customer_ids(self) -> list[str]:
        return list(self.workspaces)

    def owner(self, ws_id: str) -> User:
        users = sorted(self.users_by_ws[ws_id], key=lambda u: u.created_at)
        return users[0]

    def paid_usd(self, ws_id: str) -> Decimal:
        return sum((c.amount_usd for c in self.paid if c.workspace_id == ws_id), ZERO)

    def purchases(self, ws_id: str) -> int:
        return sum(1 for c in self.paid if c.workspace_id == ws_id) + sum(
            1 for t in self.offline if t.workspace_id == ws_id
        )

    def last_video(self, ws_id: str) -> datetime | None:
        ds = [_utc(p.created_at) for p in self.projects_by_ws.get(ws_id, [])]
        return max((d for d in ds if d), default=None)


async def load(session: AsyncSession) -> _Data:
    d = _Data()
    team = await rbac.team_emails(session)
    users = (await session.execute(select(User))).scalars().all()
    by_ws: dict[str, list[User]] = {}
    for u in users:
        by_ws.setdefault(u.workspace_id, []).append(u)
    for ws in (await session.execute(select(Workspace).where(Workspace.deleted_at.is_(None)))).scalars():
        members = by_ws.get(ws.id, [])
        if members and all(u.email.lower() in team for u in members):
            continue  # the operators' own workspace is not a customer
        if not members:
            continue
        d.workspaces[ws.id] = ws
        d.users_by_ws[ws.id] = members
    for p in (await session.execute(select(Project))).scalars():
        if p.workspace_id in d.workspaces:
            d.projects_by_ws.setdefault(p.workspace_id, []).append(p)
    d.paid = [
        c
        for c in (await session.execute(select(Checkout).where(Checkout.status == "paid"))).scalars()
        if c.workspace_id in d.workspaces
    ]
    d.offline = [
        t
        for t in (
            await session.execute(
                select(CreditTransaction).where(
                    CreditTransaction.kind == "purchase", CreditTransaction.ref.like("manual:%")
                )
            )
        ).scalars()
        if t.workspace_id in d.workspaces
    ]
    return d


def _series(days: int, rows: list[tuple[datetime, Decimal]], money: bool) -> list[DayCount]:
    today = datetime.now(UTC).date()
    buckets: dict[str, DayCount] = {
        (today - timedelta(days=i)).isoformat(): DayCount(date=(today - timedelta(days=i)).isoformat())
        for i in range(days - 1, -1, -1)
    }
    for when, amount in rows:
        b = buckets.get(_day(when))
        if b is not None:
            b.count += 1
            b.usd += amount if money else ZERO
    return list(buckets.values())


@router.get("/overview", response_model=Overview)
async def overview(
    days: int = Query(30, ge=7, le=90),
    _: Principal = Depends(require("overview.view")),
    session: AsyncSession = Depends(get_session),
) -> Overview:
    d = await load(session)
    now = datetime.now(UTC)
    d7, d30 = now - timedelta(days=7), now - timedelta(days=30)
    owners = {w: d.owner(w) for w in d.workspaces}
    signed = {w: _utc(u.created_at) for w, u in owners.items()}
    projects = [p for ps in d.projects_by_ws.values() for p in ps]
    p30 = [p for p in projects if (_utc(p.created_at) or now) >= d30]
    paying = {c.workspace_id for c in d.paid} | {t.workspace_id for t in d.offline}
    revenue_30d = sum((c.amount_usd for c in d.paid if (_utc(c.paid_at or c.created_at) or now) >= d30), ZERO)
    kpis = Kpis(
        customers=len(d.workspaces),
        signups_7d=sum(1 for t in signed.values() if t and t >= d7),
        signups_30d=sum(1 for t in signed.values() if t and t >= d30),
        paying_companies=len(paying),
        revenue_usd_total=sum((c.amount_usd for c in d.paid), ZERO),
        revenue_usd_30d=revenue_30d,
        vendor_cost_usd_30d=sum((p.cost_total for p in p30), ZERO),
        videos_total=len(projects),
        videos_30d=len(p30),
        videos_ready=sum(1 for p in projects if p.state == "final_ready"),
        active_30d=len({p.workspace_id for p in p30}),
        credits_outstanding=sum((w.credit_balance for w in d.workspaces.values()), ZERO),
    )
    states: dict[str, int] = {}
    for p in projects:
        states[p.state] = states.get(p.state, 0) + 1

    invites = (await session.execute(select(Invite))).scalars().all()
    funnel = Funnel(
        invites_sent=len(invites),
        accepted=sum(1 for i in invites if i.used_at),
        pending=sum(1 for i in invites if not i.used_at and (_utc(i.expires_at) or now) >= now),
        expired=sum(1 for i in invites if not i.used_at and (_utc(i.expires_at) or now) < now),
    )
    paused_row = await session.get(SystemSetting, "paid_steps_paused")
    pending_reviews = (
        await session.execute(
            select(func.count()).select_from(ModerationCase).where(ModerationCase.status == "pending")
        )
    ).scalar_one()
    attention = Attention(
        pending_reviews=pending_reviews,
        failed_videos=sum(1 for p in projects if p.state in {"failed", "limit_reached"}),
        suspended_workspaces=sum(1 for w in d.workspaces.values() if w.suspended),
        paused=bool(paused_row and paused_row.value.get("paused")),
    )
    recent = sorted(d.workspaces, key=lambda w: signed[w] or now, reverse=True)[:10]
    recent_rows = [
        SignupRow(
            workspace_id=w,
            company=d.workspaces[w].name,
            email=owners[w].email,
            signed_up_at=signed[w] or now,
            last_login_at=_utc(owners[w].last_login_at),
            credits=d.workspaces[w].credit_balance,
            videos=len(d.projects_by_ws.get(w, [])),
            paid=w in paying,
        )
        for w in recent
    ]
    top = sorted(d.workspaces, key=lambda w: (d.paid_usd(w), len(d.projects_by_ws.get(w, []))), reverse=True)[:5]
    top_rows = [
        TopCustomer(
            workspace_id=w,
            company=d.workspaces[w].name,
            revenue_usd=d.paid_usd(w),
            videos=len(d.projects_by_ws.get(w, [])),
            last_video_at=d.last_video(w),
        )
        for w in top
        if d.paid_usd(w) > 0 or d.projects_by_ws.get(w)
    ]
    return Overview(
        kpis=kpis,
        funnel=funnel,
        attention=attention,
        signups_by_day=_series(days, [(t, ZERO) for t in signed.values() if t], False),
        revenue_by_day=_series(days, [(_utc(c.paid_at or c.created_at) or now, c.amount_usd) for c in d.paid], True),
        videos_by_state=states,
        recent_signups=recent_rows,
        top_customers=top_rows,
    )


def _payment_rows(d: _Data, ws_ids: set[str] | None = None) -> list[PaymentRow]:
    rows = [
        PaymentRow(
            when=_utc(c.paid_at or c.created_at) or datetime.now(UTC),
            workspace_id=c.workspace_id,
            company=d.workspaces[c.workspace_id].name,
            kind="bank_transfer" if c.provider in {"manual_bank", "nuvion_bank"} else "card",
            usd=c.amount_usd,
            credits=c.credits,
            provider=c.provider,
        )
        for c in d.paid
        if ws_ids is None or c.workspace_id in ws_ids
    ]
    rows += [
        PaymentRow(
            when=_utc(t.created_at) or datetime.now(UTC),
            workspace_id=t.workspace_id,
            company=d.workspaces[t.workspace_id].name,
            kind="offline",
            usd=None,
            credits=t.amount,
        )
        for t in d.offline
        if ws_ids is None or t.workspace_id in ws_ids
    ]
    return sorted(rows, key=lambda r: r.when, reverse=True)


@router.get("/customers", response_model=CustomerList)
async def customers(
    q: str = Query("", max_length=100),
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    _: Principal = Depends(require("customers.view")),
    session: AsyncSession = Depends(get_session),
) -> CustomerList:
    d = await load(session)
    now = datetime.now(UTC)
    needle = q.strip().lower()
    ids = [
        w
        for w in d.workspaces
        if not needle
        or needle in d.workspaces[w].name.lower()
        or any(needle in u.email.lower() for u in d.users_by_ws[w])
    ]
    ids.sort(key=lambda w: _utc(d.owner(w).created_at) or now, reverse=True)
    items = []
    for w in ids[offset : offset + limit]:
        ws, owner = d.workspaces[w], d.owner(w)
        items.append(
            CustomerRow(
                workspace_id=w,
                company=ws.name,
                owner_email=owner.email,
                signed_up_at=_utc(owner.created_at) or now,
                last_login_at=_utc(owner.last_login_at),
                status="suspended" if ws.suspended else "active",
                credits=ws.credit_balance,
                paid_usd=d.paid_usd(w),
                purchases=d.purchases(w),
                videos=len(d.projects_by_ws.get(w, [])),
                last_video_at=d.last_video(w),
            )
        )
    return CustomerList(total=len(ids), items=items)


@router.get("/customers/{workspace_id}", response_model=CustomerDetail)
async def customer(
    workspace_id: str, _: Principal = Depends(require("customers.view")), session: AsyncSession = Depends(get_session)
) -> CustomerDetail:
    d = await load(session)
    ws = d.workspaces.get(workspace_id)
    if ws is None:
        raise HTTPException(404, "Customer not found")
    projects = sorted(
        d.projects_by_ws.get(workspace_id, []), key=lambda p: _utc(p.created_at) or datetime.min, reverse=True
    )
    return CustomerDetail(
        workspace_id=workspace_id,
        company=ws.name,
        plan=ws.plan,
        status="suspended" if ws.suspended else "active",
        signed_up_at=_utc(d.owner(workspace_id).created_at) or datetime.now(UTC),
        credits=ws.credit_balance,
        spent_credits=ws.spent_total,
        spend_cap=ws.spend_cap,
        users=[
            CustomerUser(
                email=u.email,
                role=u.role,
                created_at=_utc(u.created_at) or datetime.now(UTC),
                last_login_at=_utc(u.last_login_at),
            )
            for u in sorted(d.users_by_ws[workspace_id], key=lambda u: u.created_at)
        ],
        projects=[
            CustomerProject(
                id=p.id,
                state=p.state,
                created_at=_utc(p.created_at) or datetime.now(UTC),
                completed_at=_utc(p.completed_at),
                cost_usd=p.cost_total,
                interview=(p.interview_mode if p.interview_enabled else "none"),
                published=p.published_at is not None and p.story_slug is not None,
            )
            for p in projects[:25]
        ],
        payments=_payment_rows(d, {workspace_id}),
    )


@router.get("/payments", response_model=Payments)
async def payments(
    _: Principal = Depends(require("finance.view")), session: AsyncSession = Depends(get_session)
) -> Payments:
    d = await load(session)
    now = datetime.now(UTC)
    items = _payment_rows(d)
    by_co: dict[str, PayingCompany] = {}
    for r in items:
        c = by_co.setdefault(
            r.workspace_id,
            PayingCompany(workspace_id=r.workspace_id, company=r.company, payments=0, usd=ZERO, last_paid_at=None),
        )
        c.payments += 1
        c.usd += r.usd or ZERO
        c.last_paid_at = max(filter(None, [c.last_paid_at, r.when]))
    return Payments(
        total_usd=sum((c.amount_usd for c in d.paid), ZERO),
        total_usd_30d=sum((r.usd or ZERO for r in items if r.when >= now - timedelta(days=30)), ZERO),
        offline_credits=sum((t.amount for t in d.offline), ZERO),
        paying_companies=sorted(by_co.values(), key=lambda c: (c.usd, c.payments), reverse=True),
        items=items[:200],
    )
