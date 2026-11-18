"""The outlet planner: plans that fit the budget, are explainable, repeat the same way, and never suggest what they should not."""

from decimal import Decimal

from app.services import distribution_planner as planner
from app.services.distribution_planner import Ask, recommend

KNOWN = {"Nigeria": "Africa", "Kenya": "Africa", "Ghana": "Africa", "United States": "North America", "Canada": "North America"}


def _o(i, name, country, topic, credits, category="Media outlets"):
    return {
        "id": str(i),
        "name": name,
        "country": country,
        "region": KNOWN.get(country, "Africa") if country else "Africa",
        "topic": topic,
        "credits": str(credits),
        "category": category,
    }


OUTLETS = [
    _o(1, "Lagos Daily", "Nigeria", "General News", 40),
    _o(2, "Naija Business", "Nigeria", "General News", 60),
    _o(3, "Lagos Tech", "Nigeria", "Technology", 50),
    _o(4, "Abuja Tech", "Nigeria", "Technology", 70),
    _o(5, "Naija Post", "Nigeria", "General News", 100),
    _o(6, "Naija Gossip", "Nigeria", "Gossip Blogs", 20),
    _o(7, "Coin Daily", None, "Technology", 42, "Crypto News Channels"),
    _o(8, "Nation", "Kenya", "General News", 650),
    _o(9, "NY Wire", "United States", "General News", 4000),
    _o(10, "Free Outlet", "Nigeria", "General News", 0),
]


def run(budget=None, countries=("Nigeria",), goal="credibility", industry=None, balance=None):
    ask = Ask(None if budget is None else Decimal(str(budget)), list(countries), goal, industry)
    return recommend(OUTLETS, ask, balance=balance, known_countries=KNOWN)


def ids(plan):
    return [o["id"] for o in plan["outlets"]]


def test_gossip_crypto_and_free_outlets_are_never_suggested():
    r = run()
    suggested = set(r["suggested"])
    assert not suggested & {"6", "7", "10"}


def test_every_plan_stays_inside_the_budget_and_says_why():
    r = run(budget=150)
    assert r["plans"]
    for p in r["plans"]:
        assert Decimal(p["total_credits"]) <= 150
        assert all(o["reasons"] for o in p["outlets"])
    assert any("Based in Nigeria" in x for o in r["plans"][0]["outlets"] for x in o["reasons"])


def test_each_plan_builds_on_the_one_before_it():
    r = run(budget=1000)
    keys = [p["key"] for p in r["plans"]]
    assert keys[0] == "essential" and keys == sorted(keys, key=["essential", "balanced", "max"].index)
    for smaller, bigger in zip(r["plans"], r["plans"][1:], strict=False):
        assert set(ids(smaller)) < set(ids(bigger))
        assert Decimal(smaller["total_credits"]) < Decimal(bigger["total_credits"])


def test_every_country_asked_for_is_covered_in_every_plan_when_the_budget_allows():
    r = run(budget=5000, countries=("Nigeria", "United States"))
    assert r["plans"]
    for p in r["plans"]:
        assert {"Nigeria", "United States"} <= set(p["countries"])


def test_the_same_inputs_always_give_the_same_plans():
    assert run(budget=300) == run(budget=300)


def test_the_goal_changes_what_comes_first():
    tech = run(goal="investors", industry="technology")["plans"][0]
    news = run(goal="credibility")["plans"][0]
    assert {o["topic"] for o in tech["outlets"]} == {"Technology"} or tech["outlets"][0]["topic"] == "Technology"
    assert news["outlets"][0]["topic"] == "General News"


def test_only_the_countries_asked_for_or_their_region_are_used():
    r = run(countries=("Nigeria",))
    assert all(o["region"] == "Africa" for p in r["plans"] for o in p["outlets"])
    assert "9" not in r["suggested"]


def test_a_country_with_one_outlet_is_told_plainly_and_gets_regional_help():
    r = run(countries=("Kenya",))
    assert any("just one outlet in Kenya" in n for n in r["notes"])
    first = r["plans"][-1]["outlets"]
    assert "8" in {o["id"] for o in first}  # the one Kenyan outlet is in even the first plan if it is affordable
    assert any("closest we have to Kenya" in x for o in first for x in o["reasons"])


def test_a_country_with_no_outlets_says_so_and_falls_back_to_the_region():
    r = run(countries=("Ghana",))
    assert any("don't have outlets in Ghana" in n for n in r["notes"])
    assert r["plans"]


def test_a_budget_below_the_cheapest_outlet_explains_instead_of_showing_nothing():
    r = run(budget=10)
    assert r["plans"] == [] and "cheapest outlet starts at 40" in r["empty"]


def test_a_country_we_do_not_list_is_ignored_and_no_country_means_anywhere():
    assert run(countries=("Atlantis",))["countries"] == []
    anywhere = run(countries=())
    assert anywhere["plans"] and anywhere["countries"] == []


def test_the_shortfall_against_the_wallet_is_reported():
    r = run(budget=200, balance=Decimal("50"))
    assert r["balance_credits"] == "50"
    for p in r["plans"]:
        assert Decimal(p["shortfall_credits"]) == max(Decimal(0), Decimal(p["total_credits"]) - 50)


def test_budget_presets_follow_the_market():
    ng = run(countries=("Nigeria",))["budget_presets"]
    us = run(countries=("United States",))["budget_presets"]
    assert max(map(Decimal, ng)) < 500 and max(map(Decimal, us)) >= 4000
    assert ng == sorted(ng, key=Decimal)


def test_identical_plans_are_shown_once():
    r = recommend(OUTLETS[:1], Ask(None, ["Nigeria"]), known_countries=KNOWN)
    assert len(r["plans"]) == 1


def test_constants():
    assert set(planner.GOALS) == {"credibility", "investors", "customers", "hiring"}


# ---------- the API ----------
from sqlalchemy import update  # noqa: E402

from app.models import Workspace  # noqa: E402
from tests.conftest import OWNER  # noqa: E402


async def test_a_visitor_gets_plans_without_signing_in_and_nothing_is_cached(client):
    r = await client.post(
        "/v1/public/distribution/plan", json={"budget": "300", "countries": ["nigeria"], "goal": "investors"}
    )
    assert r.status_code == 200, r.text
    body = r.json()
    assert r.headers["cache-control"] == "no-store"
    assert body["plans"] and body["countries"] == ["Nigeria"]
    assert "balance_credits" not in body  # a visitor has no wallet
    for p in body["plans"]:
        assert Decimal(p["total_credits"]) <= 300
        assert {o["country"] for o in p["outlets"]} <= {"Nigeria"}
    for key in ("contact_email", "accepts_logo", "logo_credits"):  # nothing internal
        assert key not in r.text


async def test_the_planner_refuses_nonsense_instead_of_guessing(client):
    assert (await client.post("/v1/public/distribution/plan", json={"goal": "world domination"})).status_code == 422
    assert (await client.post("/v1/public/distribution/plan", json={"budget": "-5"})).status_code == 422
    assert (await client.post("/v1/public/distribution/plan", json={"countries": ["x"] * 11})).status_code == 422


async def test_a_signed_in_customer_starts_from_their_country_and_sees_their_balance(client, maker, workspace):
    async with maker() as db:
        await db.execute(update(Workspace).where(Workspace.id == workspace).values(country="Nigeria", credit_balance=Decimal("40")))
        await db.commit()
    r = await client.post("/v1/distribution/plan", json={"budget": "500"}, headers=OWNER)
    assert r.status_code == 200, r.text
    body = r.json()
    assert body["countries"] == ["Nigeria"] and body["balance_credits"] == "40"
    assert all("shortfall_credits" in p for p in body["plans"])
    assert any(Decimal(p["shortfall_credits"]) > 0 for p in body["plans"])
    assert (await client.post("/v1/distribution/plan", json={})).status_code in {401, 403}
