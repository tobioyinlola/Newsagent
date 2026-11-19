"""The on/off switch for suggested plans: off unless turned on, the back office can flip it at once, and when it is off nothing is offered."""

import pytest
from sqlalchemy import select

from app.config import get_settings
from app.models import AuditLog, PlannerEvent
from tests.conftest import OPS, OWNER

PLAN = {"countries": ["Nigeria"], "budget": "300"}
EVENT = {"kind": "used", "source": "public", "plan_key": "balanced", "outlets": 4, "credits": "80"}


@pytest.fixture
def off(monkeypatch):
    monkeypatch.setattr(get_settings(), "outlet_planner", "off")


async def test_it_is_off_unless_someone_turns_it_on(client, workspace):
    assert get_settings().outlet_planner == "off"  # the shipped default
    state = (await client.get("/v1/admin/planner-settings", headers=OPS)).json()
    assert state["enabled"] is False and state["source"] == "default"


async def test_when_off_nothing_is_offered_and_nothing_is_recorded(client, maker, workspace, off):
    for url, body, headers in (
        ("/v1/public/distribution/plan", PLAN, {}),
        ("/v1/distribution/plan", PLAN, OWNER),
        ("/v1/public/distribution/plan/event", EVENT, {}),
        ("/v1/distribution/plan/event", EVENT, OWNER),
    ):
        r = await client.post(url, json=body, headers=headers)
        assert r.status_code == 404, (url, r.text)
    async with maker() as db:
        assert (await db.execute(select(PlannerEvent))).scalars().all() == []


async def test_the_outlet_lists_tell_the_screens_whether_to_show_the_planner(client, workspace, off):
    assert (await client.get("/v1/public/distribution/outlets")).json()["planner"] is False
    assert (await client.get("/v1/distribution/outlets", headers=OWNER)).json()["planner"] is False
    await client.put("/v1/admin/planner-settings", json={"enabled": True}, headers=OPS)
    assert (await client.get("/v1/public/distribution/outlets")).json()["planner"] is True
    assert (await client.get("/v1/distribution/outlets", headers=OWNER)).json()["planner"] is True


async def test_the_back_office_turns_it_on_and_off_straight_away_and_it_is_audited(client, maker, workspace, off):
    assert (await client.post("/v1/public/distribution/plan", json=PLAN)).status_code == 404
    on = await client.put("/v1/admin/planner-settings", json={"enabled": True}, headers=OPS)
    assert on.status_code == 200 and on.json()["enabled"] is True and on.json()["source"] == "back office"
    assert on.json()["changed_by"] == "ops@example.com"
    assert (await client.post("/v1/public/distribution/plan", json=PLAN)).status_code == 200
    await client.put("/v1/admin/planner-settings", json={"enabled": False}, headers=OPS)
    assert (await client.post("/v1/public/distribution/plan", json=PLAN)).status_code == 404
    async with maker() as db:
        rows = (await db.execute(select(AuditLog).where(AuditLog.action == "distribution.planner_switch").order_by(AuditLog.created_at))).scalars().all()
    assert [(r.detail["from"], r.detail["to"]) for r in rows] == [(False, True), (True, False)]


async def test_a_choice_in_the_back_office_beats_the_default_either_way(client, workspace, monkeypatch):
    monkeypatch.setattr(get_settings(), "outlet_planner", "on")
    assert (await client.get("/v1/admin/planner-settings", headers=OPS)).json() == {"enabled": True, "source": "default", "changed_by": None, "changed_at": None}
    await client.put("/v1/admin/planner-settings", json={"enabled": False}, headers=OPS)
    assert (await client.get("/v1/admin/planner-settings", headers=OPS)).json()["enabled"] is False  # off, even though the default says on
    assert (await client.post("/v1/public/distribution/plan", json=PLAN)).status_code == 404


async def test_only_people_allowed_to_manage_can_flip_it(client, workspace):
    assert (await client.put("/v1/admin/planner-settings", json={"enabled": True})).status_code in {401, 403}
    assert (await client.put("/v1/admin/planner-settings", json={"enabled": True}, headers=OWNER)).status_code == 403  # a customer
    assert (await client.get("/v1/admin/planner-settings", headers=OWNER)).status_code == 403
    assert (await client.put("/v1/admin/planner-settings", json={"enabled": "maybe"}, headers=OPS)).status_code == 422


async def test_the_numbers_stay_readable_while_it_is_off(client, workspace, off):
    r = await client.get("/v1/admin/planner-stats", headers=OPS)
    assert r.status_code == 200 and r.json()["total"]["shown"] == 0
