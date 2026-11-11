# ruff: noqa: F811
"""Marketing campaigns: a copy to a segment, paced, guarded, and never sent twice."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.config import get_settings
from app.integrations import registry
from app.models import MarketingPref, MarketingRecipient, MarketingSend, User
from app.services import marketing
from app.services import marketing_campaigns as mcamp
from tests.conftest import OPS, OWNER
from tests.test_marketing_segments import _person

COPY = {
    "name": "Nudge",
    "category": "activation",
    "subject": "{{first_name|there}}, make a video",
    "preheader": "",
    "body": "Hi {{first_name|there}}, {{company}} has {{credits_left}} credits.",
    "button_label": "Go",
    "button_url": "/dashboard",
}
RULES = {"match": "all", "conditions": [{"field": "country", "op": "in", "value": ["Nigeria"]}]}


@pytest.fixture
def on(monkeypatch):
    monkeypatch.setattr(get_settings(), "marketing_email", "on")


async def _setup(client, maker, n=3):
    for i in range(n):
        await _person(maker, f"p{i}@x.test", joined=2, country="Nigeria")
    seg = (
        await client.post("/v1/admin/marketing/segments", json={"name": "Nigeria", "rules": RULES}, headers=OPS)
    ).json()["id"]
    copy = (await client.post("/v1/admin/marketing/copies", json=COPY, headers=OPS)).json()["id"]
    c = await client.post(
        "/v1/admin/marketing/campaigns", json={"name": "Nudge NG", "segment_id": seg, "copy_id": copy}, headers=OPS
    )
    assert c.status_code == 201, c.text
    return c.json()["id"], seg, copy


async def _go(client, cid, n, when=None):
    return await client.post(
        f"/v1/admin/marketing/campaigns/{cid}/schedule", json={"send_at": when, "confirm_count": n}, headers=OPS
    )


def _mail():
    return [m for m in registry.get_email().sent if m["to"].endswith("@x.test")]


async def test_send_now_reaches_everyone_once_with_the_pinned_words(client, maker, workspace, on):
    cid, _, copy = await _setup(client, maker)
    assert (await _go(client, cid, 3)).json()["status"] == "scheduled"
    # editing the copy after scheduling must not change what goes out
    await client.put(f"/v1/admin/marketing/copies/{copy}", json={**COPY, "subject": "CHANGED"}, headers=OPS)
    assert (await mcamp.deliver_due())["delivered"] == 3
    assert sorted(m["to"] for m in _mail()) == ["p0@x.test", "p1@x.test", "p2@x.test"]
    assert all(m["subject"] == "there, make a video" and "Hi there, p" in m["text"] for m in _mail())
    assert all("/v1/unsubscribe/" in m["headers"]["List-Unsubscribe"] for m in _mail())
    got = (await client.get(f"/v1/admin/marketing/campaigns/{cid}", headers=OPS)).json()
    assert got["status"] == "sent" and got["counts"]["sent"] == 3 and got["audience"] == 3
    await mcamp.deliver_due()  # running again sends nothing more
    assert len(_mail()) == 3


async def test_it_is_spread_out_a_few_a_minute(client, maker, workspace, on):
    cid, *_ = await _setup(client, maker, 5)
    await client.put(
        "/v1/admin/marketing/config", json={"per_minute": 2, "min_gap_days": 2, "daily_cap": 500}, headers=OPS
    )
    await _go(client, cid, 5)
    assert [(await mcamp.deliver_due())["delivered"] for _ in range(4)] == [2, 2, 1, 0]
    assert (await client.get(f"/v1/admin/marketing/campaigns/{cid}", headers=OPS)).json()["status"] == "sent"


async def test_a_later_time_waits_and_the_audience_is_fixed_when_it_starts(client, maker, workspace, on):
    cid, *_ = await _setup(client, maker, 2)
    later = (datetime.now(UTC) + timedelta(hours=2)).isoformat()
    assert (await _go(client, cid, 2, later)).status_code == 200
    assert (await mcamp.deliver_due()) == {"started": 0, "delivered": 0} and _mail() == []
    assert (await mcamp.deliver_due(datetime.now(UTC) + timedelta(hours=3)))["started"] == 1
    assert len(_mail()) == 2


async def test_unsubscribed_and_recently_mailed_people_are_left_out(client, maker, workspace, on):
    cid, *_ = await _setup(client, maker, 3)
    async with maker() as s:
        u = (await s.execute(select(User).where(User.email == "p0@x.test"))).scalar_one()
        s.add(MarketingPref(user_id=u.id, token="t" * 20, opted_out_at=datetime.now(UTC)))
        v = (await s.execute(select(User).where(User.email == "p1@x.test"))).scalar_one()
        s.add(MarketingSend(user_id=v.id, kind="campaign", status="sent"))  # got a marketing email an hour ago
        await s.commit()
    r = await _go(client, cid, 2)  # p0 isn't counted: they can't be emailed
    assert r.status_code == 200
    await mcamp.deliver_due()
    assert sorted(m["to"] for m in _mail()) == ["p2@x.test"]
    got = (await client.get(f"/v1/admin/marketing/campaigns/{cid}", headers=OPS)).json()["counts"]
    assert got["sent"] == 1 and got["skipped_by_reason"] == {"too_soon": 1}


async def test_the_daily_cap_pauses_a_campaign_and_it_carries_on_later(client, maker, workspace, on):
    cid, *_ = await _setup(client, maker, 3)
    await client.put(
        "/v1/admin/marketing/config", json={"daily_cap": 1, "min_gap_days": 2, "per_minute": 20}, headers=OPS
    )
    await _go(client, cid, 3)
    await mcamp.deliver_due()
    got = (await client.get(f"/v1/admin/marketing/campaigns/{cid}", headers=OPS)).json()
    assert got["status"] == "sending" and got["counts"]["sent"] == 1 and got["counts"]["pending"] == 2
    await client.put(
        "/v1/admin/marketing/config", json={"daily_cap": 500, "min_gap_days": 2, "per_minute": 20}, headers=OPS
    )
    await mcamp.deliver_due()
    assert len(_mail()) == 3
    async with maker() as s:  # waiting for the cap is not logged as a skip every minute
        assert not (await s.execute(select(MarketingSend).where(MarketingSend.skip_reason == "daily_cap"))).first()


async def test_pause_holds_everything_and_cancel_stops_the_rest(client, maker, workspace, on):
    cid, *_ = await _setup(client, maker, 4)
    await client.put(
        "/v1/admin/marketing/config",
        json={"per_minute": 2, "min_gap_days": 2, "daily_cap": 500, "paused": True},
        headers=OPS,
    )
    await _go(client, cid, 4)
    assert await mcamp.deliver_due() == {"started": 0, "delivered": 0} and _mail() == []
    await client.put(
        "/v1/admin/marketing/config", json={"per_minute": 2, "min_gap_days": 2, "daily_cap": 500}, headers=OPS
    )
    await mcamp.deliver_due()
    assert len(_mail()) == 2
    c = (await client.post(f"/v1/admin/marketing/campaigns/{cid}/cancel", headers=OPS)).json()
    assert (
        c["status"] == "cancelled" and c["counts"]["sent"] == 2 and c["counts"]["skipped_by_reason"] == {"cancelled": 2}
    )
    await mcamp.deliver_due()
    assert len(_mail()) == 2


async def test_dry_run_records_but_sends_nothing(client, maker, workspace, monkeypatch):
    monkeypatch.setattr(get_settings(), "marketing_email", "dry_run")
    cid, *_ = await _setup(client, maker, 2)
    await _go(client, cid, 2)
    await mcamp.deliver_due()
    assert _mail() == []
    async with maker() as s:
        assert [x.status for x in (await s.execute(select(MarketingSend))).scalars()] == ["dry_run", "dry_run"]


async def test_scheduling_is_checked(client, maker, workspace, monkeypatch):
    cid, *_ = await _setup(client, maker, 2)
    r = await _go(client, cid, 2)  # the engine is off
    assert r.status_code == 409 and "switched off" in r.json()["detail"]
    monkeypatch.setattr(get_settings(), "marketing_email", "on")
    assert (await _go(client, cid, 99)).status_code == 409  # not the number they were shown
    past = (datetime.now(UTC) - timedelta(days=1)).isoformat()
    assert (await _go(client, cid, 2, past)).status_code == 422
    assert (await _go(client, cid, 2)).status_code == 200
    assert (await _go(client, cid, 2)).status_code == 409  # already scheduled
    assert (
        await client.put(
            f"/v1/admin/marketing/campaigns/{cid}", json={"name": "x", "segment_id": "a", "copy_id": "b"}, headers=OPS
        )
    ).status_code == 409


async def test_nobody_to_email_and_bad_picks(client, maker, workspace, on):
    seg = (
        await client.post("/v1/admin/marketing/segments", json={"name": "None", "rules": RULES}, headers=OPS)
    ).json()["id"]
    copy = (await client.post("/v1/admin/marketing/copies", json=COPY, headers=OPS)).json()["id"]
    cid = (
        await client.post(
            "/v1/admin/marketing/campaigns", json={"name": "Empty", "segment_id": seg, "copy_id": copy}, headers=OPS
        )
    ).json()["id"]
    assert (await _go(client, cid, 0)).status_code == 422
    bad = await client.post(
        "/v1/admin/marketing/campaigns", json={"name": "x", "segment_id": "nope", "copy_id": copy}, headers=OPS
    )
    assert bad.status_code == 422
    assert (await client.delete(f"/v1/admin/marketing/campaigns/{cid}", headers=OPS)).status_code == 204


async def test_a_failing_provider_marks_the_person_failed_and_the_rest_still_go(
    client, maker, workspace, on, monkeypatch
):
    cid, *_ = await _setup(client, maker, 3)
    mail = registry.get_email()
    real = mail.send
    calls = {"n": 0}

    async def flaky(to, *a, **k):
        calls["n"] += 1
        if calls["n"] == 1:
            raise RuntimeError("down")
        return await real(to, *a, **k)

    monkeypatch.setattr(mail, "send", flaky)
    await _go(client, cid, 3)
    await mcamp.deliver_due()
    got = (await client.get(f"/v1/admin/marketing/campaigns/{cid}", headers=OPS)).json()
    assert got["counts"]["failed"] == 1 and got["counts"]["sent"] == 2 and got["status"] == "sent"
    async with maker() as s:
        assert (
            await s.execute(select(MarketingRecipient).where(MarketingRecipient.status == "pending"))
        ).first() is None


async def test_permissions(client, maker, workspace):
    cid, *_ = await _setup(client, maker, 1)
    assert (await client.get("/v1/admin/marketing/campaigns", headers=OWNER)).status_code in (401, 403)
    assert (await client.post(f"/v1/admin/marketing/campaigns/{cid}/cancel", headers=OWNER)).status_code in (401, 403)
    assert marketing.engine_mode() == "off"
