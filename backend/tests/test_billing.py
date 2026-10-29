import json
from decimal import Decimal

from app.integrations import registry
from app.integrations.billing.mock import SIGNATURE_HEADER, sign
from app.models import Checkout, User, Workspace
from app.services import ledger
from tests.conftest import OPS, OWNER
from tests.helpers import make_final_ready

SECRET = "dev-billing-secret"


async def make_pack(client, name="Starter", credits="20", price="25"):
    r = await client.post("/v1/admin/packs", json={"name": name, "credits": credits, "price_usd": price}, headers=OPS)
    assert r.status_code == 200, r.text
    return r.json()["id"]


def event(checkout_id, status="paid", amount="25", eid=None):
    body = json.dumps(
        {"id": eid or f"evt_{checkout_id}", "checkout_id": checkout_id, "status": status, "amount_usd": amount}
    ).encode()
    return body, {SIGNATURE_HEADER: sign(body, SECRET), "content-type": "application/json"}


async def start_checkout(client, pack_id):
    r = await client.post("/v1/billing/checkout", json={"pack_id": pack_id}, headers=OWNER)
    assert r.status_code == 200, r.text
    return r.json()["checkout_id"]


async def balance(maker, wid):
    async with maker() as s:
        return (await s.get(Workspace, wid)).credit_balance


async def test_packs_are_listed_and_inactive_ones_hidden(client, workspace):
    a = await make_pack(client, "Starter")
    b = await make_pack(client, "Old", "5", "7")
    await client.patch(f"/v1/admin/packs/{b}", json={"active": False}, headers=OPS)
    names = [p["name"] for p in (await client.get("/v1/billing/packs", headers=OWNER)).json()]
    assert names == ["Starter"] and a
    assert (await client.post("/v1/billing/checkout", json={"pack_id": b}, headers=OWNER)).status_code == 404
    assert (
        await client.post("/v1/admin/packs", json={"name": "x", "credits": "1", "price_usd": "1"}, headers=OWNER)
    ).status_code == 403


async def test_paid_webhook_grants_credits_once(client, workspace, maker):
    co = await start_checkout(client, await make_pack(client))
    body, headers = event(co)
    r = await client.post("/v1/webhooks/billing", content=body, headers=headers)
    assert r.status_code == 200 and r.json()["result"] == "granted"
    assert await balance(maker, workspace) == Decimal("30")
    again = await client.post("/v1/webhooks/billing", content=body, headers=headers)  # provider retries delivery
    assert again.json()["result"] == "duplicate" and await balance(maker, workspace) == Decimal("30")
    other_event = event(co, eid="evt_other")  # even a different event id for the same checkout can't pay twice
    assert (await client.post("/v1/webhooks/billing", content=other_event[0], headers=other_event[1])).json()[
        "result"
    ] == "duplicate"
    assert await balance(maker, workspace) == Decimal("30")
    async with maker() as s:
        assert (await s.get(Checkout, co)).status == "paid"
        assert await ledger.ledger_sum(s, workspace) == Decimal("30")
    assert any(m["subject"] == "Credits added" for m in registry.get_email().sent)


async def test_bad_or_missing_signature_is_rejected_and_grants_nothing(client, workspace, maker):
    co = await start_checkout(client, await make_pack(client))
    body, _ = event(co)
    for headers in ({}, {SIGNATURE_HEADER: "deadbeef"}, {SIGNATURE_HEADER: sign(body, "wrong-secret")}):
        r = await client.post("/v1/webhooks/billing", content=body, headers=headers)
        assert r.status_code == 401
    tampered = body.replace(b'"paid"', b'"paid" ')  # signature no longer matches the body
    assert (
        await client.post("/v1/webhooks/billing", content=tampered, headers={SIGNATURE_HEADER: sign(body, SECRET)})
    ).status_code == 401
    assert await balance(maker, workspace) == Decimal("10")


async def test_amount_mismatch_and_unpaid_events_do_not_grant(client, workspace, maker):
    co = await start_checkout(client, await make_pack(client))
    cheap = event(co, amount="1")
    assert (await client.post("/v1/webhooks/billing", content=cheap[0], headers=cheap[1])).json()[
        "result"
    ] == "amount_mismatch"
    failed = event(co, status="failed", eid="evt_f")
    assert (await client.post("/v1/webhooks/billing", content=failed[0], headers=failed[1])).json()[
        "result"
    ] == "not_paid"
    unknown = event("nope")
    assert (await client.post("/v1/webhooks/billing", content=unknown[0], headers=unknown[1])).json()[
        "result"
    ] == "unknown_checkout"
    malformed = b"{not json"
    assert (
        await client.post(
            "/v1/webhooks/billing", content=malformed, headers={SIGNATURE_HEADER: sign(malformed, SECRET)}
        )
    ).status_code == 400
    assert await balance(maker, workspace) == Decimal("10")


async def test_dev_pay_flow_works_end_to_end_in_local_mode(client, workspace, maker):
    co = await start_checkout(client, await make_pack(client, credits="7", price="9"))
    r = await client.post(f"/v1/billing/dev/pay/{co}", headers=OWNER)
    assert r.json()["result"] == "granted" and await balance(maker, workspace) == Decimal("17")


async def test_cannot_pay_another_workspaces_checkout_via_dev_endpoint(client, workspace, maker):
    co = await start_checkout(client, await make_pack(client))
    async with maker() as s:
        ws = Workspace(name="Other")
        s.add(ws)
        await s.flush()
        s.add(User(email="other@example.com", workspace_id=ws.id))
        await s.commit()
    r = await client.post(f"/v1/billing/dev/pay/{co}", headers={"Authorization": "Bearer dev:other@example.com"})
    assert r.status_code == 404


async def test_manual_credit_is_idempotent_by_reference(client, workspace, maker):
    body = {"credits": "50", "ref": "INV-2026-001", "note": "bank transfer"}
    a = await client.post(f"/v1/admin/workspaces/{workspace}/credits", json=body, headers=OPS)
    b = await client.post(f"/v1/admin/workspaces/{workspace}/credits", json=body, headers=OPS)
    assert a.json()["duplicate"] is False and b.json()["duplicate"] is True
    assert await balance(maker, workspace) == Decimal("60")
    assert (await client.post(f"/v1/admin/workspaces/{workspace}/credits", json=body, headers=OWNER)).status_code == 403


async def test_usage_statement_matches_what_was_charged(client, workspace, maker):
    pid = await make_final_ready(client)
    st = (await client.get("/v1/billing/usage", headers=OWNER)).json()
    assert {ln["project_id"] for ln in st["lines"]} == {pid}
    assert {ln["stage"] for ln in st["lines"]} >= {"anchor", "preview", "final"}
    assert Decimal(st["total_credits"]) == Decimal("10") - await balance(maker, workspace) > 0
    csv = (await client.get("/v1/billing/usage.csv", headers=OWNER)).text.splitlines()
    assert csv[0] == "month,project_id,step,credits" and csv[-1].split(",")[2] == "TOTAL"
    assert (await client.get("/v1/billing/usage?month=2020-01", headers=OWNER)).json()["lines"] == []
    assert (await client.get("/v1/billing/usage?month=bad", headers=OWNER)).status_code == 422


async def test_usage_and_ledger_are_private_to_the_workspace(client, workspace, maker):
    await make_final_ready(client)
    async with maker() as s:
        ws = Workspace(name="Other", credit_balance=Decimal("0"))
        s.add(ws)
        await s.flush()
        s.add(User(email="other@example.com", workspace_id=ws.id))
        await ledger.apply(s, ws, Decimal("3"), "grant")
        await s.commit()
    other = {"Authorization": "Bearer dev:other@example.com"}
    assert (await client.get("/v1/billing/usage", headers=other)).json()["lines"] == []
    entries = (await client.get("/v1/billing/ledger", headers=other)).json()
    assert [e["kind"] for e in entries] == ["grant"]
    mine = (await client.get("/v1/billing/ledger", headers=OWNER)).json()
    assert len(mine) > 1 and all("vendor_cost" not in e for e in mine)  # customers never see our vendor costs


async def test_summary(client, workspace):
    s = (await client.get("/v1/billing/summary", headers=OWNER)).json()
    assert Decimal(s["credit_balance"]) == Decimal("10") and Decimal(s["low_balance_threshold"]) == Decimal("5")


async def test_the_packs_on_sale_are_public_for_the_landing_page(client, workspace):
    r = await client.get("/v1/public/packs")
    assert r.status_code == 200 and isinstance(r.json(), list)
    assert all({"name", "credits", "price_usd"} <= set(p) for p in r.json())


async def test_public_stats_count_finished_videos_and_shared_video_views(client, workspace):
    r = await client.get("/v1/public/stats")
    assert r.status_code == 200 and set(r.json()) == {"videos", "impressions"}


async def test_there_is_no_daily_video_limit(client, workspace):
    """A workspace can approve as many scripts in a day as its credits, spend cap and vendor budgets allow."""
    from tests.conftest import OWNER
    from tests.helpers import BRIEF

    for _ in range(6):  # the old limit was 3 a day
        pid = (await client.post("/v1/projects", json=BRIEF, headers=OWNER)).json()["id"]
        script = (await client.post(f"/v1/projects/{pid}/script/generate", headers=OWNER)).json()
        body = {k: script[k] for k in ("segments", "ticker_lines", "lower_thirds", "interview_questions")}
        await client.put(f"/v1/projects/{pid}/script", json=body, headers=OWNER)
        r = await client.post(f"/v1/projects/{pid}/script/approve", headers=OWNER)
        assert r.status_code == 200, r.text
    summary = await client.get("/v1/billing/summary", headers=OWNER)
    assert summary.status_code == 200 and "max_videos_per_day" not in summary.json()
