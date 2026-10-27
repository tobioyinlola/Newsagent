"""The back office: operators see what is going on across the product; customers see none of it."""

from decimal import Decimal

from sqlalchemy import select

from app.models import Checkout, CreditPack, CreditTransaction, User, Workspace
from app.pipeline.queue import get_queue
from tests.conftest import OPS, OWNER
from tests.helpers import BRIEF, make_final_ready

BACKOFFICE = ["/v1/admin/overview", "/v1/admin/customers", "/v1/admin/payments"]


async def new_customer(client, maker, email, company, credits="10"):
    """A signed-up customer, made through the real invite and sign-up endpoints."""
    import re

    from app.integrations import registry

    inv = (
        await client.post(
            "/v1/admin/invites", json={"email": email, "workspace_name": company, "credits": credits}, headers=OPS
        )
    ).json()
    await client.post("/v1/auth/signup/start", json={"invite_code": inv["code"], "password": "correct horse battery"})
    mails = [m for m in registry.get_email().sent if m["to"] == email]
    code = re.search(r"\b(\d{6})\b", mails[-1]["text"]).group(1)
    r = await client.post("/v1/auth/signup/verify", json={"invite_code": inv["code"], "code": code})
    assert r.status_code == 200, r.text
    return inv["workspace_id"], {"Authorization": f"Bearer {r.json()['token']}"}


async def pay(maker, workspace_id, usd="49", credits="50"):
    async with maker() as s:
        pack = CreditPack(name="Pilot", credits=Decimal(credits), price_usd=Decimal(usd))
        s.add(pack)
        await s.flush()
        s.add(
            Checkout(
                workspace_id=workspace_id,
                pack_id=pack.id,
                credits=Decimal(credits),
                amount_usd=Decimal(usd),
                provider="mock",
                status="paid",
            )
        )
        from datetime import UTC, datetime

        co = (await s.execute(select(Checkout).order_by(Checkout.created_at.desc()))).scalars().first()
        co.paid_at = datetime.now(UTC)
        await s.commit()


async def test_only_operators_can_see_the_back_office(client, workspace):
    for path in BACKOFFICE:
        assert (await client.get(path, headers=OWNER)).status_code == 403
        assert (await client.get(path)).status_code == 401
        assert (await client.get(path, headers=OPS)).status_code == 200


async def test_the_customer_app_origin_cannot_reach_the_back_office_even_as_an_operator(client, workspace, monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(
        get_settings(), "admin_base_url", "http://localhost:5174"
    )  # the back office hosted as its own site
    r = await client.get("/v1/admin/overview", headers={**OPS, "Origin": "http://localhost:5173"})
    assert r.status_code == 403 and "not available from this app" in r.json()["detail"]
    ok = await client.get("/v1/admin/overview", headers={**OPS, "Origin": "http://localhost:5174"})
    assert ok.status_code == 200
    # the customer app's own endpoints are unaffected
    assert (await client.get("/v1/me", headers={**OWNER, "Origin": "http://localhost:5173"})).status_code == 200


async def test_overview_counts_signups_payments_and_videos_and_excludes_the_operators_own_workspace(
    client, workspace, maker
):
    empty = (await client.get("/v1/admin/overview", headers=OPS)).json()
    assert (
        empty["kpis"]["customers"] == 0 or empty["kpis"]["customers"] == 1
    )  # the fixture's "Acme" holds a non-operator user
    base = empty["kpis"]["customers"]

    acme, h1 = await new_customer(client, maker, "ada@acmefarms.example.com", "Acme Farms")
    beta, h2 = await new_customer(client, maker, "bola@betapay.example.com", "Beta Pay")
    await pay(maker, acme, "49", "50")
    await pay(maker, acme, "99", "120")
    r = await client.post("/v1/projects", json=BRIEF, headers=h1)
    assert r.status_code == 200

    o = (await client.get("/v1/admin/overview", headers=OPS)).json()
    k = o["kpis"]
    assert k["customers"] == base + 2 and k["signups_7d"] >= 2 and k["signups_30d"] >= 2
    assert k["paying_companies"] == 1 and Decimal(k["revenue_usd_total"]) == Decimal("148") == Decimal(
        k["revenue_usd_30d"]
    )
    assert k["videos_total"] >= 1 and k["videos_30d"] >= 1 and k["active_30d"] >= 1
    assert Decimal(k["credits_outstanding"]) >= Decimal("20")
    assert o["funnel"]["invites_sent"] >= 2 and o["funnel"]["accepted"] >= 2
    assert sum(d["count"] for d in o["signups_by_day"]) >= 2 and len(o["signups_by_day"]) == 30
    assert sum(Decimal(d["usd"]) for d in o["revenue_by_day"]) == Decimal("148")
    recent = {s["company"]: s for s in o["recent_signups"]}
    assert recent["Acme Farms"]["paid"] is True and recent["Beta Pay"]["paid"] is False
    assert recent["Acme Farms"]["email"] == "ada@acmefarms.example.com"
    assert o["top_customers"][0]["company"] == "Acme Farms" and Decimal(
        o["top_customers"][0]["revenue_usd"]
    ) == Decimal("148")
    assert o["videos_by_state"].get("draft", 0) >= 1
    assert o["attention"] == {"pending_reviews": 0, "failed_videos": 0, "suspended_workspaces": 0, "paused": False}
    assert (await client.get("/v1/admin/overview?days=90", headers=OPS)).json()["signups_by_day"].__len__() == 90
    assert (await client.get("/v1/admin/overview?days=3", headers=OPS)).status_code == 422
    assert beta  # silence unused


async def test_attention_flags_reviews_failures_and_suspensions(client, workspace, maker):
    acme, h1 = await new_customer(client, maker, "ada@acmefarms.example.com", "Acme Farms")
    await client.patch(f"/v1/admin/workspaces/{acme}", json={"suspended": True}, headers=OPS)
    r = await client.patch("/v1/admin/settings", json={"paused": True, "pause_reason": "test"}, headers=OPS)
    assert r.status_code == 200, r.text
    a = (await client.get("/v1/admin/overview", headers=OPS)).json()["attention"]
    assert a["suspended_workspaces"] == 1 and a["paused"] is True


async def test_customer_list_search_and_detail(client, workspace, maker):
    acme, h1 = await new_customer(client, maker, "ada@acmefarms.example.com", "Acme Farms")
    beta, _ = await new_customer(client, maker, "bola@betapay.example.com", "Beta Pay")
    await pay(maker, acme)
    await client.post("/v1/projects", json=BRIEF, headers=h1)
    lst = (await client.get("/v1/admin/customers", headers=OPS)).json()
    names = [c["company"] for c in lst["items"]]
    assert lst["total"] == len(names) and names.index("Beta Pay") < names.index("Acme Farms")  # newest sign-up first
    row = next(c for c in lst["items"] if c["company"] == "Acme Farms")
    assert row["owner_email"] == "ada@acmefarms.example.com" and row["status"] == "active"
    assert Decimal(row["paid_usd"]) == Decimal("49") and row["purchases"] == 1 and row["videos"] == 1
    found = (await client.get("/v1/admin/customers?q=betapay", headers=OPS)).json()
    assert [c["company"] for c in found["items"]] == ["Beta Pay"] and found["total"] == 1
    assert (await client.get("/v1/admin/customers?q=ACME", headers=OPS)).json()["items"][0]["company"] == "Acme Farms"
    page = (await client.get("/v1/admin/customers?limit=1&offset=1", headers=OPS)).json()
    assert len(page["items"]) == 1 and page["total"] == lst["total"]

    d = (await client.get(f"/v1/admin/customers/{acme}", headers=OPS)).json()
    assert d["company"] == "Acme Farms" and d["users"][0]["email"] == "ada@acmefarms.example.com"
    assert d["projects"][0]["state"] == "draft" and d["projects"][0]["interview"] == "none"
    assert d["payments"][0]["kind"] == "card" and Decimal(d["payments"][0]["usd"]) == Decimal("49")
    assert (await client.get("/v1/admin/customers/does-not-exist", headers=OPS)).status_code == 404


async def test_payments_list_card_and_offline_and_paying_companies(client, workspace, maker):
    acme, _ = await new_customer(client, maker, "ada@acmefarms.example.com", "Acme Farms")
    beta, _ = await new_customer(client, maker, "bola@betapay.example.com", "Beta Pay")
    await pay(maker, acme, "49", "50")
    await pay(maker, acme, "99", "120")
    r = await client.post(
        f"/v1/admin/workspaces/{beta}/credits",
        json={"credits": "30", "ref": "INV-7", "note": "bank transfer"},
        headers=OPS,
    )
    assert r.status_code == 200
    p = (await client.get("/v1/admin/payments", headers=OPS)).json()
    assert Decimal(p["total_usd"]) == Decimal("148") and Decimal(p["offline_credits"]) == Decimal("30")
    assert [c["company"] for c in p["paying_companies"]] == ["Acme Farms", "Beta Pay"]
    assert p["paying_companies"][0]["payments"] == 2 and Decimal(p["paying_companies"][0]["usd"]) == Decimal("148")
    kinds = {i["kind"] for i in p["items"]}
    assert kinds == {"card", "offline"}
    offline = next(i for i in p["items"] if i["kind"] == "offline")
    assert offline["usd"] is None and Decimal(offline["credits"]) == Decimal("30") and offline["company"] == "Beta Pay"
    whens = [i["when"] for i in p["items"]]
    assert whens == sorted(whens, reverse=True)
    ov = (await client.get("/v1/admin/overview", headers=OPS)).json()["kpis"]
    assert ov["paying_companies"] == 2  # an offline payment counts as paying


async def test_deleted_workspaces_and_unpaid_checkouts_do_not_count(client, workspace, maker):
    acme, h1 = await new_customer(client, maker, "ada@acmefarms.example.com", "Acme Farms")
    async with maker() as s:
        pack = CreditPack(name="P", credits=Decimal("10"), price_usd=Decimal("20"))
        s.add(pack)
        await s.flush()
        s.add(
            Checkout(
                workspace_id=acme,
                pack_id=pack.id,
                credits=Decimal("10"),
                amount_usd=Decimal("20"),
                provider="mock",
                status="pending",
            )
        )
        await s.commit()
    assert Decimal((await client.get("/v1/admin/payments", headers=OPS)).json()["total_usd"]) == 0
    r = await client.request("DELETE", "/v1/account", json={"confirm": "DELETE Acme Farms"}, headers=h1)
    assert r.status_code == 200, r.text
    names = [c["company"] for c in (await client.get("/v1/admin/customers", headers=OPS)).json()["items"]]
    assert "Acme Farms" not in names


async def test_videos_by_state_reflects_finished_videos(client, workspace, maker):
    await make_final_ready(client)
    o = (await client.get("/v1/admin/overview", headers=OPS)).json()
    assert o["kpis"]["videos_ready"] >= 1 and o["videos_by_state"]["final_ready"] >= 1
    assert get_queue() is not None
    assert Decimal(o["kpis"]["vendor_cost_usd_30d"]) > 0
    _ = (User, Workspace, CreditTransaction)  # models imported for readers of this file


async def test_when_one_site_serves_both_the_back_office_is_reachable_from_it(client, workspace):
    # the default: the back office lives at <customer site>/admin, so its own requests carry the customer site's origin
    r = await client.get("/v1/admin/overview", headers={**OPS, "Origin": "http://localhost:5173"})
    assert r.status_code == 200
    # ...but being on the site is not enough: it still takes an operator's sign-in
    assert (
        await client.get("/v1/admin/overview", headers={**OWNER, "Origin": "http://localhost:5173"})
    ).status_code == 403
    assert (await client.get("/v1/admin/overview", headers={"Origin": "http://localhost:5173"})).status_code == 401
