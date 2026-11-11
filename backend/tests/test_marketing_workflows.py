# ruff: noqa: F811
"""Marketing workflows: enrolment, waits, "only if", goals, sending hours, and the controls around switching on."""

from datetime import UTC, datetime, timedelta
from zoneinfo import ZoneInfo

import pytest
from sqlalchemy import select

from app.config import get_settings
from app.integrations import registry
from app.models import Checkout, MarketingEnrollment, MarketingPref, Project, User
from app.services import marketing_workflows as wfs
from tests.conftest import OPS, OWNER
from tests.test_marketing_segments import _person

NG = {"match": "all", "conditions": [{"field": "country", "op": "in", "value": ["Nigeria"]}]}
NO_VIDEO = {"match": "all", "conditions": [{"field": "videos_started", "op": "eq", "value": 0}]}
BOUGHT = {"match": "all", "conditions": [{"field": "has_bought_credits", "op": "is", "value": True}]}
OPEN = {"enabled": False, "start": 9, "end": 18}  # sending hours off, for tests that aren't about them
CLOCK = {"now": datetime.now(UTC)}


def copy(subject, body="Hello {{company}}"):
    return {
        "name": subject,
        "category": "activation",
        "subject": subject,
        "preheader": "",
        "body": body,
        "button_label": "",
        "button_url": "",
    }


@pytest.fixture(autouse=True)
def clock(monkeypatch):
    CLOCK["now"] = datetime.now(UTC)
    monkeypatch.setattr(wfs, "utcnow", lambda: CLOCK["now"])


@pytest.fixture
def on(monkeypatch):
    monkeypatch.setattr(get_settings(), "marketing_email", "on")


async def _seg(client, name, rules):
    return (await client.post("/v1/admin/marketing/segments", json={"name": name, "rules": rules}, headers=OPS)).json()[
        "id"
    ]


async def _copy(client, subject):
    return (await client.post("/v1/admin/marketing/copies", json=copy(subject), headers=OPS)).json()["id"]


async def _no_gap(client):
    await client.put(
        "/v1/admin/marketing/config", json={"min_gap_days": 0, "daily_cap": 500, "per_minute": 20}, headers=OPS
    )


async def _workflow(client, steps, *, goal=None, hours=OPEN, trigger=None):
    r = await client.post(
        "/v1/admin/marketing/workflows",
        json={"name": "Flow", "trigger_segment_id": trigger, "steps": steps, "goal_segment_id": goal, "hours": hours},
        headers=OPS,
    )
    assert r.status_code == 201, r.text
    return r.json()["id"]


async def _on(client, wid, n, existing=True):
    r = await client.post(
        f"/v1/admin/marketing/workflows/{wid}/activate",
        json={"include_existing": existing, "confirm_count": n},
        headers=OPS,
    )
    assert r.status_code == 200, r.text
    return r.json()


def _mail(to=None):
    return [m for m in registry.get_email().sent if m["to"].endswith("@x.test") and (to is None or m["to"] == to)]


async def _enrol(maker, email):
    async with maker() as s:
        u = (await s.execute(select(User).where(User.email == email))).scalar_one()
        return (await s.execute(select(MarketingEnrollment).where(MarketingEnrollment.user_id == u.id))).scalar_one()


async def _flow_basics(client, maker):
    for e in ("a@x.test", "b@x.test"):
        await _person(maker, e, joined=2, country="Nigeria")
    await _no_gap(client)
    return await _seg(client, "NG", NG), await _seg(client, "No video", NO_VIDEO), await _seg(client, "Bought", BOUGHT)


async def test_a_sequence_runs_waits_skips_and_finishes(client, maker, workspace, on):
    trigger, no_video, _ = await _flow_basics(client, maker)
    a, b = await _copy(client, "First"), await _copy(client, "Second")
    wid = await _workflow(
        client,
        [
            {"type": "email", "copy_id": a},
            {"type": "wait", "days": 1},
            {"type": "email", "copy_id": b, "only_if_segment_id": no_video},
        ],
        trigger=trigger,
    )
    await _on(client, wid, 2)
    assert (await wfs.tick(10)) == {"enrolled": 2, "sent": 2}
    assert sorted(m["subject"] for m in _mail()) == ["First", "First"]
    assert (await wfs.tick(10))["sent"] == 0  # the wait: nothing yet
    async with maker() as s:  # b makes a video during the wait
        u = (await s.execute(select(User).where(User.email == "b@x.test"))).scalar_one()
        s.add(Project(workspace_id=u.workspace_id))
        await s.commit()
    CLOCK["now"] += timedelta(days=1, hours=1)
    assert (await wfs.tick(10))["sent"] == 1
    assert [m["to"] for m in _mail() if m["subject"] == "Second"] == ["a@x.test"]  # only the one with no video
    await wfs.tick(10)
    assert {(await _enrol(maker, e)).status for e in ("a@x.test", "b@x.test")} == {"completed"}
    await wfs.tick(10)
    assert len(_mail()) == 3  # nothing is ever sent twice
    stats = (await client.get(f"/v1/admin/marketing/workflows/{wid}", headers=OPS)).json()["stats"]
    assert stats["completed"] == 2 and stats["sent_by_step"] == {"0": 2, "2": 1}


async def test_only_people_who_arrive_after_switching_on_are_mailed_by_default(client, maker, workspace, on):
    trigger, *_ = await _flow_basics(client, maker)
    wid = await _workflow(client, [{"type": "email", "copy_id": await _copy(client, "Hi")}], trigger=trigger)
    await _on(client, wid, 2, existing=False)
    await wfs.tick(10)
    assert _mail() == [] and (await _enrol(maker, "a@x.test")).exit_reason == "existing_at_start"
    await _person(maker, "late@x.test", joined=0, country="Nigeria")
    await wfs.tick(10)
    assert [m["to"] for m in _mail()] == ["late@x.test"]


async def test_the_goal_ends_it_for_anyone_who_reaches_it(client, maker, workspace, on):
    trigger, _, bought = await _flow_basics(client, maker)
    one, two = await _copy(client, "One"), await _copy(client, "Two")
    wid = await _workflow(
        client,
        [{"type": "email", "copy_id": one}, {"type": "wait", "days": 1}, {"type": "email", "copy_id": two}],
        goal=bought,
        trigger=trigger,
    )
    await _on(client, wid, 2)
    await wfs.tick(10)
    async with maker() as s:
        u = (await s.execute(select(User).where(User.email == "a@x.test"))).scalar_one()
        s.add(Checkout(workspace_id=u.workspace_id, credits=5, amount_usd=5, provider="x", status="paid"))
        await s.commit()
    CLOCK["now"] += timedelta(days=2)
    await wfs.tick(10)
    assert [m["to"] for m in _mail() if m["subject"] == "Two"] == ["b@x.test"]
    e = await _enrol(maker, "a@x.test")
    assert (e.status, e.exit_reason) == ("exited", "goal_reached")


async def test_someone_who_unsubscribes_midway_leaves(client, maker, workspace, on):
    trigger, *_ = await _flow_basics(client, maker)
    wid = await _workflow(
        client,
        [
            {"type": "email", "copy_id": await _copy(client, "One")},
            {"type": "wait", "days": 1},
            {"type": "email", "copy_id": await _copy(client, "Two")},
        ],
        trigger=trigger,
    )
    await _on(client, wid, 2)
    await wfs.tick(10)
    async with maker() as s:
        u = (await s.execute(select(User).where(User.email == "a@x.test"))).scalar_one()
        (await s.get(MarketingPref, u.id)).opted_out_at = datetime.now(UTC)  # made when the first email went out
        await s.commit()
    CLOCK["now"] += timedelta(days=2)
    await wfs.tick(10)
    assert [m["to"] for m in _mail() if m["subject"] == "Two"] == ["b@x.test"]
    assert (await _enrol(maker, "a@x.test")).exit_reason == "opted_out"


async def test_emails_wait_for_the_sending_hours_where_the_person_lives(client, maker, workspace, on):
    await _person(maker, "a@x.test", joined=2, country="Nigeria")
    await _no_gap(client)
    trigger = await _seg(client, "NG", NG)
    wid = await _workflow(
        client,
        [{"type": "email", "copy_id": await _copy(client, "Morning")}],
        hours={"enabled": True, "start": 9, "end": 18},
        trigger=trigger,
    )
    await _on(client, wid, 1)
    lagos = ZoneInfo("Africa/Lagos")
    CLOCK["now"] = datetime(2030, 3, 4, 2, 0, tzinfo=lagos).astimezone(UTC)  # 02:00 in Lagos
    await wfs.tick(10)
    assert _mail() == []
    assert (await _enrol(maker, "a@x.test")).next_run_at.replace(tzinfo=UTC) == datetime(
        2030, 3, 4, 9, 0, tzinfo=lagos
    ).astimezone(UTC)
    CLOCK["now"] = datetime(2030, 3, 4, 9, 30, tzinfo=lagos).astimezone(UTC)
    await wfs.tick(10)
    assert len(_mail()) == 1


def test_sending_hours_maths():
    tz = ZoneInfo("Africa/Lagos")
    at = lambda h, d=4: datetime(2030, 3, d, h, 0, tzinfo=tz).astimezone(UTC)  # noqa: E731
    assert wfs.next_open(at(10), tz, 9, 18) is None
    assert wfs.next_open(at(3), tz, 9, 18) == at(9)
    assert wfs.next_open(at(20), tz, 9, 18) == at(9, 5)
    assert (
        wfs.tz_for("Nigeria").key == "Africa/Lagos"
        and wfs.tz_for("Atlantis").key == get_settings().marketing_default_timezone
    )


async def test_a_tick_sends_no_more_than_its_budget(client, maker, workspace, on):
    trigger, *_ = await _flow_basics(client, maker)
    wid = await _workflow(client, [{"type": "email", "copy_id": await _copy(client, "Hi")}], trigger=trigger)
    await _on(client, wid, 2)
    assert (await wfs.tick(1))["sent"] == 1
    assert (await wfs.tick(1))["sent"] == 1
    assert (await wfs.tick(1))["sent"] == 0 and len(_mail()) == 2


async def test_an_email_held_back_by_the_gap_is_retried_then_given_up(client, maker, workspace, on):
    trigger, *_ = await _flow_basics(client, maker)
    await client.put(
        "/v1/admin/marketing/config", json={"min_gap_days": 2, "daily_cap": 500, "per_minute": 20}, headers=OPS
    )
    wid = await _workflow(
        client,
        [
            {"type": "email", "copy_id": await _copy(client, "One")},
            {"type": "email", "copy_id": await _copy(client, "Two")},
        ],
        trigger=trigger,
    )
    await _on(client, wid, 2)
    await wfs.tick(10)
    assert len(_mail()) == 2  # step one went; step two is held back by the gap
    for _ in range(3):
        CLOCK["now"] += timedelta(hours=13)
        await wfs.tick(10)
    assert [m["subject"] for m in _mail()] == ["One", "One"]
    assert {(await _enrol(maker, e)).status for e in ("a@x.test", "b@x.test")} == {
        "completed"
    }  # gave up on Two, finished


async def test_pause_freezes_and_stop_empties_it(client, maker, workspace, on):
    trigger, *_ = await _flow_basics(client, maker)
    wid = await _workflow(client, [{"type": "email", "copy_id": await _copy(client, "Hi")}], trigger=trigger)
    await _on(client, wid, 2)
    assert (await client.post(f"/v1/admin/marketing/workflows/{wid}/pause", headers=OPS)).json()["status"] == "paused"
    await wfs.tick(10)
    assert _mail() == []
    assert (await client.post(f"/v1/admin/marketing/workflows/{wid}/resume", headers=OPS)).json()["status"] == "active"
    await wfs.tick(10)
    assert len(_mail()) == 2
    assert (await client.post(f"/v1/admin/marketing/workflows/{wid}/stop", headers=OPS)).json()["status"] == "stopped"
    assert (await client.post(f"/v1/admin/marketing/workflows/{wid}/resume", headers=OPS)).status_code == 409


async def test_the_words_are_fixed_when_it_is_switched_on(client, maker, workspace, on):
    trigger, *_ = await _flow_basics(client, maker)
    cid = await _copy(client, "Original")
    wid = await _workflow(client, [{"type": "email", "copy_id": cid}], trigger=trigger)
    await _on(client, wid, 2)
    await client.put(f"/v1/admin/marketing/copies/{cid}", json=copy("Changed"), headers=OPS)
    await wfs.tick(10)
    assert {m["subject"] for m in _mail()} == {"Original"}


@pytest.mark.parametrize(
    "steps,message",
    [
        ([{"type": "wait", "days": 1}], "at least one email"),
        ([{"type": "email", "copy_id": "x"}, {"type": "wait", "days": 1}], "last step should be an email"),
        ([{"type": "email", "copy_id": "nope"}], "choose an email"),
    ],
)
async def test_bad_workflows_are_refused_in_plain_words(client, maker, workspace, steps, message):
    trigger = await _seg(client, "NG", NG)
    r = await client.post(
        "/v1/admin/marketing/workflows", json={"name": "x", "trigger_segment_id": trigger, "steps": steps}, headers=OPS
    )
    assert r.status_code == 422 and message in r.text.lower()


async def test_switching_on_is_checked(client, maker, workspace, monkeypatch):
    trigger, *_ = await _flow_basics(client, maker)
    wid = await _workflow(client, [{"type": "email", "copy_id": await _copy(client, "Hi")}], trigger=trigger)
    body = {"include_existing": True, "confirm_count": 2}
    r = await client.post(f"/v1/admin/marketing/workflows/{wid}/activate", json=body, headers=OPS)
    assert r.status_code == 409 and "switched off" in r.json()["detail"]
    monkeypatch.setattr(get_settings(), "marketing_email", "on")
    assert (
        await client.post(
            f"/v1/admin/marketing/workflows/{wid}/activate", json={**body, "confirm_count": 9}, headers=OPS
        )
    ).status_code == 409
    assert (
        await client.post(f"/v1/admin/marketing/workflows/{wid}/activate", json=body, headers=OPS)
    ).status_code == 200
    assert (
        await client.post(f"/v1/admin/marketing/workflows/{wid}/activate", json=body, headers=OPS)
    ).status_code == 409
    put = await client.put(
        f"/v1/admin/marketing/workflows/{wid}",
        json={"name": "x", "trigger_segment_id": trigger, "steps": [{"type": "email", "copy_id": "z"}]},
        headers=OPS,
    )
    assert (
        put.status_code == 409
        and (await client.delete(f"/v1/admin/marketing/workflows/{wid}", headers=OPS)).status_code == 409
    )


async def test_the_welcome_sequence_is_made_ready_to_open_and_reuses_what_exists(client, maker, workspace, on):
    r = await client.post("/v1/admin/marketing/workflows/starter", headers=OPS)
    assert r.status_code == 201
    w = r.json()
    assert w["status"] == "draft" and [s["type"] for s in w["steps"]] == ["email", "wait", "email", "wait", "email"]
    assert w["trigger_segment_name"] == "Joined in the last day" and w["goal_segment_name"] == "Has bought credits"
    await client.post("/v1/admin/marketing/workflows/starter", headers=OPS)
    assert len((await client.get("/v1/admin/marketing/segments", headers=OPS)).json()["items"]) == 4
    assert len((await client.get("/v1/admin/marketing/copies", headers=OPS)).json()["items"]) == 3
    # a person who just joined goes through it: welcome now (hours off for the test), nothing else until the waits pass
    await _no_gap(client)
    async with maker() as s:
        from app.models import MarketingWorkflow

        row = await s.get(MarketingWorkflow, w["id"])
        row.settings = OPEN
        await s.commit()
    await _person(maker, "new@x.test", joined=0)
    seen = (await client.get(f"/v1/admin/marketing/workflows/{w['id']}", headers=OPS)).json()["preview"]["reachable"]
    await _on(client, w["id"], seen, existing=False)
    await _person(maker, "newer@x.test", joined=0)
    await wfs.tick(10)
    assert [m["subject"] for m in _mail()] == ["Welcome to Cover Founder, there"]


async def test_permissions(client, workspace):
    assert (await client.get("/v1/admin/marketing/workflows", headers=OWNER)).status_code in (401, 403)
    assert (await client.post("/v1/admin/marketing/workflows/starter", headers=OWNER)).status_code in (401, 403)
