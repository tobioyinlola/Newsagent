"""The credit ledger. EVERY change to a workspace's credit_balance goes through `apply`, so the ledger always
sums to the balance (a test enforces it). Rows are append-only and outlive a deleted workspace."""

from decimal import Decimal

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import CreditTransaction, Workspace

KINDS = {"grant", "purchase", "adjustment", "usage", "usage_adjust", "usage_release"}


async def apply(
    session: AsyncSession,
    ws: Workspace,
    amount: Decimal,
    kind: str,
    *,
    project_id: str | None = None,
    stage: str | None = None,
    vendor: str | None = None,
    vendor_cost: Decimal | None = None,
    ref: str | None = None,
    description: str | None = None,
) -> CreditTransaction | None:
    """Add `amount` (signed) to the balance and record it. With `ref`, a repeat call is a no-op (returns None):
    that is what makes payment webhooks safe to deliver twice."""
    assert kind in KINDS, kind
    if ref is not None:
        exists = (
            await session.execute(
                select(CreditTransaction.id).where(
                    CreditTransaction.workspace_id == ws.id, CreditTransaction.ref == ref
                )
            )
        ).first()
        if exists:
            return None
    ws.credit_balance = (ws.credit_balance or Decimal("0")) + amount
    if kind in {"grant", "purchase", "adjustment"} and amount > 0:
        ws.low_balance_alerted = False  # topped up: arm the low-balance alert again
    tx = CreditTransaction(
        workspace_id=ws.id,
        kind=kind,
        amount=amount,
        balance_after=ws.credit_balance,
        project_id=project_id,
        stage=stage,
        vendor=vendor,
        vendor_cost=vendor_cost,
        ref=ref,
        description=description,
    )
    try:
        async with session.begin_nested():  # a savepoint: losing a race on `ref` must not roll back the caller
            session.add(tx)
            await session.flush()
    except IntegrityError:
        ws.credit_balance -= amount
        return None
    return tx


async def ledger_sum(session: AsyncSession, workspace_id: str) -> Decimal:
    return (
        await session.execute(
            select(func.coalesce(func.sum(CreditTransaction.amount), 0)).where(
                CreditTransaction.workspace_id == workspace_id
            )
        )
    ).scalar_one()
