# ruff: noqa: F811, F401
"""Marketing, the rest of the plan: nested segment groups, brand/event rules, workflow branches and re-entry, AI drafts, activity."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.config import get_settings
from app.integrations import registry
from app.models import MarketingPref, Project, User, Workspace
from app.services import marketing_campaigns as mcamp
from app.services import marketing_workflows as wfs
from app.services import user_events
from tests.conftest import OPS, OWNER
from tests.test_marketing_segments import _count, _emails, _person
from tests.test_marketing_workflows import (
    CLOCK,
    NG,
    NO_VIDEO,
    OPEN,
    _copy,
    _enrol,
    _flow_basics,
    _mail,
    _no_gap,
    _on,
    _seg,
    _workflow,
    clock,
    on,
)

HAS_VIDEO = {"match": "all", "conditions": [{"field": "videos_started", "op": "gte", "value": 1}]}


def rule(field, op, value):
    return {"field": field, "op": op, "value": value}


# ---------- segments ----------
@pytest.fixture
async def folks(maker, workspace):
    await _person(maker, "new@x.test", joined=0)
    await _person(maker, "old-video@x.test", joined=40, videos=2, finished=1)
    await _person(maker, "old-bought@x.test", joined=40, bought=True)
    await _person(maker, "mid@x.test", joined=10, videos=1)


async def test_groups_nest_so_a_and_b_or_c_works(client, folks):
    joined_recently = rule("joined_days_ago", "lte", 12)
    inner = {"match": "any", "conditions": [rule("videos_started", "gte", 1), rule("has_bought_credits", "is", True)]}
    p = await _count(client, joined_recently, inner)  # (joined within 12 days) AND (has a video OR has bought)
    assert _emails(p) == ["mid@x.test"]
    p = await _count(client, inner, match="all")  # a group on its own
    assert _emails(p) == ["mid@x.test", "old-bought@x.test", "old-video@x.test"]
    outer_any = await _count(client, rule("joined_days_ago", "eq", 0), inner, match="any")
    assert _emails(outer_any) == ["mid@x.test", "new@x.test", "old-bought@x.test", "old-video@x.test"]


async def test_groups_can_be_saved_and_read_back(client, folks):
    rules = {
        "match": "all",
        "conditions": [
            rule("joined_days_ago", "gte", 30),
            {"match": "any", "conditions": [rule("videos_started", "gte", 1), rule("has_bought_credits", "is", True)]},
        ],
    }
    r = await client.post("/v1/admin/marketing/segments", json={"name": "Old and active", "rules": rules}, headers=OPS)
    assert r.status_code == 201
    got = (await client.get(f"/v1/admin/marketing/segments/{r.json()['id']}", headers=OPS)).json()
    assert got["rules"] == rules and got["preview"]["matched"] == 2


@pytest.mark.parametrize(
    "rules,message",
    [
        (
            {"match": "all", "conditions": [rule("videos_started", "gte", 1), {"match": "any", "conditions": []}]},
            "empty",
        ),
        (
            {
                "match": "all",
                "conditions": [
                    {
                        "match": "any",
                        "conditions": [
                            {
                                "match": "any",
                                "conditions": [
                                    {
                                        "match": "any",
                                        "conditions": [
                                            {"match": "any", "conditions": [rule("videos_started", "gte", 1)]}
                                        ],
                                    }
                                ],
                            }
                        ],
                    }
                ],
            },
            "nested",
        ),
        ({"match": "all", "conditions": [{"field": "videos_started"}, {"bogus": 1}]}, "right shape"),
        ({"match": "all", "conditions": [{"match": "any", "conditions": [rule("nope", "eq", 1)]}]}, "Unknown rule"),
    ],
)
async def test_bad_groups_are_refused(client, workspace, rules, message):
    r = await client.post("/v1/admin/marketing/segments/preview", json={"rules": rules}, headers=OPS)
    assert r.status_code == 422 and message in r.json()["detail"]


async def test_brand_kit_and_remembered_actions_are_rules(client, maker, workspace):
    await _person(maker, "branded@x.test", joined=5)
    await _person(maker, "plain@x.test", joined=5)
    async with maker() as s:
        ws = (await s.execute(select(Workspace).where(Workspace.name == "branded"))).scalar_one()
        ws.brand_kit_id = "kit"
        u = (await s.execute(select(User).where(User.email == "branded@x.test"))).scalar_one()
        user_events.record(s, u.id, "video_shared")
        user_events.record(s, u.id, "not_an_event")  # ignored
        await s.commit()
    assert _emails(await _count(client, rule("has_brand_kit", "is", True))) == ["branded@x.test"]
    assert _emails(await _count(client, rule("did_video_shared", "is", True))) == ["branded@x.test"]
    assert _emails(await _count(client, rule("did_video_shared", "is", False), rule("joined_days_ago", "eq", 5))) == [
        "plain@x.test"
    ]
    assert _emails(await _count(client, rule("since_video_shared", "lte", 1))) == ["branded@x.test"]
    assert await _count(client, rule("since_video_shared", "gte", 3)) == {
        "matched": 0,
        "reachable": 0,
        "excluded": 0,
        "sample": [],
    }  # only people who did it
    names = {f["key"] for f in (await client.get("/v1/admin/marketing/segment-fields", headers=OPS)).json()["fields"]}
    assert {"has_brand_kit", "did_brand_saved", "since_brand_saved", "did_video_shared"} <= names


async def test_saving_a_brand_kit_and_sharing_a_video_are_remembered(client, maker, workspace):
    kit = {"primary_color": "#0B3D91", "accent_color": "#F5A623", "tone": "confident"}
    assert (await client.put("/v1/brand-kit", json=kit, headers=OWNER)).status_code == 200
    p = await _count(client, rule("did_brand_saved", "is", True))
    assert [x["email"] for x in p["sample"]] == ["owner@acme.test"]


# ---------- workflows: branches and end ----------
async def _branching(client, maker, trigger, has_video):
    a, nudge, done = await _copy(client, "One"), await _copy(client, "Nudge"), await _copy(client, "Congrats")
    steps = [
        {"type": "email", "copy_id": a},
        {"type": "branch", "segment_id": has_video, "yes_to": 4, "no_to": 2},
        {"type": "email", "copy_id": nudge},
        {"type": "end"},
        {"type": "email", "copy_id": done},
    ]
    return await _workflow(client, steps, trigger=trigger)


async def test_a_branch_sends_people_down_different_paths(client, maker, workspace, on):
    trigger, *_ = await _flow_basics(client, maker)
    async with maker() as s:
        u = (await s.execute(select(User).where(User.email == "b@x.test"))).scalar_one()
        s.add(Project(workspace_id=u.workspace_id))
        await s.commit()
    wid = await _branching(client, maker, trigger, await _seg(client, "Has video", HAS_VIDEO))
    await _on(client, wid, 2)
    for _ in range(6):
        await wfs.tick(10)
    sent = {m["to"]: [x["subject"] for x in _mail(m["to"])] for m in _mail()}
    assert sent == {"a@x.test": ["One", "Nudge"], "b@x.test": ["One", "Congrats"]}
    assert {(await _enrol(maker, e)).status for e in sent} == {"completed"}
    st = (await client.get(f"/v1/admin/marketing/workflows/{wid}", headers=OPS)).json()["stats"]
    assert st["sent_by_step"] == {"0": 2, "2": 1, "4": 1}


@pytest.mark.parametrize(
    "steps_fn,message",
    [
        (
            lambda c, s: [
                {"type": "email", "copy_id": c},
                {"type": "branch", "segment_id": s, "yes_to": 0},
                {"type": "end"},
            ],
            "later step",
        ),
        (
            lambda c, s: [
                {"type": "email", "copy_id": c},
                {"type": "branch", "segment_id": s, "yes_to": 9},
                {"type": "end"},
            ],
            "later step",
        ),
        (lambda c, s: [{"type": "email", "copy_id": c}, {"type": "branch", "segment_id": s}], "last step"),
        (
            lambda c, s: [{"type": "email", "copy_id": c}, {"type": "branch", "segment_id": "nope"}, {"type": "end"}],
            "branch group",
        ),
    ],
)
async def test_branches_only_go_forward_and_need_a_group(client, maker, workspace, steps_fn, message):
    trigger = await _seg(client, "NG", NG)
    seg, cid = await _seg(client, "Has video", HAS_VIDEO), await _copy(client, "One")
    r = await client.post(
        "/v1/admin/marketing/workflows",
        json={"name": "x", "trigger_segment_id": trigger, "steps": steps_fn(cid, seg), "hours": OPEN},
        headers=OPS,
    )
    assert r.status_code == 422 and message in r.text.lower() or message in r.text


# ---------- workflows: re-entry ----------
async def test_people_can_go_through_again_after_the_gap_only_if_re_entry_is_on(client, maker, workspace, on):
    await _person(maker, "a@x.test", joined=2, country="Nigeria")
    await _no_gap(client)
    trigger = await _seg(client, "NG", NG)
    cid = await _copy(client, "Hello")
    with_re = await _workflow(client, [{"type": "email", "copy_id": cid}], trigger=trigger)
    r = await client.put(
        f"/v1/admin/marketing/workflows/{with_re}",
        json={
            "name": "Flow",
            "trigger_segment_id": trigger,
            "steps": [{"type": "email", "copy_id": cid}],
            "hours": OPEN,
            "reentry_days": 30,
        },
        headers=OPS,
    )
    assert r.status_code == 200 and r.json()["reentry_days"] == 30
    await _on(client, with_re, 1)
    await wfs.tick(10)
    await wfs.tick(10)
    assert len(_mail()) == 1 and (await _enrol(maker, "a@x.test")).status == "completed"
    CLOCK["now"] += timedelta(days=10)
    await wfs.tick(10)
    assert len(_mail()) == 1  # not yet
    CLOCK["now"] += timedelta(days=25)
    await wfs.tick(10)
    e = await _enrol(maker, "a@x.test")
    assert len(_mail()) == 2 and e.runs == 2  # a fresh run sends again
    await wfs.tick(10)
    assert len(_mail()) == 2 and (await _enrol(maker, "a@x.test")).status == "completed"


async def test_without_re_entry_nobody_goes_through_twice(client, maker, workspace, on):
    await _person(maker, "a@x.test", joined=2, country="Nigeria")
    await _no_gap(client)
    trigger = await _seg(client, "NG", NG)
    wid = await _workflow(client, [{"type": "email", "copy_id": await _copy(client, "Hello")}], trigger=trigger)
    await _on(client, wid, 1)
    await wfs.tick(10)
    CLOCK["now"] += timedelta(days=400)
    for _ in range(3):
        await wfs.tick(10)
    assert len(_mail()) == 1


async def test_re_entry_needs_a_sensible_gap(client, maker, workspace):
    trigger, cid = await _seg(client, "NG", NG), await _copy(client, "Hello")
    r = await client.post(
        "/v1/admin/marketing/workflows",
        json={
            "name": "x",
            "trigger_segment_id": trigger,
            "steps": [{"type": "email", "copy_id": cid}],
            "reentry_days": 1,
        },
        headers=OPS,
    )
    assert r.status_code == 422


# ---------- AI drafts ----------
async def test_an_ai_draft_comes_back_ready_to_edit(client, workspace):
    r = await client.post(
        "/v1/admin/marketing/copies/draft",
        json={"brief": "Remind new users to make their first video", "category": "activation"},
        headers=OPS,
    )
    assert r.status_code == 200, r.text
    d = r.json()
    assert set(d) == {"subject", "preheader", "body"} and "Hi {{first_name|there}}" in d["body"]
    check = await client.post(
        "/v1/admin/marketing/copies/preview", json={**d, "name": "x", "category": "activation"}, headers=OPS
    )
    assert check.status_code == 200 and "{{" not in check.json()["html"]


async def test_a_draft_with_bad_tags_is_repaired_and_a_useless_one_is_refused(client, workspace, monkeypatch):
    llm = registry.get_llm()

    async def messy(brief, category, tags):
        return {
            "subject": "Hey {{first_name}} and {{nickname}}",
            "preheader": "",
            "body": "Hi {{first_name}},  {{secret}} hello {{company}}",
        }

    monkeypatch.setattr(llm, "draft_marketing_copy", messy)
    d = (
        await client.post("/v1/admin/marketing/copies/draft", json={"brief": "Something about videos"}, headers=OPS)
    ).json()
    assert d["subject"] == "Hey {{first_name|there}} and" and d["body"] == "Hi {{first_name|there}}, hello {{company}}"

    async def empty(brief, category, tags):
        return {"subject": "", "preheader": "", "body": ""}

    monkeypatch.setattr(llm, "draft_marketing_copy", empty)
    assert (
        await client.post("/v1/admin/marketing/copies/draft", json={"brief": "Something about videos"}, headers=OPS)
    ).status_code == 502

    async def down(brief, category, tags):
        raise RuntimeError("down")

    monkeypatch.setattr(llm, "draft_marketing_copy", down)
    r = await client.post("/v1/admin/marketing/copies/draft", json={"brief": "Something about videos"}, headers=OPS)
    assert r.status_code == 502 and "couldn't write" in r.json()["detail"]


async def test_draft_checks_and_permissions(client, workspace):
    assert (
        await client.post("/v1/admin/marketing/copies/draft", json={"brief": "short"}, headers=OPS)
    ).status_code == 422
    assert (
        await client.post("/v1/admin/marketing/copies/draft", json={"brief": "A long enough brief"}, headers=OWNER)
    ).status_code in (401, 403)


# ---------- activity ----------
async def test_activity_shows_what_was_sent_and_why_something_was_not(client, maker, workspace, on):
    for e in ("p0@x.test", "p1@x.test", "p2@x.test"):
        await _person(maker, e, joined=2, country="Nigeria")
    await _no_gap(client)
    async with maker() as s:
        u = (await s.execute(select(User).where(User.email == "p2@x.test"))).scalar_one()
        s.add(MarketingPref(user_id=u.id, token="t" * 20, opted_out_at=datetime.now(UTC)))
        await s.commit()
    seg = await _seg(client, "NG", NG)
    copy = await _copy(client, "Hello there")
    cid = (
        await client.post(
            "/v1/admin/marketing/campaigns", json={"name": "Hello NG", "segment_id": seg, "copy_id": copy}, headers=OPS
        )
    ).json()["id"]
    await client.post(f"/v1/admin/marketing/campaigns/{cid}/schedule", json={"confirm_count": 2}, headers=OPS)
    await mcamp.deliver_due()
    wid = await _workflow(client, [{"type": "email", "copy_id": copy}], trigger=seg)
    await _on(client, wid, 2)
    await client.post(
        "/v1/admin/marketing/copies/test",
        json={"name": "t", "category": "product", "subject": "T", "body": "B"},
        headers=OPS,
    )
    items = (await client.get("/v1/admin/marketing/activity", headers=OPS)).json()
    assert items["total"] >= 3 and {"campaign", "test"} <= {i["kind"] for i in items["items"]}
    camp = [i for i in (await client.get("/v1/admin/marketing/activity?kind=campaign", headers=OPS)).json()["items"]]
    assert (
        sorted(i["email"] for i in camp) == ["p0@x.test", "p1@x.test"]
        and {i["source"] for i in camp} == {"Hello NG"}
        and {i["status"] for i in camp} == {"sent"}
    )
    one = (await client.get("/v1/admin/marketing/activity?q=P1@X", headers=OPS)).json()
    assert [i["email"] for i in one["items"]] == ["p1@x.test"] and one["total"] == 1
    assert (await client.get("/v1/admin/marketing/activity?status=skipped", headers=OPS)).json()["items"] == []
    assert (await client.get("/v1/admin/marketing/activity?limit=1&offset=1", headers=OPS)).json()[
        "items"
    ].__len__() == 1


async def test_activity_names_workflow_steps_and_needs_permission(client, maker, workspace, on):
    await _person(maker, "a@x.test", joined=2, country="Nigeria")
    await _no_gap(client)
    seg = await _seg(client, "NG", NG)
    wid = await _workflow(client, [{"type": "email", "copy_id": await _copy(client, "Hi")}], trigger=seg)
    await _on(client, wid, 1)
    await wfs.tick(10)
    row = (await client.get("/v1/admin/marketing/activity?kind=workflow", headers=OPS)).json()["items"][0]
    assert row["source"] == "Flow (step 1)" and row["email"] == "a@x.test" and row["status"] == "sent"
    assert (await client.get("/v1/admin/marketing/activity", headers=OWNER)).status_code in (401, 403)
