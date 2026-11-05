"""Back office: every customer's wallet (balance, what they bought, what they used) and each wallet's full history."""

import csv
import io
from datetime import UTC, datetime
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import Response
from pydantic import BaseModel
from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import Principal, require
from app.db import get_session
from app.models import CreditTransaction, User, Workspace

router = APIRouter(prefix="/v1/admin", tags=["backoffice"])

PAYMENT_KINDS = (
    "purchase",
    "grant",
    "adjustment",
    "refund",
    "chargeback",
    "chargeback_reversal",
)  # credits arriving or going back
USAGE_KINDS = ("usage", "usage_adjust", "usage_release")  # credits spent on videos and distribution
KIND_LABEL = {
    "grant": "Free credits",
    "purchase": "Credits bought",
    "adjustment": "Adjustment by our team",
    "usage": "Used",
    "usage_adjust": "Used (adjusted)",
    "usage_release": "Used (released)",
    "refund": "Refund",
    "chargeback": "Chargeback",
    "chargeback_reversal": "Chargeback reversed",
}


class WalletRow(BaseModel):
    workspace_id: str
    company: str
    owner_email: str
    status: str  # active | suspended
    balance: Decimal
    bought: Decimal  # credits they paid for
    free: Decimal  # credits we gave (sign-up credit, referral rewards, grants)
    used: Decimal  # credits spent on videos and distribution (net)
    last_activity_at: datetime | None


class WalletTotals(BaseModel):
    wallets: int
    balance: Decimal
    empty: int  # wallets with no credit left
    bought: Decimal
    used: Decimal


class WalletList(BaseModel):
    totals: WalletTotals
    total: int
    items: list[WalletRow]


class LedgerRow(BaseModel):
    id: str
    when: datetime
    kind: str
    label: str
    amount: Decimal  # + adds credits, - spends
    balance_after: Decimal
    description: str | None
    stage: str | None
    project_id: str | None


class Ledger(BaseModel):
    company: str
    balance: Decimal
    total: int
    items: list[LedgerRow]


def _utc(t: datetime | None) -> datetime | None:
    return None if t is None else (t if t.tzinfo else t.replace(tzinfo=UTC))


def _sum(*kinds: str):
    """The total of this wallet's ledger rows of these kinds (zero when there are none)."""
    return func.coalesce(func.sum(case((CreditTransaction.kind.in_(kinds), CreditTransaction.amount), else_=0)), 0)


async def _rows(session: AsyncSession, q: str = "") -> list[WalletRow]:
    agg = {
        r.workspace_id: r
        for r in (
            await session.execute(
                select(
                    CreditTransaction.workspace_id,
                    _sum("purchase").label("bought"),
                    _sum("grant").label("free"),
                    _sum(*USAGE_KINDS).label("used"),
                    func.max(CreditTransaction.created_at).label("last"),
                ).group_by(CreditTransaction.workspace_id)
            )
        ).all()
    }
    workspaces = (await session.execute(select(Workspace).where(Workspace.deleted_at.is_(None)))).scalars().all()
    owners: dict[str, str] = {}
    for u in (await session.execute(select(User).order_by(User.created_at))).scalars():
        owners.setdefault(u.workspace_id, u.email)
    needle = q.strip().lower()
    out = []
    for w in workspaces:
        if needle and needle not in w.name.lower() and needle not in owners.get(w.id, "").lower():
            continue
        a = agg.get(w.id)
        out.append(
            WalletRow(
                workspace_id=w.id,
                company=w.name,
                owner_email=owners.get(w.id, ""),
                status="suspended" if w.suspended else "active",
                balance=w.credit_balance or Decimal("0"),
                bought=Decimal(a.bought) if a else Decimal("0"),
                free=Decimal(a.free) if a else Decimal("0"),
                used=-Decimal(a.used)
                if a
                else Decimal("0"),  # spending is negative in the ledger; shown as a positive number
                last_activity_at=_utc(a.last) if a else None,
            )
        )
    return out


SORTS = {
    "balance_low": (lambda r: r.balance, False),
    "balance_high": (lambda r: r.balance, True),
    "used_high": (lambda r: r.used, True),
    "recent": (lambda r: r.last_activity_at or datetime.min.replace(tzinfo=UTC), True),
    "company": (lambda r: r.company.lower(), False),
}


@router.get("/wallets", response_model=WalletList)
async def wallets(
    q: str = Query("", max_length=100),
    sort: Literal["balance_low", "balance_high", "used_high", "recent", "company"] = "balance_high",
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    _: Principal = Depends(require("customers.view")),
    session: AsyncSession = Depends(get_session),
) -> WalletList:
    rows = await _rows(session, q)
    key, reverse = SORTS[sort]
    rows.sort(key=key, reverse=reverse)
    return WalletList(
        totals=WalletTotals(
            wallets=len(rows),
            balance=sum((r.balance for r in rows), Decimal("0")),
            empty=sum(1 for r in rows if r.balance <= 0),
            bought=sum((r.bought for r in rows), Decimal("0")),
            used=sum((r.used for r in rows), Decimal("0")),
        ),
        total=len(rows),
        items=rows[offset : offset + limit],
    )


def _csv(name: str, header: list[str], lines: list[list]) -> Response:
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(header)
    for line in lines:
        w.writerow(
            [("'" + c if isinstance(c, str) and c[:1] in "=+-@" else c) for c in line]
        )  # a cell never starts a spreadsheet formula
    return Response(
        out.getvalue(), media_type="text/csv", headers={"Content-Disposition": f'attachment; filename="{name}"'}
    )


@router.get("/wallets.csv")
async def wallets_csv(
    q: str = Query("", max_length=100),
    sort: Literal["balance_low", "balance_high", "used_high", "recent", "company"] = "balance_high",
    _: Principal = Depends(require("customers.view")),
    session: AsyncSession = Depends(get_session),
) -> Response:
    rows = await _rows(session, q)
    key, reverse = SORTS[sort]
    rows.sort(key=key, reverse=reverse)
    return _csv(
        "wallets.csv",
        ["company", "owner_email", "status", "balance", "bought", "free", "used", "last_activity"],
        [
            [
                r.company,
                r.owner_email,
                r.status,
                f"{r.balance:.2f}",
                f"{r.bought:.2f}",
                f"{r.free:.2f}",
                f"{r.used:.2f}",
                r.last_activity_at.isoformat() if r.last_activity_at else "",
            ]
            for r in rows
        ],
    )


def _kinds(group: str) -> tuple[str, ...] | None:
    return {"payments": PAYMENT_KINDS, "usage": USAGE_KINDS}.get(group)


async def _ledger_rows(
    session: AsyncSession, workspace_id: str, group: str, limit: int | None, offset: int = 0
) -> tuple[int, list[CreditTransaction]]:
    where = [CreditTransaction.workspace_id == workspace_id]
    kinds = _kinds(group)
    if kinds:
        where.append(CreditTransaction.kind.in_(kinds))
    total = (await session.execute(select(func.count()).select_from(CreditTransaction).where(*where))).scalar_one()
    q = (
        select(CreditTransaction)
        .where(*where)
        .order_by(CreditTransaction.created_at.desc(), CreditTransaction.id.desc())
        .offset(offset)
    )
    if limit:
        q = q.limit(limit)
    return int(total), list((await session.execute(q)).scalars().all())


@router.get("/customers/{workspace_id}/ledger", response_model=Ledger)
async def ledger(
    workspace_id: str,
    group: Literal["all", "payments", "usage"] = "all",
    limit: int = Query(50, ge=1, le=200),
    offset: int = Query(0, ge=0),
    _: Principal = Depends(require("customers.view")),
    session: AsyncSession = Depends(get_session),
) -> Ledger:
    ws = await session.get(Workspace, workspace_id)
    if ws is None:
        raise HTTPException(404, "Customer not found")
    total, rows = await _ledger_rows(session, workspace_id, group, limit, offset)
    return Ledger(
        company=ws.name,
        balance=ws.credit_balance or Decimal("0"),
        total=total,
        items=[
            LedgerRow(
                id=t.id,
                when=_utc(t.created_at) or datetime.now(UTC),
                kind=t.kind,
                label=KIND_LABEL.get(t.kind, t.kind),
                amount=t.amount,
                balance_after=t.balance_after,
                description=t.description,
                stage=t.stage,
                project_id=t.project_id,
            )
            for t in rows
        ],
    )


@router.get("/customers/{workspace_id}/ledger.csv")
async def ledger_csv(
    workspace_id: str,
    group: Literal["all", "payments", "usage"] = "all",
    _: Principal = Depends(require("customers.view")),
    session: AsyncSession = Depends(get_session),
) -> Response:
    ws = await session.get(Workspace, workspace_id)
    if ws is None:
        raise HTTPException(404, "Customer not found")
    _total, rows = await _ledger_rows(session, workspace_id, group, None)
    return _csv(
        f"wallet-{workspace_id[:8]}-{group}.csv",
        ["when", "type", "amount", "balance_after", "description", "stage", "project_id"],
        [
            [
                t.created_at.isoformat(),
                KIND_LABEL.get(t.kind, t.kind),
                f"{t.amount:.2f}",
                f"{t.balance_after:.2f}",
                t.description or "",
                t.stage or "",
                t.project_id or "",
            ]
            for t in rows
        ],
    )
