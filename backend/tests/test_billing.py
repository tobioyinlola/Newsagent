import json
import re
from decimal import Decimal

from app.integrations import registry
from app.integrations.billing.mock import SIGNATURE_HEADER, sign
from app.models import Checkout, User, Workspace
from app.services import ledger
from tests.conftest import OPS, OWNER, VIDEO
from tests.helpers import make_final_ready

SECRET = "dev-billing-secret"


TEN = Decimal("3.70")  # what $10 buys at $2.70 a credit


def event(checkout_id, status="paid", amount="10", eid=None):
    body = json.dumps(
        {"id": eid or f"evt_{checkout_id}", "checkout_id": checkout_id, "status": status, "amount_usd": amount}
    ).encode()
    return body, {SIGNATURE_HEADER: sign(body, SECRET), "content-type": "application/json"}


async def start_checkout(client, amount="10"):
    r = await client.post("/v1/billing/checkout", json={"amount_usd": amount}, headers=OWNER)
    assert r.status_code == 200, r.text
    return r.json()["checkout_id"]


async def balance(maker, wid):
    async with maker() as s:
        return (await s.get(Workspace, wid)).credit_balance


async def test_credits_are_sold_in_fixed_amounts_at_2_70_a_credit(client, workspace):
    options = (await client.get("/v1/billing/options", headers=OWNER)).json()
    assert [(Decimal(o["amount_usd"]), Decimal(o["credits"]), o["videos"]) for o in options] == [
        (Decimal("1"), Decimal("0.37"), 0),
        (Decimal("10"), Decimal("3.70"), 3),
        (Decimal("50"), Decimal("18.52"), 18),
        (Decimal("100"), Decimal("37.04"), 37),
        (Decimal("200"), Decimal("74.07"), 74),
    ]
    for amount in ("5", "9.99", "25", "10.5", "1000", "0", "-10"):  # nothing but the amounts on offer can be bought
        r = await client.post("/v1/billing/checkout", json={"amount_usd": amount}, headers=OWNER)
        assert r.status_code == 422, amount
    assert (await client.get("/v1/billing/options")).status_code == 401  # signed in to buy
    assert (await client.post("/v1/admin/packs", json={}, headers=OPS)).status_code in (
        404,
        405,
    )  # no more custom packs


async def test_the_checkout_is_for_exactly_the_amount_and_credits_on_offer(client, workspace, maker):
    for amount, credits in (("1", "0.37"), ("10", "3.70"), ("50", "18.52"), ("100", "37.04"), ("200", "74.07")):
        co = await start_checkout(client, amount)
        async with maker() as s:
            row = await s.get(Checkout, co)
            assert (row.amount_usd, row.credits) == (Decimal(amount), Decimal(credits))


async def test_paid_webhook_grants_credits_once(client, workspace, maker):
    co = await start_checkout(client)
    body, headers = event(co)
    r = await client.post("/v1/webhooks/billing", content=body, headers=headers)
    assert r.status_code == 200 and r.json()["result"] == "granted"
    assert await balance(maker, workspace) == Decimal("10") + TEN
    again = await client.post("/v1/webhooks/billing", content=body, headers=headers)  # provider retries delivery
    assert again.json()["result"] == "duplicate" and await balance(maker, workspace) == Decimal("10") + TEN
    other_event = event(co, eid="evt_other")  # even a different event id for the same checkout can't pay twice
    assert (await client.post("/v1/webhooks/billing", content=other_event[0], headers=other_event[1])).json()[
        "result"
    ] == "duplicate"
    assert await balance(maker, workspace) == Decimal("10") + TEN
    async with maker() as s:
        assert (await s.get(Checkout, co)).status == "paid"
        assert await ledger.ledger_sum(s, workspace) == Decimal("10") + TEN
    assert any(m["subject"] == "Credits added" for m in registry.get_email().sent)


async def test_bad_or_missing_signature_is_rejected_and_grants_nothing(client, workspace, maker):
    co = await start_checkout(client)
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
    co = await start_checkout(client)
    cheap = event(co, amount="1")  # a payment that is not for the amount asked grants nothing
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
    co = await start_checkout(client, "50")
    r = await client.post(f"/v1/billing/dev/pay/{co}", headers=OWNER)
    assert r.json()["result"] == "granted" and await balance(maker, workspace) == Decimal("10") + Decimal("18.52")


async def test_cannot_pay_another_workspaces_checkout_via_dev_endpoint(client, workspace, maker):
    co = await start_checkout(client)
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
    assert {ln["stage"] for ln in st["lines"]} >= {"video", "anchor", "preview", "final"}
    assert Decimal(st["total_credits"]) == Decimal("10") - await balance(maker, workspace) >= VIDEO
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
    assert Decimal(s["credit_balance"]) == Decimal("10") and Decimal(s["low_balance_threshold"]) == Decimal("1")
    assert (Decimal(s["credits_per_video"]), Decimal(s["usd_per_credit"]), s["videos_left"]) == (1, Decimal("2.7"), 10)


async def test_the_amounts_on_sale_are_public_for_the_landing_page(client, workspace):
    r = await client.get("/v1/public/credit-options")
    assert r.status_code == 200
    assert [Decimal(o["amount_usd"]) for o in r.json()] == [Decimal(a) for a in (1, 10, 50, 100, 200)]


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


# ---------- the credit system: one credit a video, one free video, then buy ----------
async def new_workspace(client, email="free@startup.example.com"):
    """A business that signed up on its own, with what a new workspace is given."""
    r = await client.post(
        "/v1/auth/signup/start",
        json={
            "email": email,
            "business_name": "FreeCo",
            "password": "correct horse battery",
            "city": "Lagos",
            "country": "Nigeria",
            "industry": "technology",
        },
    )
    assert r.status_code == 200, r.text
    code = re.search(r"\b(\d{6})\b", [m for m in registry.get_email().sent if m["to"] == email][-1]["text"]).group(1)
    r = await client.post("/v1/auth/signup/verify", json={"email": email, "code": code})
    assert r.status_code == 200, r.text
    return {"Authorization": f"Bearer {r.json()['token']}"}


async def test_a_new_business_gets_one_free_video_then_has_to_buy_credits(client, workspace, maker):
    from tests.helpers import BRIEF

    me = await new_workspace(client)
    assert Decimal((await client.get("/v1/billing/summary", headers=me)).json()["credit_balance"]) == Decimal("1")

    first = await client.post("/v1/projects", json=BRIEF, headers=me)  # the free video
    assert first.status_code == 200, first.text
    s = (await client.get("/v1/billing/summary", headers=me)).json()
    assert Decimal(s["credit_balance"]) == 0 and s["videos_left"] == 0

    second = await client.post("/v1/projects", json=BRIEF, headers=me)  # out of credits: nothing starts
    assert second.status_code == 402
    detail = second.json()["detail"]
    assert detail["error"] == "insufficient_credits" and "Buy credits" in detail["message"]
    assert Decimal(detail["credit_balance"]) == 0 and Decimal(detail["credits_needed"]) == 1
    listing = (await client.get("/v1/projects", headers=me)).json()
    assert len(listing) == 1  # the refused attempt left no project behind

    # buying credits is what lets them go on
    co = (await client.post("/v1/billing/checkout", json={"amount_usd": "10"}, headers=me)).json()["checkout_id"]
    assert (await client.post(f"/v1/billing/dev/pay/{co}", headers=me)).json()["result"] == "granted"
    assert Decimal((await client.get("/v1/billing/summary", headers=me)).json()["credit_balance"]) == TEN
    for _ in range(3):  # $10 = 3.70 credits = three videos, with 0.70 left over
        assert (await client.post("/v1/projects", json=BRIEF, headers=me)).status_code == 200
    assert (await client.post("/v1/projects", json=BRIEF, headers=me)).status_code == 402
    assert Decimal((await client.get("/v1/billing/summary", headers=me)).json()["credit_balance"]) == Decimal("0.70")


async def test_a_video_costs_one_credit_once_and_the_ledger_shows_it(client, workspace, maker, monkeypatch):
    from app.config import get_settings
    from tests.helpers import BRIEF

    monkeypatch.setattr(get_settings(), "credit_markup", "0")  # as shipped: the steps take nothing more
    pid = await make_final_ready(client)
    entries = (await client.get("/v1/billing/ledger", headers=OWNER)).json()
    video = [e for e in entries if e["stage"] == "video"]
    assert len(video) == 1 and Decimal(video[0]["amount"]) == -1 and video[0]["project_id"] == pid
    assert await balance(maker, workspace) == Decimal("10") - VIDEO  # a finished video took one credit and nothing else
    async with maker() as s:
        assert await ledger.ledger_sum(s, workspace) == await balance(maker, workspace)
    assert (
        await client.post("/v1/projects", json=BRIEF, headers=OWNER)
    ).status_code == 200  # a second video: a second credit
    assert await balance(maker, workspace) == Decimal("10") - 2 * VIDEO


async def test_two_videos_started_at_once_cannot_both_use_the_last_credit(client, workspace, maker):
    import asyncio

    from tests.helpers import BRIEF

    async with maker() as s:
        ws = await s.get(Workspace, workspace)
        await ledger.apply(s, ws, Decimal("-9"), "adjustment")  # one credit left
        await s.commit()
    codes = sorted(
        r.status_code
        for r in await asyncio.gather(*(client.post("/v1/projects", json=BRIEF, headers=OWNER) for _ in range(2)))
    )
    assert codes[0] == 200 and codes[1] in (200, 402)
    assert await balance(maker, workspace) >= 0
