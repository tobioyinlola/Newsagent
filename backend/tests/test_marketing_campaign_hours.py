# ruff: noqa: F811
"""Campaign sending hours: people outside their day wait for it, without holding anyone else up."""

from datetime import UTC, datetime

import pytest
from sqlalchemy import select

from app.config import get_settings
from app.integrations import registry
from app.models import MarketingRecipient
from app.services import marketing_campaigns as mcamp
from tests.conftest import OPS
from tests.test_marketing_segments import _person

COPY = {
    "name": "Hours",
    "category": "activation",
    "subject": "Good morning",
    "preheader": "",
    "body": "Hello {{company}}",
    "button_label": "",
    "button_url": "",
}
ALL = {"match": "all", "conditions": [{"field": "country", "op": "in", "value": ["Nigeria", "United States"]}]}
HOURS = {"enabled": True, "start": 9, "end": 18}
WINTER_10_UTC = datetime(2030, 1, 15, 10, 0, tzinfo=UTC)  # 11:00 in Lagos, 05:00 in New York
WINTER_1430_UTC = datetime(2030, 1, 15, 14, 30, tzinfo=UTC)  # 15:30 in Lagos, 09:30 in New York


@pytest.fixture
def on(monkeypatch):
    monkeypatch.setattr(get_settings(), "marketing_email", "on")


async def _setup(client, maker, ng=2, us=2, hours=HOURS, per_minute=600):
    for i in range(ng):
        await _person(maker, f"ng{i}@x.test", joined=2, country="Nigeria")
    for i in range(us):
        await _person(maker, f"us{i}@x.test", joined=2, country="United States")
    await client.put("/v1/admin/marketing/config", json={"per_minute": per_minute, "min_gap_days": 2}, headers=OPS)
    seg = (await client.post("/v1/admin/marketing/segments", json={"name": "All", "rules": ALL}, headers=OPS)).json()[
        "id"
    ]
    copy = (await client.post("/v1/admin/marketing/copies", json=COPY, headers=OPS)).json()["id"]
    body = {"name": "H", "segment_id": seg, "copy_id": copy, "hours": hours}
    cid = (await client.post("/v1/admin/marketing/campaigns", json=body, headers=OPS)).json()["id"]
    r = await client.post(f"/v1/admin/marketing/campaigns/{cid}/schedule", json={"confirm_count": ng + us}, headers=OPS)
    assert r.status_code == 200, r.text
    return cid


def _to():
    return sorted(m["to"] for m in registry.get_email().sent if m["to"].endswith("@x.test"))


async def _counts(client, cid):
    return (await client.get(f"/v1/admin/marketing/campaigns/{cid}", headers=OPS)).json()


async def test_people_outside_their_day_wait_for_it_and_are_sent_when_it_opens(client, maker, workspace, on):
    cid = await _setup(client, maker)
    await mcamp.deliver_due(WINTER_10_UTC)
    assert _to() == ["ng0@x.test", "ng1@x.test"]  # Lagos is mid-morning; New York is 5 in the morning
    c = await _counts(client, cid)
    assert c["status"] == "sending" and c["counts"]["sent"] == 2 and c["counts"]["pending"] == 2
    async with maker() as s:
        waiting = (
            (await s.execute(select(MarketingRecipient).where(MarketingRecipient.status == "pending"))).scalars().all()
        )
        assert {r.send_after.replace(tzinfo=UTC) for r in waiting} == {
            datetime(2030, 1, 15, 14, 0, tzinfo=UTC)
        }  # 09:00 in New York
    await mcamp.deliver_due(datetime(2030, 1, 15, 12, 0, tzinfo=UTC))
    assert len(_to()) == 2  # still too early
    await mcamp.deliver_due(WINTER_1430_UTC)
    assert _to() == ["ng0@x.test", "ng1@x.test", "us0@x.test", "us1@x.test"]
    assert (await _counts(client, cid))["status"] == "sent"


async def test_waiting_people_never_hold_up_those_who_can_be_sent_to_now(client, maker, workspace, on):
    cid = await _setup(client, maker, ng=3, us=10, per_minute=2)
    await mcamp.deliver_due(WINTER_10_UTC)
    assert len(_to()) == 2
    await mcamp.deliver_due(WINTER_10_UTC)
    assert len(_to()) == 3 and all(
        e.startswith("ng") for e in _to()
    )  # every Nigerian, though ten others were ahead in line
    assert (await _counts(client, cid))["counts"]["pending"] == 10


async def test_a_campaign_without_hours_sends_at_once_as_before(client, maker, workspace, on):
    cid = await _setup(client, maker, hours=None)
    await mcamp.deliver_due(WINTER_10_UTC)
    assert len(_to()) == 4
    assert (await _counts(client, cid))["hours"] is None


async def test_the_screen_is_told_how_many_are_waiting_for_their_morning(client, maker, workspace, on):
    cid = await _setup(client, maker)
    await mcamp.deliver_due(
        datetime.now(UTC).replace(hour=10, minute=0)
    )  # any time today; the waiting ones are in the future or sent
    c = await _counts(client, cid)
    assert "deferred" in c["counts"] and c["hours"] == HOURS


async def test_hours_are_checked_and_can_be_changed_on_a_draft(client, maker, workspace):
    await _person(maker, "a@x.test", joined=2, country="Nigeria")
    seg = (await client.post("/v1/admin/marketing/segments", json={"name": "All", "rules": ALL}, headers=OPS)).json()[
        "id"
    ]
    copy = (await client.post("/v1/admin/marketing/copies", json=COPY, headers=OPS)).json()["id"]
    body = {"name": "H", "segment_id": seg, "copy_id": copy}
    bad = await client.post(
        "/v1/admin/marketing/campaigns", json={**body, "hours": {"enabled": True, "start": 18, "end": 9}}, headers=OPS
    )
    assert bad.status_code == 422
    cid = (await client.post("/v1/admin/marketing/campaigns", json=body, headers=OPS)).json()["id"]
    assert (await _counts(client, cid))["hours"] is None
    r = await client.put(
        f"/v1/admin/marketing/campaigns/{cid}",
        json={**body, "hours": {"enabled": True, "start": 8, "end": 20}},
        headers=OPS,
    )
    assert r.json()["hours"] == {"enabled": True, "start": 8, "end": 20}
    r = await client.put(
        f"/v1/admin/marketing/campaigns/{cid}",
        json={**body, "hours": {"enabled": False, "start": 9, "end": 18}},
        headers=OPS,
    )
    assert r.json()["hours"]["enabled"] is False


async def test_cancelling_stops_the_ones_still_waiting(client, maker, workspace, on):
    cid = await _setup(client, maker)
    await mcamp.deliver_due(WINTER_10_UTC)
    c = (await client.post(f"/v1/admin/marketing/campaigns/{cid}/cancel", headers=OPS)).json()
    assert c["counts"]["sent"] == 2 and c["counts"]["skipped_by_reason"] == {"cancelled": 2}
    await mcamp.deliver_due(WINTER_1430_UTC)
    assert len(_to()) == 2
