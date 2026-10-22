from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.config import get_settings
from app.integrations import registry
from app.models import AuditLog, CreditTransaction, Project, SystemSetting, Workspace
from app.pipeline.queue import get_queue
from app.services import ledger
from tests.conftest import OPS, OWNER
from tests.helpers import invite, make_awaiting_founder, make_final_ready, record


async def ledger_total(maker, wid):
    async with maker() as s:
        return await ledger.ledger_sum(s, wid), (await s.get(Workspace, wid)).credit_balance


async def test_ledger_always_sums_to_balance_across_a_full_interview(client, workspace, maker):
    pid = await make_awaiting_founder(client)
    token = await invite(client, pid)
    await record(client, token, 0)
    await record(client, token, 1)
    await client.post(f"/v1/interview/{token}/submit")
    await client.post(f"/v1/projects/{pid}/interview/merge", headers=OWNER)
    await get_queue().drain()
    total, balance = await ledger_total(maker, workspace)
    assert total == balance and balance < Decimal("10")
    async with maker() as s:
        p = await s.get(Project, pid)
        vendor_cost = (
            await s.execute(select(func.sum(CreditTransaction.vendor_cost)).where(CreditTransaction.project_id == pid))
        ).scalar_one()
    assert vendor_cost == p.cost_total > 0  # what we paid vendors == what the project says it cost


async def test_failed_attempts_net_to_zero_in_the_ledger(client, workspace, maker):
    from app.integrations.avatar.mock import MockAvatarProvider

    class Flaky(MockAvatarProvider):
        async def generate(self, req):
            raise RuntimeError("down")

    registry.override(avatar=Flaky())
    pid = await make_final_ready(client)
    total, balance = await ledger_total(maker, workspace)
    assert total == balance == Decimal("10")
    async with maker() as s:
        kinds = {
            t.kind
            for t in (await s.execute(select(CreditTransaction).where(CreditTransaction.project_id == pid))).scalars()
        }
    assert kinds == set()  # the failed attempt rolled back whole: nothing charged, nothing to reconcile
    assert (await client.get(f"/v1/projects/{pid}", headers=OWNER)).json()["state"] == "failed"


async def test_markup_charges_customer_more_than_vendor_cost(client, workspace, maker, monkeypatch):
    monkeypatch.setattr(get_settings(), "credit_markup", "3")
    pid = await make_final_ready(client)
    async with maker() as s:
        p = await s.get(Project, pid)
        charged = -(
            await s.execute(select(func.sum(CreditTransaction.amount)).where(CreditTransaction.project_id == pid))
        ).scalar_one()
    assert charged == p.cost_total * 3
    total, balance = await ledger_total(maker, workspace)
    assert total == balance == Decimal("10") - charged


async def test_markup_applies_to_the_balance_check(client, workspace, maker, monkeypatch):
    monkeypatch.setattr(get_settings(), "credit_markup", "1000")  # same vendor cost, now unaffordable
    pid = await make_final_ready(client)
    assert (await client.get(f"/v1/projects/{pid}", headers=OWNER)).json()["state"] == "limit_reached"
    total, balance = await ledger_total(maker, workspace)
    assert total == balance == Decimal("10")


async def test_operator_pause_switch_stops_paid_steps_and_resumes(client, workspace, maker):
    async with maker() as s:
        s.add(SystemSetting(key="paid_steps_paused", value={"paused": True}))
        await s.commit()
    pid = await make_final_ready(client)
    p = (await client.get(f"/v1/projects/{pid}", headers=OWNER)).json()
    assert p["state"] == "limit_reached" and "paused for maintenance" in p["failure_reason"]
    total, balance = await ledger_total(maker, workspace)
    assert balance == Decimal("10") and total == Decimal("10")
    async with maker() as s:
        (await s.get(SystemSetting, "paid_steps_paused")).value = {"paused": False}
        await s.commit()
    await client.post(f"/v1/projects/{pid}/retry", headers=OWNER)
    await get_queue().drain()
    assert (await client.get(f"/v1/projects/{pid}", headers=OWNER)).json()["state"] == "final_ready"


async def test_low_balance_email_sent_once_and_rearmed_by_topup(client, workspace, maker):
    import asyncio

    async with maker() as s:  # leave just enough for one video, so the balance ends below the threshold
        ws = await s.get(Workspace, workspace)
        await ledger.apply(s, ws, Decimal("-9.8"), "adjustment")
        await s.commit()
    registry.get_email().sent.clear()
    await make_final_ready(client)
    await asyncio.sleep(0.05)
    low = [m for m in registry.get_email().sent if m["subject"].startswith("You're running low")]
    assert {m["to"] for m in low} == {"owner@acme.test", "ops@example.com"} and "/billing" in low[0]["text"]
    async with maker() as s:
        ws = await s.get(Workspace, workspace)
        assert ws.low_balance_alerted is True
        await ledger.apply(s, ws, Decimal("20"), "purchase", ref="pay_1")
        await s.commit()
        assert ws.low_balance_alerted is False  # armed again


async def test_ref_makes_credits_idempotent(client, workspace, maker):
    async with maker() as s:
        ws = await s.get(Workspace, workspace)
        first = await ledger.apply(s, ws, Decimal("5"), "purchase", ref="pay_abc")
        again = await ledger.apply(s, ws, Decimal("5"), "purchase", ref="pay_abc")
        await s.commit()
        assert first is not None and again is None and ws.credit_balance == Decimal("15")
    total, balance = await ledger_total(maker, workspace)
    assert total == balance


async def test_operator_balance_edit_is_a_ledger_adjustment_and_audited(client, workspace, maker):
    r = await client.patch(f"/v1/admin/workspaces/{workspace}", json={"credit_balance": "25"}, headers=OPS)
    assert r.status_code == 200
    async with maker() as s:
        adj = (await s.execute(select(CreditTransaction).where(CreditTransaction.kind == "adjustment"))).scalar_one()
        assert (
            adj.amount == Decimal("15") and adj.balance_after == Decimal("25") and "ops@example.com" in adj.description
        )
        log = (await s.execute(select(AuditLog).where(AuditLog.action == "workspace.update"))).scalar_one()
        assert log.actor == "ops@example.com" and log.target_id == workspace and log.detail["credit_balance"] == "25"
    total, balance = await ledger_total(maker, workspace)
    assert total == balance == Decimal("25")


async def test_invite_grant_is_in_the_ledger(client, workspace, maker):
    r = await client.post(
        "/v1/admin/invites",
        json={"email": "new@startup.example.com", "workspace_name": "NewCo", "credits": "12"},
        headers=OPS,
    )
    wid = r.json()["workspace_id"]
    total, balance = await ledger_total(maker, wid)
    assert total == balance == Decimal("12")
    async with maker() as s:
        assert (await s.execute(select(AuditLog).where(AuditLog.action == "invite.create"))).scalar_one().detail[
            "credits"
        ] == "12"


@pytest.mark.parametrize("bad", ["", "-"])
def test_markup_default_is_pass_through(bad):
    assert get_settings().credit_markup == "1"
