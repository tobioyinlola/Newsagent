"""Marketing segments: who the rules pick, and that bad rules are refused in plain words."""

from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest

from app.models import Checkout, MarketingPref, Project, User, Workspace
from app.services import marketing
from tests.conftest import OPS, OWNER

NOW = datetime.now(UTC)


async def _person(maker, email, *, joined=0, seen=None, videos=0, finished=0, bought=False, balance=0, **ws):
    async with maker() as s:
        w = Workspace(name=email.split("@")[0], credit_balance=Decimal(balance), **ws)
        s.add(w)
        await s.flush()
        u = User(email=email, workspace_id=w.id, created_at=NOW - timedelta(days=joined, hours=1))
        if seen is not None:
            u.last_login_at = NOW - timedelta(days=seen, hours=1)
        s.add(u)
        for i in range(videos):
            s.add(Project(workspace_id=w.id, completed_at=NOW if i < finished else None))
        if bought:
            s.add(Checkout(workspace_id=w.id, credits=Decimal(5), amount_usd=Decimal(5), provider="x", status="paid"))
        await s.commit()
        return u.id


async def _count(client, *conditions, match="all") -> dict:
    r = await client.post(
        "/v1/admin/marketing/segments/preview",
        json={"rules": {"match": match, "conditions": list(conditions)}},
        headers=OPS,
    )
    assert r.status_code == 200, r.text
    return r.json()


def _emails(p):
    return sorted(x["email"] for x in p["sample"] if x["email"].endswith("@x.test"))  # not the seeded accounts


@pytest.fixture
async def people(maker, workspace):
    await _person(maker, "new@x.test", joined=0)
    await _person(maker, "day3@x.test", joined=3, videos=0)
    await _person(maker, "day5@x.test", joined=5, videos=2, finished=1)
    await _person(maker, "day40@x.test", joined=40, seen=35, videos=3, finished=3, bought=True, balance=0)
    await _person(maker, "ng@x.test", joined=10, country="Nigeria", industry="technology", balance=7)


async def test_joined_between_days_is_inclusive_on_both_ends(client, people):
    p = await _count(client, {"field": "joined_days_ago", "op": "between", "value": [3, 7]})
    assert _emails(p) == ["day3@x.test", "day5@x.test"]
    assert _emails(await _count(client, {"field": "joined_days_ago", "op": "eq", "value": 0})) == ["new@x.test"]


async def test_joined_at_least_and_at_most(client, people):
    assert (await _count(client, {"field": "joined_days_ago", "op": "gte", "value": 30}))["matched"] == 1
    assert (await _count(client, {"field": "joined_days_ago", "op": "lte", "value": 4}))[
        "matched"
    ] >= 2  # includes the seeded staff


async def test_the_few_actions_case_joined_recently_and_made_no_video(client, people):
    p = await _count(
        client,
        {"field": "joined_days_ago", "op": "between", "value": [1, 7]},
        {"field": "videos_started", "op": "eq", "value": 0},
    )
    assert _emails(p) == ["day3@x.test"]


async def test_any_versus_all(client, people):
    a = {"field": "videos_finished", "op": "gte", "value": 3}
    b = {"field": "credits_left", "op": "gte", "value": 5}
    assert (await _count(client, a, b))["matched"] == 0
    assert _emails(await _count(client, a, b, match="any")) == ["day40@x.test", "ng@x.test"]


async def test_money_and_profile_rules(client, people):
    assert _emails(await _count(client, {"field": "has_bought_credits", "op": "is", "value": True})) == ["day40@x.test"]
    assert _emails(await _count(client, {"field": "country", "op": "in", "value": ["nigeria"]})) == ["ng@x.test"]
    assert _emails(await _count(client, {"field": "industry", "op": "in", "value": ["technology"]})) == ["ng@x.test"]


async def test_inactive_counts_from_the_day_they_joined_if_they_never_came_back(client, people):
    p = await _count(client, {"field": "last_seen_days_ago", "op": "gte", "value": 30})
    assert _emails(p) == [
        "day40@x.test"
    ]  # day40 last seen 35 days ago; nobody else is that old without a sign-in... except never-seen: none


async def test_joined_between_dates(client, people):
    d = lambda n: (NOW - timedelta(days=n)).date().isoformat()  # noqa: E731
    p = await _count(client, {"field": "joined_dates", "op": "between", "value": [d(6), d(2)]})
    assert _emails(p) == ["day3@x.test", "day5@x.test"]


async def test_people_who_cannot_be_emailed_are_matched_but_not_reachable(client, maker, people):
    async with maker() as s:
        from sqlalchemy import select

        u = (await s.execute(select(User).where(User.email == "day3@x.test"))).scalar_one()
        s.add(MarketingPref(user_id=u.id, token="t" * 20, opted_out_at=datetime.now(UTC)))
        await marketing.suppress(s, "day5@x.test", "bounce")
        await s.commit()
    p = await _count(client, {"field": "joined_days_ago", "op": "between", "value": [3, 7]})
    assert (p["matched"], p["reachable"], p["excluded"]) == (2, 0, 2)
    assert p["sample"] == []


@pytest.mark.parametrize(
    "cond,message",
    [
        ({"field": "nope", "op": "eq", "value": 1}, "Unknown rule"),
        ({"field": "joined_days_ago", "op": "like", "value": 1}, "comparison"),
        ({"field": "joined_days_ago", "op": "gte", "value": "abc"}, "enter a number"),
        ({"field": "joined_days_ago", "op": "gte", "value": -2}, "zero or more"),
        ({"field": "joined_days_ago", "op": "between", "value": [9, 2]}, "bigger"),
        ({"field": "has_bought_credits", "op": "is", "value": "yes"}, "yes or no"),
        ({"field": "industry", "op": "in", "value": ["made-up"]}, "isn't an option"),
        ({"field": "joined_dates", "op": "between", "value": ["2026-02-01", "2026-01-01"]}, "start"),
    ],
)
async def test_bad_rules_are_refused_in_plain_words(client, workspace, cond, message):
    r = await client.post("/v1/admin/marketing/segments/preview", json={"rules": {"conditions": [cond]}}, headers=OPS)
    assert r.status_code == 422 and message in r.json()["detail"]


async def test_empty_rules_are_refused(client, workspace):
    r = await client.post("/v1/admin/marketing/segments/preview", json={"rules": {"conditions": []}}, headers=OPS)
    assert r.status_code == 422


async def test_save_edit_archive_and_permissions(client, people):
    rules = {"match": "all", "conditions": [{"field": "videos_started", "op": "eq", "value": 0}]}
    r = await client.post("/v1/admin/marketing/segments", json={"name": "No video yet", "rules": rules}, headers=OPS)
    assert r.status_code == 201
    sid = r.json()["id"]
    got = (await client.get(f"/v1/admin/marketing/segments/{sid}", headers=OPS)).json()
    assert got["preview"]["matched"] >= 3
    rules["conditions"][0]["value"] = 1
    assert (
        await client.put(f"/v1/admin/marketing/segments/{sid}", json={"name": "One video", "rules": rules}, headers=OPS)
    ).status_code == 200
    assert [s["name"] for s in (await client.get("/v1/admin/marketing/segments", headers=OPS)).json()["items"]] == [
        "One video"
    ]
    assert (
        await client.post("/v1/admin/marketing/segments", json={"name": "x", "rules": rules}, headers=OWNER)
    ).status_code in (401, 403)
    assert (await client.delete(f"/v1/admin/marketing/segments/{sid}", headers=OPS)).status_code == 204
    assert (await client.get(f"/v1/admin/marketing/segments/{sid}", headers=OPS)).status_code == 404
    assert (await client.get("/v1/admin/marketing/segment-fields", headers=OPS)).json()["fields"][0][
        "key"
    ] == "joined_days_ago"
