from decimal import Decimal

import pytest
from sqlalchemy import select

from app.models import VendorBudget, Workspace
from app.services.spend_guard import LimitReached, SpendGuard


async def _state(maker, wid):
    async with maker() as s:
        ws = await s.get(Workspace, wid)
        vb = (await s.execute(select(VendorBudget).where(VendorBudget.vendor == "heygen"))).scalar_one()
        return ws.credit_balance, ws.spent_total, vb.spent


async def test_reserve_and_settle_refunds_difference(maker, workspace):
    async with maker() as s:
        g = SpendGuard(s)
        r = await g.reserve(workspace, "heygen", 2)
        await g.settle(r, 1.5)
        await s.commit()
    assert await _state(maker, workspace) == (Decimal("8.5"), Decimal("1.5"), Decimal("1.5"))


@pytest.mark.parametrize(
    "setup,code",
    [
        (lambda ws, vb: setattr(ws, "credit_balance", Decimal("1")), "credits"),
        (lambda ws, vb: setattr(ws, "spend_cap", Decimal("1")), "workspace_cap"),
        (lambda ws, vb: setattr(vb, "limit", Decimal("1")), "vendor_budget"),
        (lambda ws, vb: setattr(ws, "suspended", True), "suspended"),
    ],
)
async def test_refused_step_costs_nothing(maker, workspace, setup, code):
    async with maker() as s:
        ws = await s.get(Workspace, workspace)
        vb = (await s.execute(select(VendorBudget).where(VendorBudget.vendor == "heygen"))).scalar_one()
        setup(ws, vb)
        await s.commit()
        before = (ws.credit_balance, ws.spent_total, vb.spent)
    async with maker() as s:
        with pytest.raises(LimitReached) as e:
            await SpendGuard(s).reserve(workspace, "heygen", 2)
        assert e.value.code == code
        await s.rollback()
    async with maker() as s:
        ws = await s.get(Workspace, workspace)
        vb = (await s.execute(select(VendorBudget).where(VendorBudget.vendor == "heygen"))).scalar_one()
        assert (ws.credit_balance, ws.spent_total, vb.spent) == before


async def test_missing_vendor_budget_fails_closed(maker, workspace):
    async with maker() as s:
        with pytest.raises(LimitReached) as e:
            await SpendGuard(s).reserve(workspace, "unknown", 0.01)
        assert e.value.code == "vendor_budget"


async def test_alert_at_80_percent_once(maker, workspace):
    alerts = []
    async with maker() as s:
        ws = await s.get(Workspace, workspace)
        ws.credit_balance, ws.spend_cap = Decimal("1000"), Decimal("1000")
        g = SpendGuard(s, on_alert=lambda *a: alerts.append(a))
        await g.reserve(workspace, "heygen", 79)
        assert not alerts
        await g.reserve(workspace, "heygen", 2)  # 81 > 80
        await g.reserve(workspace, "heygen", 1)
    assert len(alerts) == 1
