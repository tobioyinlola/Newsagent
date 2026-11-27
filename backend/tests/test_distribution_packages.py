import asyncio
from datetime import timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.config import get_settings
from app.models import CreditTransaction, DistributionPackage, Workspace
from app.models.base import utcnow
from app.services import credits
from app.services.package_seed import PACKAGES, ids_for
from tests.conftest import OPS, OWNER
from tests.test_distribution import distribution_data, draft  # noqa: F401


async def add(maker, **values):
    base = {"slug": "p1", "name": "Test package", "usd_price": Decimal("27.00"), "outlet_names": ["A", "B"], "outlet_ids": ["1", "2"],
            "local_prices": {"NGN": "40000"}, "includes": [], "kind": "regional", "region": "nigeria"}
    async with maker() as db:
        pkg = DistributionPackage(**{**base, **values})
        db.add(pkg)
        await db.commit()
        return pkg.id


def test_seed_matches_the_document():
    by = {p["slug"]: p for p in PACKAGES}
    assert len(PACKAGES) == 24 and len(by) == 24
    assert by["nigeria-startup-launch"]["usd_price"] == "651.57" and by["nigeria-startup-launch"]["local_prices"] == {"NGN": "912203.49"}
    assert by["bf-international-founder-deal"]["standard_usd"] == "1495.00" and by["bf-international-founder-deal"]["slots_total"] == 10
    assert by["bf-startup-visibility-deal"]["slots_total"] == 20 and by["cm-two-market-deal"]["slots_total"] == 15
    assert by["bf-executive-spotlight-deal"]["slots_total"] == 10 and by["cm-startup-portfolio-deal"]["slots_total"] == 5
    assert by["cm-startup-portfolio-deal"]["usd_price"] is None  # a custom quote
    assert by["global-portfolio-partnership"]["usd_price"] == "25000.00"
    assert ids_for(["Techbullion.com", "TechBullion", "CNN.com"]) == ["54"]  # one outlet, and CNN is not ours to write to


async def test_public_list_shows_state_and_price_in_credits(client, maker):
    await add(maker, slug="open")
    await add(maker, slug="quote", usd_price=None)
    await add(maker, slug="gone", slots_total=2, slots_taken=2)
    await add(maker, slug="late", ends_at=utcnow() - timedelta(days=1))
    await add(maker, slug="hidden", active=False)
    r = await client.get("/v1/public/distribution/packages")
    assert r.status_code == 200
    got = {p["slug"]: p for p in r.json()["packages"]}
    assert set(got) == {"open", "quote", "gone", "late"}
    assert got["open"]["state"] == "open" and Decimal(got["open"]["credits"]) == credits.credits_for_usd(Decimal("27"))
    assert got["quote"]["state"] == "quote" and got["quote"]["credits"] is None
    assert got["gone"]["state"] == "sold_out" and got["gone"]["slots_left"] == 0
    assert got["late"]["state"] == "ended"


async def test_buying_a_package_charges_its_price_once_and_takes_a_slot(client, distribution_data, maker, workspace):  # noqa: F811
    pid = await add(maker, slots_total=3)
    price = credits.credits_for_usd(Decimal("27"))
    async with maker() as db:
        ws = await db.get(Workspace, workspace)
        ws.credit_balance = price + Decimal("1")
        await db.commit()
    id = await draft(client, {**distribution_data, "outlet_ids": [], "package_id": pid})
    saved = (await client.get(f"/v1/distribution/{id}", headers=OWNER)).json()
    assert Decimal(saved["total_credits"]) == price and saved["data"]["outlet_ids"] == ["1", "2"]
    results = await asyncio.gather(*[client.post(f"/v1/distribution/{id}/submit", headers=OWNER) for _ in range(2)])
    assert all(r.status_code == 200 for r in results), [r.text for r in results]
    done = results[0].json()
    assert done["data"]["package"]["name"] == "Test package" and sum(Decimal(o["credits"]) for o in done["data"]["outlets"]) == price
    async with maker() as db:
        assert (await db.get(Workspace, workspace)).credit_balance == Decimal("1")
        assert (await db.get(DistributionPackage, pid)).slots_taken == 1  # a double click takes one slot
        txs = (await db.execute(select(CreditTransaction).where(CreditTransaction.ref == f"distribution:{id}"))).scalars().all()
        assert len(txs) == 1 and txs[0].amount == -price


async def test_last_slot_is_never_sold_twice(client, distribution_data, maker, workspace):  # noqa: F811
    pid = await add(maker, slots_total=1)
    price = credits.credits_for_usd(Decimal("27"))
    first = await draft(client, {**distribution_data, "outlet_ids": [], "package_id": pid})
    second = await draft(client, {**distribution_data, "outlet_ids": [], "package_id": pid})
    async with maker() as db:
        ws = await db.get(Workspace, workspace)
        ws.credit_balance = price * 2
        await db.commit()
    a = await client.post(f"/v1/distribution/{first}/submit", headers=OWNER)
    b = await client.post(f"/v1/distribution/{second}/submit", headers=OWNER)
    assert a.status_code == 200 and b.status_code == 409
    async with maker() as db:
        assert (await db.get(Workspace, workspace)).credit_balance == price  # only one was charged
        assert (await db.get(DistributionPackage, pid)).slots_taken == 1
    # the second is a draft again, and a sold-out package cannot even be chosen
    r = await client.put(f"/v1/distribution/{second}", headers=OWNER, json={**distribution_data, "outlet_ids": [], "package_id": pid})
    assert r.status_code == 422


@pytest.mark.parametrize("change", [{"usd_price": None}, {"ends_at": utcnow() - timedelta(hours=1)}, {"active": False}, {"starts_at": utcnow() + timedelta(days=1)}])
async def test_a_package_that_is_not_open_cannot_be_chosen(client, distribution_data, maker, change):  # noqa: F811
    pid = await add(maker, **change)
    r = await client.post("/v1/distribution", headers=OWNER)
    r = await client.put(f"/v1/distribution/{r.json()['id']}", headers=OWNER, json={**distribution_data, "package_id": pid})
    assert r.status_code == 422, r.text


async def test_a_package_without_our_outlets_is_one_line_for_the_team(client, distribution_data, maker, workspace):  # noqa: F811
    pid = await add(maker, slug="org", usd_price=Decimal("5000"), outlet_ids=[], outlet_names=[], includes=["Ten startups"], kind="organisation")
    price = credits.credits_for_usd(Decimal("5000"))
    async with maker() as db:
        ws = await db.get(Workspace, workspace)
        ws.credit_balance = price
        await db.commit()
    id = await draft(client, {**distribution_data, "outlet_ids": [], "package_id": pid})
    r = await client.post(f"/v1/distribution/{id}/submit", headers=OWNER)
    assert r.status_code == 200, r.text
    lines = r.json()["data"]["outlets"]
    assert len(lines) == 1 and Decimal(lines[0]["credits"]) == price and lines[0]["package"] is True


async def test_not_enough_credits_keeps_the_draft_and_the_slot(client, distribution_data, maker):  # noqa: F811
    pid = await add(maker, slots_total=2, usd_price=Decimal("2700"))
    id = await draft(client, {**distribution_data, "outlet_ids": [], "package_id": pid})
    r = await client.post(f"/v1/distribution/{id}/submit", headers=OWNER)
    assert r.status_code == 402
    async with maker() as db:
        assert (await db.get(DistributionPackage, pid)).slots_taken == 0


async def test_admin_edits_price_slots_and_dates(client, maker, workspace):
    pid = await add(maker, slots_total=5)
    r = await client.patch(f"/v1/admin/distribution-packages/{pid}", headers=OPS, json={"usd_price": "30.50", "slots_total": 9, "active": False})
    assert r.status_code == 200, r.text
    assert r.json()["usd_price"] == "30.50" and r.json()["slots_total"] == 9 and r.json()["state"] == "off"
    assert (await client.patch(f"/v1/admin/distribution-packages/{pid}", headers=OWNER, json={"active": True})).status_code in (401, 403)
    assert get_settings() is not None
    r = await client.patch(f"/v1/admin/distribution-packages/{pid}", headers=OPS, json={"clear_slots": True, "clear_price": True, "active": True})
    assert r.json()["slots_total"] is None and r.json()["state"] == "quote"


async def test_admin_adds_a_package_and_edits_all_of_it(client, maker, workspace):
    made = await client.post("/v1/admin/distribution-packages", headers=OPS, json={
        "name": "Ghana Startup Spotlight", "kind": "regional", "region": "africa", "usd_price": "300", "ideal_for": "Ghanaian startups",
        "outlets": ["Techbullion.com", "tech cabal", "Some Outlet We Do Not Hold"], "includes": ["A coverage report", "  "],
        "local_prices": {"ghs": "3,500"}, "slots_total": 4,
    })
    assert made.status_code == 200, made.text
    p = made.json()
    assert p["slug"] == "ghana-startup-spotlight" and p["state"] == "open" and p["slots_left"] == 4
    assert p["outlets"] == ["Techbullion.com", "tech cabal", "Some Outlet We Do Not Hold"]
    assert sorted(p["held"]) == ["Tech Cabal", "TechBullion"]  # the two we can write to; the third is arranged by hand
    assert p["includes"] == ["A coverage report"] and p["local_prices"] == {"GHS": "3500"}
    again = await client.post("/v1/admin/distribution-packages", headers=OPS, json={"name": "Ghana Startup Spotlight"})
    assert again.json()["slug"] == "ghana-startup-spotlight-2" and again.json()["state"] == "quote"  # no price yet
    r = await client.patch(f"/v1/admin/distribution-packages/{p['id']}", headers=OPS, json={"name": "Ghana Spotlight", "outlets": ["Punch"], "note": "Hello", "kind": "campaign", "campaign": "black_friday"})
    assert r.status_code == 200 and r.json()["name"] == "Ghana Spotlight" and r.json()["held"] == ["Punch"] and r.json()["campaign"] == "black_friday"
    pid = p["id"]
    async with maker() as db:
        assert (await db.get(DistributionPackage, pid)).outlet_ids == ["30"]
    for bad in ({"local_prices": {"naira": "1"}}, {"local_prices": {"NGN": "lots"}}, {"local_prices": {"NGN": "-5"}}):
        assert (await client.patch(f"/v1/admin/distribution-packages/{pid}", headers=OPS, json=bad)).status_code == 422
    assert (await client.post("/v1/admin/distribution-packages", headers=OPS, json={"usd_price": "5"})).status_code == 422  # no name
    assert (await client.post("/v1/admin/distribution-packages", headers=OWNER, json={"name": "Nope"})).status_code in (401, 403)
