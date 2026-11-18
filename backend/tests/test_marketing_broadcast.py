# ruff: noqa: F811
"""Campaigns sent as one Resend Broadcast: one shared segment, sent once, cleaned up, with the guards that still apply."""

import pytest
from sqlalchemy import select

from app.config import get_settings
from app.integrations import registry
from app.models import MarketingPref, MarketingRecipient, MarketingSend
from app.services import marketing
from app.services import marketing_campaigns as mcamp
from tests.conftest import OPS
from tests.test_marketing_segments import _person

COPY = {
    "name": "Distribute",
    "category": "activation",
    "subject": "{{first_name|there}}, your credits are waiting",
    "preheader": "Pick your outlets",
    "body": "Hi {{first_name|there}}, send your story out.",
    "button_label": "Distribute",
    "button_url": "/distribution/request",
}
RULES = {"match": "all", "conditions": [{"field": "country", "op": "in", "value": ["Nigeria"]}]}


@pytest.fixture
def broadcast(monkeypatch):
    monkeypatch.setattr(get_settings(), "marketing_email", "on")
    monkeypatch.setattr(get_settings(), "marketing_campaign_channel", "broadcast")
    return registry.get_broadcast()


async def _campaign(client, maker, n=3, copy=COPY, extra=None, name="Credits nudge"):
    for i in range(n):
        await _person(maker, f"b{i}@x.test", joined=2, country="Nigeria")
    seg = (await client.post("/v1/admin/marketing/segments", json={"name": f"NG{name}", "rules": RULES}, headers=OPS)).json()["id"]
    cp = (await client.post("/v1/admin/marketing/copies", json=copy, headers=OPS)).json()["id"]
    c = await client.post(
        "/v1/admin/marketing/campaigns",
        json={"name": name, "segment_id": seg, "copy_id": cp, **(extra or {})},
        headers=OPS,
    )
    assert c.status_code == 201, c.text
    cid = c.json()["id"]
    r = await client.post(
        f"/v1/admin/marketing/campaigns/{cid}/schedule", json={"send_at": None, "confirm_count": n}, headers=OPS
    )
    assert r.status_code == 200, r.text
    return cid


async def _status(client, cid):
    return (await client.get(f"/v1/admin/marketing/campaigns/{cid}", headers=OPS)).json()


async def test_one_broadcast_goes_to_everyone_through_resend_not_one_email_each(client, maker, workspace, broadcast):
    cid = await _campaign(client, maker)
    for _ in range(3):
        await mcamp.deliver_due()
    assert len(broadcast.broadcasts) == 1
    b = broadcast.broadcasts[0]
    assert b["to"] == ["b0@x.test", "b1@x.test", "b2@x.test"]
    assert b["subject"] == "{{{contact.first_name|there}}}, your credits are waiting"
    assert "{{{RESEND_UNSUBSCRIBE_URL}}}" in b["html"] and "{{{RESEND_UNSUBSCRIBE_URL}}}" in b["text"]
    assert "placeholder.invalid" not in b["html"]
    assert "utm_campaign=credits-nudge" in b["html"]
    assert not [m for m in registry.get_email().sent if m["to"].endswith("@x.test")]  # nothing went out one by one
    got = await _status(client, cid)
    assert got["status"] == "sent"
    assert got["counts"]["sent"] == 3
    assert broadcast.segments[next(iter(broadcast.segments))] == set()  # the segment is emptied afterwards
    async with maker() as db:
        rows = (await db.execute(select(MarketingSend).where(MarketingSend.ref == cid))).scalars().all()
    assert len(rows) == 3 and all(r.subject == "there, your credits are waiting" for r in rows)
    await mcamp.deliver_due()
    assert len(broadcast.broadcasts) == 1  # running again sends nothing more


async def test_people_who_opted_out_are_never_put_in_the_segment(client, maker, workspace, broadcast):
    await _person(maker, "gone@x.test", joined=2, country="Nigeria")
    async with maker() as db:
        from app.models import User

        u = (await db.execute(select(User).where(User.email == "gone@x.test"))).scalar_one()
        pref = await marketing.pref_for(db, u.id)
        pref.opted_out_at = marketing.utcnow()
        await db.commit()
    await _campaign(client, maker, n=2)
    for _ in range(3):
        await mcamp.deliver_due()
    assert broadcast.broadcasts[0]["to"] == ["b0@x.test", "b1@x.test"]


async def test_a_campaign_over_the_contact_limit_sends_nothing(client, maker, workspace, broadcast, monkeypatch):
    monkeypatch.setattr(get_settings(), "resend_contact_limit", 2)
    cid = await _campaign(client, maker, n=3)
    await mcamp.deliver_due()
    assert broadcast.broadcasts == [] and not broadcast.contacts
    assert (await _status(client, cid))["status"] == "cancelled"
    async with maker() as db:
        reasons = {r.reason for r in (await db.execute(select(MarketingRecipient))).scalars()}
    assert reasons == {"resend_contact_limit"}


async def test_a_subject_test_or_other_tags_keep_the_one_by_one_path(client, maker, workspace, broadcast):
    copy = {**COPY, "body": "{{company}} has {{credits_left}} credits."}
    await _campaign(client, maker, n=2, copy=copy, name="Tags")
    await mcamp.deliver_due()
    assert broadcast.broadcasts == []
    assert len([m for m in registry.get_email().sent if m["to"].endswith("@x.test")]) == 2


async def test_a_second_campaign_waits_for_the_first_to_finish_with_the_segment(client, maker, workspace, broadcast):
    await client.put(
        "/v1/admin/marketing/config", json={"per_minute": 20, "min_gap_days": 0, "daily_cap": 500}, headers=OPS
    )
    first = await _campaign(client, maker, n=2, name="First")
    broadcast.status_value = "queued"  # Resend has not finished sending the first
    await mcamp.deliver_due()
    await mcamp.deliver_due()
    second = (
        await client.post(
            "/v1/admin/marketing/campaigns",
            json={"name": "Second", "segment_id": (await _status(client, first))["segment_id"], "copy_id": (await _status(client, first))["copy_id"]},
            headers=OPS,
        )
    ).json()["id"]
    await client.post(f"/v1/admin/marketing/campaigns/{second}/schedule", json={"send_at": None, "confirm_count": 2}, headers=OPS)
    await mcamp.deliver_due()
    assert len(broadcast.broadcasts) == 1 and (await _status(client, first))["status"] == "sending"
    broadcast.status_value = "sent"
    for _ in range(5):
        await mcamp.deliver_due()
    assert (await _status(client, first))["status"] == "sent"
    assert len(broadcast.broadcasts) == 2  # the second then goes out, to a segment that was emptied first


async def test_resend_unsubscribe_event_opts_the_person_out(client, maker, workspace):
    await _person(maker, "bye@x.test", joined=2, country="Nigeria")
    async with maker() as db:
        assert await marketing.apply_resend_unsubscribe(db, ["Bye@x.test", "nobody"]) == 1
        await db.commit()
        from app.models import User

        u = (await db.execute(select(User).where(User.email == "bye@x.test"))).scalar_one()
        assert (await db.get(MarketingPref, u.id)).opted_out_at is not None


async def test_the_resend_calls_have_the_documented_shape(monkeypatch):
    import httpx

    from app.integrations.broadcast.resend import ResendBroadcast
    from app.integrations.email import resend as sender

    async def no_wait(*a, **k):
        return None

    monkeypatch.setattr(sender, "_pace", no_wait)
    monkeypatch.setattr(sender, "_sleep", no_wait)
    seen: list[tuple[str, str, dict]] = []

    def handler(req: httpx.Request) -> httpx.Response:
        import json

        seen.append((req.method, req.url.raw_path.decode(), json.loads(req.content) if req.content else {}))
        if req.url.raw_path == b"/contacts":
            return httpx.Response(422, json={"message": "already exists"})  # an existing contact is fine
        return httpx.Response(200, json={"id": "abc", "status": "sent"})

    p = ResendBroadcast(httpx.AsyncClient(base_url="https://api.resend.com", transport=httpx.MockTransport(handler)))
    assert await p.ensure_segment("Campaign audience") == "abc"
    await p.add_contact("a+b@x.test", "Ada", "seg1")
    await p.remove_contact("a+b@x.test", "seg1")
    assert await p.send("seg1", "Nudge", "Hi", "<p>x</p>", "x") == "abc"
    assert await p.status("abc") == "sent"
    assert seen[0] == ("POST", "/segments", {"name": "Campaign audience"})
    assert seen[1] == ("POST", "/contacts", {"email": "a+b@x.test", "unsubscribed": False, "first_name": "Ada"})
    assert seen[2][:2] == ("POST", "/contacts/a%2Bb%40x.test/segments/seg1")
    assert seen[3][:2] == ("DELETE", "/contacts/a%2Bb%40x.test/segments/seg1")
    method, path, body = seen[4]
    assert (method, path, body["segment_id"], body["send"]) == ("POST", "/broadcasts", "seg1", True)
    assert seen[5][:2] == ("GET", "/broadcasts/abc")
