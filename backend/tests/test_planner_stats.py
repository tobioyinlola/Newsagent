"""Measuring the outlet planner: events are recorded, carry no identity for visitors, cannot be spoofed, and add up correctly."""

from decimal import Decimal

import pytest
from sqlalchemy import select

from app.config import get_settings
from app.models import PlannerEvent, Project, ScriptVersion, Workspace
from app.routes import distribution as routes
from app.services import planner_stats
from tests.conftest import OPS, OWNER


async def events(maker):
    async with maker() as db:
        return (await db.execute(select(PlannerEvent).order_by(PlannerEvent.created_at, PlannerEvent.id))).scalars().all()


async def test_a_plan_made_for_a_visitor_is_counted_with_no_identity(client, maker):
    await client.post("/v1/public/distribution/plan", json={"countries": ["Nigeria"], "auto": True})
    await client.post("/v1/public/distribution/plan", json={"countries": ["Nigeria"]})
    got = await events(maker)
    assert [(e.kind, e.source, e.workspace_id) for e in got] == [("shown", "public", None), ("asked", "public", None)]


async def test_a_visitor_cannot_pass_themselves_off_as_an_internal_screen(client, maker):
    await client.post("/v1/public/distribution/plan", json={"source": "ready_prompt"})
    await client.post("/v1/public/distribution/plan", json={"source": "email"})
    await client.post(
        "/v1/public/distribution/plan/event",
        json={"kind": "used", "source": "request", "plan_key": "balanced", "outlets": 4, "credits": "80"},
    )
    assert [e.source for e in await events(maker)] == ["public", "email", "public"]


async def test_a_signed_in_event_is_tied_to_its_workspace_and_says_which_screen(client, maker, workspace):
    await client.post("/v1/distribution/plan", headers=OWNER, json={"source": "ready_prompt", "auto": True})
    r = await client.post(
        "/v1/distribution/plan/event",
        headers=OWNER,
        json={"kind": "used", "source": "ready_prompt", "plan_key": "balanced", "outlets": 4, "credits": "80.5"},
    )
    assert r.status_code == 200
    shown, used = await events(maker)
    assert (shown.kind, shown.source, shown.workspace_id) == ("shown", "ready_prompt", workspace)
    assert (used.kind, used.plan_key, used.outlets, used.credits) == ("used", "balanced", 4, Decimal("80.5"))


@pytest.mark.parametrize(
    "bad",
    [
        {"kind": "submitted", "plan_key": "balanced", "outlets": 1, "credits": "1"},  # recorded by the server only
        {"kind": "used", "plan_key": "huge", "outlets": 1, "credits": "1"},
        {"kind": "used", "plan_key": "balanced", "outlets": 101, "credits": "1"},
        {"kind": "used", "plan_key": "balanced", "outlets": 1, "credits": "-1"},
        {"kind": "used", "plan_key": "balanced", "outlets": 1, "credits": "99999999999"},
    ],
)
async def test_nonsense_events_are_refused(client, maker, bad):
    assert (await client.post("/v1/public/distribution/plan/event", json=bad)).status_code == 422
    assert await events(maker) == []


async def test_a_visitor_cannot_read_the_numbers_and_an_operator_can(client, workspace):
    assert (await client.get("/v1/admin/planner-stats")).status_code in {401, 403}
    assert (await client.get("/v1/admin/planner-stats", headers=OWNER)).status_code == 403
    assert (await client.get("/v1/admin/planner-stats?days=0", headers=OPS)).status_code == 422
    assert (await client.get("/v1/admin/planner-stats", headers=OPS)).status_code == 200


async def test_the_summary_adds_up_and_gives_rates(client, maker, workspace):
    async with maker() as db:
        for _ in range(6):
            planner_stats.record(db, "shown", "ready_prompt")
        for _ in range(4):
            planner_stats.record(db, "asked", "public")
        for _ in range(5):
            planner_stats.record(db, "used", "public", plan_key="balanced", outlets=4, credits=80)
        planner_stats.record(db, "submitted", "request", plan_key="balanced", outlets=4, credits=100, unchanged=True)
        planner_stats.record(db, "submitted", "request", plan_key="balanced", outlets=3, credits=60, unchanged=False)
        await db.commit()
    body = (await client.get("/v1/admin/planner-stats", headers=OPS)).json()
    t = body["total"]
    assert (t["shown"], t["asked"], t["used"], t["submitted"], t["unchanged"]) == (6, 4, 5, 2, 1)
    assert t["rates"]["use_of_viewed"] == 0.5 and t["rates"]["submitted_of_used"] == 0.4
    assert t["rates"]["unchanged_of_submitted"] == 0.5 and t["rates"]["average_credits"] == "80.0"
    assert body["by_source"]["public"]["asked"] == 4 and body["by_source"]["ready_prompt"]["shown"] == 6
    assert body["by_source"]["email"]["rates"]["use_of_viewed"] is None  # nothing there yet: no rate, not zero


async def test_events_older_than_the_window_are_left_out(client, maker, workspace):
    from datetime import timedelta

    from app.models.base import utcnow

    async with maker() as db:
        planner_stats.record(db, "asked", "public")
        old = PlannerEvent(kind="asked", source="public", created_at=utcnow() - timedelta(days=40))
        db.add(old)
        await db.commit()
    assert (await client.get("/v1/admin/planner-stats?days=30", headers=OPS)).json()["total"]["asked"] == 1
    assert (await client.get("/v1/admin/planner-stats?days=90", headers=OPS)).json()["total"]["asked"] == 2


@pytest.fixture
async def paid_draft(maker, workspace, monkeypatch):
    for o in routes.OUTLETS.values():
        monkeypatch.setitem(o, "credits", "0")
    monkeypatch.setattr(get_settings(), "hide_free_distribution_outlets", False)
    async with maker() as db:
        project = Project(workspace_id=workspace, state="final_ready")
        db.add(project)
        await db.flush()
        db.add(ScriptVersion(project_id=project.id, story={"headline": "Acme", "dek": "d", "sections": [{"heading": "h", "paragraphs": ["p"]}]}))
        await db.commit()
        return project.id


async def _submit(client, project_id, **extra):
    r = await client.post("/v1/distribution", headers=OWNER)
    id = r.json()["id"]
    data = {"stage": "review", "outlet_ids": ["1", "2"], "project_id": project_id, "headline": "H", "announcement": "A", "contact_name": "Ada", "contact_email": "ada@example.com", "phone": "+2348012345678", **extra}
    assert (await client.put(f"/v1/distribution/{id}", headers=OWNER, json=data)).status_code == 200
    done = await client.post(f"/v1/distribution/{id}/submit", headers=OWNER)
    assert done.status_code == 200, done.text


async def test_a_paid_request_that_began_from_a_plan_records_whether_it_was_kept(client, maker, paid_draft, workspace):
    await _submit(client, paid_draft, plan_key="balanced", plan_ids=["1", "2"])
    await _submit(client, paid_draft, plan_key="essential", plan_ids=["1", "3"])  # changed one outlet
    got = [e for e in await events(maker) if e.kind == "submitted"]
    assert [(e.plan_key, e.unchanged, e.outlets, e.workspace_id) for e in got] == [("balanced", True, 2, workspace), ("essential", False, 2, workspace)]


async def test_a_request_with_no_plan_records_nothing(client, maker, paid_draft):
    await _submit(client, paid_draft)
    assert await events(maker) == []


async def test_erasing_a_workspace_erases_its_planner_events_and_keeps_the_anonymous_ones(client, maker, workspace):
    from app.services import privacy

    async with maker() as db:
        planner_stats.record(db, "used", "request", workspace_id=workspace, plan_key="balanced", outlets=3, credits=10)
        planner_stats.record(db, "used", "public", plan_key="balanced", outlets=3, credits=10)  # a visitor: nothing to erase
        await db.commit()
    async with maker() as db:
        await privacy.delete_workspace(db, await db.get(Workspace, workspace))
        await db.commit()
    left = await events(maker)
    assert [(e.source, e.workspace_id) for e in left] == [("public", None)]
