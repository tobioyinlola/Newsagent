"""Spend guard (spec section 7). Every paid step reserves before running and settles after.

Reserve holds the estimate against: workspace credit balance, workspace spend cap and the vendor's
monthly budget. A refused reserve changes nothing (a refused step costs nothing).
"""

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import SystemSetting, VendorBudget, Workspace
from app.models.base import new_id
from app.services import ledger

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
    amount: Decimal  # vendor cost estimate (what the vendor will charge us)
    charge: Decimal  # credits held from the customer (amount x markup)
    project_id: str | None = None
    stage: str | None = None


def _period(now: datetime | None = None) -> str:
    return (now or datetime.now(UTC)).strftime("%Y-%m")


def markup() -> Decimal:
    return Decimal(get_settings().credit_markup)


async def is_paused(session: AsyncSession) -> bool:
    row = await session.get(SystemSetting, "paid_steps_paused")
    return bool(row and row.value.get("paused"))


class SpendGuard:
    def __init__(self, session: AsyncSession, on_alert=None, on_low_balance=None) -> None:
        self.session = session
        self.on_alert = on_alert  # callable(vendor, period, spent, limit) -> None
        self.on_low_balance = on_low_balance  # callable(workspace_id, balance) -> None

    async def reserve(
        self,
        workspace_id: str,
        vendor: str,
        estimated_cost: float | Decimal,
        *,
        project_id: str | None = None,
        stage: str | None = None,
    ) -> Reservation:
        est = Decimal(str(estimated_cost))
        charge = est * markup()
        if await is_paused(self.session):  # operator kill switch
            raise LimitReached("Video creation is paused for maintenance. It will resume shortly.", "paused")
        ws = (
            await self.session.execute(select(Workspace).where(Workspace.id == workspace_id).with_for_update())
        ).scalar_one()
        if ws.suspended:
            raise LimitReached("This workspace is suspended.", "suspended")
        if ws.credit_balance < charge:
            raise LimitReached("Not enough credits for this step.", "credits")
        if ws.spend_cap and ws.spent_total + charge > ws.spend_cap:
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

        await ledger.apply(
            self.session,
            ws,
            -charge,
            "usage",
            project_id=project_id,
            stage=stage,
            vendor=vendor,
            vendor_cost=est,
            description=f"{stage or 'step'} ({vendor}) estimate",
        )
        ws.spent_total += charge
        vb.spent += est
        await self._maybe_alert(vb)
        await self.session.flush()
        return Reservation(workspace_id, vendor, period, est, charge, project_id, stage)

    async def settle(self, res: Reservation, actual_cost: float | Decimal) -> Decimal:
        """Reconcile the hold with actual cost (refund the difference, or charge the overage)."""
        actual = Decimal(str(actual_cost))
        new_charge = actual * markup()
        await self._adjust(
            res, res.charge - new_charge, actual - res.amount, "usage_adjust", f"{res.stage or 'step'} actual"
        )
        await self._maybe_low_balance(res.workspace_id)
        return actual

    async def release(self, res: Reservation) -> None:
        """Step failed before incurring cost: return the whole hold."""
        await self._adjust(res, res.charge, -res.amount, "usage_release", f"{res.stage or 'step'} failed, released")

    async def _adjust(
        self, res: Reservation, credit_delta: Decimal, vendor_delta: Decimal, kind: str, note: str
    ) -> None:
        ws = (
            await self.session.execute(select(Workspace).where(Workspace.id == res.workspace_id).with_for_update())
        ).scalar_one()
        vb = (
            await self.session.execute(
                select(VendorBudget).where(VendorBudget.vendor == res.vendor, VendorBudget.period == res.period)
            )
        ).scalar_one()
        if credit_delta != 0 or vendor_delta != 0:
            await ledger.apply(
                self.session,
                ws,
                credit_delta,
                kind,
                project_id=res.project_id,
                stage=res.stage,
                vendor=res.vendor,
                vendor_cost=vendor_delta,
                description=note,
            )
        ws.spent_total -= credit_delta
        vb.spent += vendor_delta
        await self._maybe_alert(vb)
        await self.session.flush()

    async def _maybe_low_balance(self, workspace_id: str) -> None:
        ws = await self.session.get(Workspace, workspace_id)
        if ws and not ws.low_balance_alerted and ws.credit_balance < Decimal(get_settings().low_balance_threshold):
            ws.low_balance_alerted = True
            if self.on_low_balance:
                self.on_low_balance(ws.id, ws.credit_balance)

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
