"""Spend guard (spec section 7). Every paid step reserves before running and settles after.

Reserve holds the estimate against: workspace credit balance, workspace spend cap and the vendor's
monthly budget. A refused reserve changes nothing (a refused step costs nothing).
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import VendorBudget, Workspace
from app.models.base import new_id

ALERT_THRESHOLD = Decimal("0.8")


class LimitReached(Exception):
    def __init__(self, reason: str, code: str) -> None:
        super().__init__(reason)
        self.reason, self.code = reason, code


@dataclass
class Reservation:
    workspace_id: str
    vendor: str
    period: str
    amount: Decimal


def _period(now: datetime | None = None) -> str:
    return (now or datetime.now(UTC)).strftime("%Y-%m")


class SpendGuard:
    def __init__(self, session: AsyncSession, on_alert=None) -> None:
        self.session = session
        self.on_alert = on_alert  # callable(vendor, period, spent, limit) -> None

    async def reserve(self, workspace_id: str, vendor: str, estimated_cost: float | Decimal) -> Reservation:
        est = Decimal(str(estimated_cost))
        ws = (
            await self.session.execute(select(Workspace).where(Workspace.id == workspace_id).with_for_update())
        ).scalar_one()
        if ws.suspended:
            raise LimitReached("This workspace is suspended.", "suspended")
        if ws.credit_balance < est:
            raise LimitReached("Not enough credits for this step.", "credits")
        if ws.spend_cap and ws.spent_total + est > ws.spend_cap:
            raise LimitReached("Workspace spend cap reached.", "workspace_cap")

        period = _period()
        vb = (
            await self.session.execute(
                select(VendorBudget)
                .where(VendorBudget.vendor == vendor, VendorBudget.period == period)
                .with_for_update()
            )
        ).scalar_one_or_none()
        if vb is None:
            # No budget row means no approved budget: fail closed.
            raise LimitReached(f"No monthly budget configured for {vendor}.", "vendor_budget")
        if vb.spent + est > vb.limit:
            raise LimitReached(f"Monthly budget for {vendor} reached.", "vendor_budget")

        ws.credit_balance -= est
        ws.spent_total += est
        vb.spent += est
        await self._maybe_alert(vb)
        await self.session.flush()
        return Reservation(workspace_id, vendor, period, est)

    async def settle(self, res: Reservation, actual_cost: float | Decimal) -> Decimal:
        """Reconcile the hold with actual cost (refund the difference, or charge the overage)."""
        actual = Decimal(str(actual_cost))
        diff = res.amount - actual
        await self._adjust(res, diff)
        return actual

    async def release(self, res: Reservation) -> None:
        """Step failed before incurring cost: return the whole hold."""
        await self._adjust(res, res.amount)

    async def _adjust(self, res: Reservation, refund: Decimal) -> None:
        ws = (
            await self.session.execute(select(Workspace).where(Workspace.id == res.workspace_id).with_for_update())
        ).scalar_one()
        vb = (
            await self.session.execute(
                select(VendorBudget).where(VendorBudget.vendor == res.vendor, VendorBudget.period == res.period)
            )
        ).scalar_one()
        ws.credit_balance += refund
        ws.spent_total -= refund
        vb.spent -= refund
        await self._maybe_alert(vb)
        await self.session.flush()

    async def _maybe_alert(self, vb: VendorBudget) -> None:
        if vb.limit and not vb.alerted_80 and vb.spent >= vb.limit * ALERT_THRESHOLD:
            vb.alerted_80 = True
            if self.on_alert:
                self.on_alert(vb.vendor, vb.period, vb.spent, vb.limit)


async def ensure_vendor_budget(session: AsyncSession, vendor: str, limit: Decimal) -> VendorBudget:
    period = _period()
    vb = (
        await session.execute(select(VendorBudget).where(VendorBudget.vendor == vendor, VendorBudget.period == period))
    ).scalar_one_or_none()
    if vb is None:
        vb = VendorBudget(id=new_id(), vendor=vendor, period=period, limit=limit, spent=Decimal("0"))
        session.add(vb)
    else:
        vb.limit = limit
    await session.flush()
    return vb
