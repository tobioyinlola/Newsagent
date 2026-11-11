"""Bounces and complaints from the mail provider, and a person's way back in (resubscribe)."""

import base64
import hashlib
import hmac
import json
import time

import pytest
from sqlalchemy import select

from app.config import get_settings
from app.integrations import registry
from app.models import MarketingPref, MarketingSuppression, User
from app.services import marketing
from tests.conftest import OPS, OWNER

SECRET = "whsec_" + base64.b64encode(b"super-secret-key-for-tests-0123456").decode()


@pytest.fixture
def hook(monkeypatch):
    monkeypatch.setattr(get_settings(), "resend_events_secret", SECRET)
    monkeypatch.setattr(get_settings(), "marketing_email", "on")


def signed(event, *, secret=SECRET, ts=None, mid="msg_1"):
    body = json.dumps(event).encode()
    ts = str(int(ts or time.time()))
    key = base64.b64decode(secret[len("whsec_") :])
    sig = base64.b64encode(hmac.new(key, f"{mid}.{ts}.".encode() + body, hashlib.sha256).digest()).decode()
    return body, {
        "svix-id": mid,
        "svix-timestamp": ts,
        "svix-signature": f"v1,{sig}",
        "content-type": "application/json",
    }


async def post(client, event, **kw):
    body, headers = signed(event, **kw)
    return await client.post("/v1/webhooks/resend-events", content=body, headers=headers)


def bounce(kind="Permanent", to="owner@acme.test"):
    return {"type": "email.bounced", "data": {"to": [to], "bounce": {"type": kind}}}


async def _owner(maker) -> User:
    async with maker() as s:
        return (await s.execute(select(User).where(User.email == "owner@acme.test"))).scalar_one()


async def _try_send(maker):
    u = await _owner(maker)
    async with maker() as s:
        out = await marketing.send(s, await s.get(User, u.id), "Hi", "Body")
        await s.commit()
    return out


async def test_the_endpoint_is_closed_without_a_secret_and_rejects_bad_signatures(client, workspace, hook, monkeypatch):
    body, headers = signed(bounce())
    assert (
        await client.post("/v1/webhooks/resend-events", content=body, headers={**headers, "svix-signature": "v1,AAAA"})
    ).status_code == 401
    assert (await client.post("/v1/webhooks/resend-events", content=body)).status_code == 401  # no signature at all
    other = "whsec_" + base64.b64encode(b"some-other-key-entirely-0123456789").decode()
    assert (await post(client, bounce(), secret=other)).status_code == 401
    assert (await post(client, bounce(), ts=time.time() - 3600)).status_code == 401  # too old: a replay
    monkeypatch.setattr(get_settings(), "resend_events_secret", "")
    assert (await post(client, bounce())).status_code == 404


async def test_a_hard_bounce_blocks_the_address_and_nothing_more_is_sent(client, maker, workspace, hook):
    r = await post(client, bounce())
    assert r.status_code == 200 and r.json()["handled"] == 1
    async with maker() as s:
        row = await s.get(MarketingSuppression, "owner@acme.test")
        assert row is not None and row.reason == "hard bounce"
    assert await _try_send(maker) == "skipped:suppressed"
    assert [m for m in registry.get_email().sent if m["to"] == "owner@acme.test"] == []


@pytest.mark.parametrize("kind", ["Transient", "Undetermined", "", "something-new"])
async def test_a_soft_or_unclear_bounce_does_not_block(client, maker, workspace, hook, kind):
    r = await post(client, bounce(kind))
    assert r.status_code == 200 and r.json()["handled"] == 0
    async with maker() as s:
        assert await s.get(MarketingSuppression, "owner@acme.test") is None


async def test_a_spam_complaint_blocks_and_counts_as_an_unsubscribe(client, maker, workspace, hook):
    r = await post(client, {"type": "email.complained", "data": {"to": ["Owner@Acme.test"]}})
    assert r.status_code == 200 and r.json()["handled"] == 1
    u = await _owner(maker)
    async with maker() as s:
        assert (await s.get(MarketingSuppression, "owner@acme.test")).reason == "spam complaint"
        pref = await s.get(MarketingPref, u.id)
        assert pref.opted_out_at is not None and pref.source == "complaint"
    assert (
        await post(client, {"type": "email.complained", "data": {"to": ["owner@acme.test"]}}, mid="msg_2")
    ).status_code == 200  # a repeat is harmless
    assert await _try_send(maker) in {"skipped:opted_out", "skipped:suppressed"}


async def test_other_events_and_odd_payloads_are_accepted_and_ignored(client, workspace, hook):
    for t in ("email.delivered", "email.opened", "email.delivery_delayed", "something.else"):
        r = await post(client, {"type": t, "data": {"to": ["owner@acme.test"]}})
        assert r.status_code == 200 and r.json()["handled"] == 0
    assert (await post(client, bounce(to=""))).json()["handled"] == 0
    assert (
        await post(
            client, {"type": "email.bounced", "data": {"to": "owner@acme.test", "bounce": {"type": "Permanent"}}}
        )
    ).json()["handled"] == 1
    bad = b"not json"
    key = base64.b64decode(SECRET[len("whsec_") :])
    ts = str(int(time.time()))
    sig = base64.b64encode(hmac.new(key, f"m.{ts}.".encode() + bad, hashlib.sha256).digest()).decode()
    r = await client.post(
        "/v1/webhooks/resend-events",
        content=bad,
        headers={"svix-id": "m", "svix-timestamp": ts, "svix-signature": f"v1,{sig}"},
    )
    assert r.status_code == 400


# ---------- resubscribe ----------
async def _token(maker, client):
    u = await _owner(maker)
    async with maker() as s:
        await marketing.send(s, await s.get(User, u.id), "Hi", "Body")
        await s.commit()
    m = [x for x in registry.get_email().sent if x["to"] == "owner@acme.test"][0]
    return m["headers"]["List-Unsubscribe"].strip("<>").rsplit("/", 1)[1]


async def test_someone_can_resubscribe_from_the_unsubscribe_page(client, maker, workspace, hook):
    t = await _token(maker, client)
    done = await client.post(f"/v1/unsubscribe/{t}")
    assert "Resubscribe" in done.text and f"/v1/unsubscribe/{t}/resubscribe" in done.text
    again = await client.get(f"/v1/unsubscribe/{t}")  # opening the link later still offers the way back
    assert "Resubscribe" in again.text
    ok = await client.post(f"/v1/unsubscribe/{t}/resubscribe")
    assert ok.status_code == 200 and "subscribed again" in ok.text
    u = await _owner(maker)
    async with maker() as s:
        pref = await s.get(MarketingPref, u.id)
        assert pref.opted_out_at is None and pref.source == "resubscribe"
    assert "Stop marketing emails?" in (await client.get(f"/v1/unsubscribe/{t}")).text
    assert (await client.post("/v1/unsubscribe/nope/resubscribe")).status_code == 404


async def test_opening_the_link_never_changes_anything(client, maker, workspace, hook):
    t = await _token(maker, client)
    await client.get(f"/v1/unsubscribe/{t}")
    await client.get(f"/v1/unsubscribe/{t}/resubscribe")  # not even a route for GET
    u = await _owner(maker)
    async with maker() as s:
        assert (await s.get(MarketingPref, u.id)).opted_out_at is None


async def test_the_customer_can_choose_in_their_account_settings(client, maker, workspace, hook):
    assert (await client.get("/v1/me/marketing", headers=OWNER)).json() == {"subscribed": True, "blocked": False}
    off = (await client.put("/v1/me/marketing", json={"subscribed": False}, headers=OWNER)).json()
    assert off["subscribed"] is False
    assert await _try_send(maker) == "skipped:opted_out"
    on = (await client.put("/v1/me/marketing", json={"subscribed": True}, headers=OWNER)).json()
    assert on["subscribed"] is True
    assert await _try_send(maker) == "sent"
    assert (await client.get("/v1/me/marketing")).status_code in (401, 403)


async def test_a_blocked_address_is_reported_to_the_customer(client, maker, workspace, hook):
    await post(client, bounce())
    got = (await client.get("/v1/me/marketing", headers=OWNER)).json()
    assert got["blocked"] is True
    assert (await client.put("/v1/me/marketing", json={"subscribed": True}, headers=OWNER)).json()[
        "blocked"
    ] is True  # choosing doesn't unblock
    assert await _try_send(maker) == "skipped:suppressed"


# ---------- the back office lists ----------
async def test_the_back_office_lists_blocked_and_unsubscribed_and_can_lift_a_block(client, maker, workspace, hook):
    await post(client, bounce(to="owner@acme.test"))
    await post(client, bounce(to="ghost@elsewhere.test"), mid="msg_9")
    t = await _token_for_ops(maker)
    await client.post(f"/v1/unsubscribe/{t}")
    blocked = (await client.get("/v1/admin/marketing/optouts?kind=blocked", headers=OPS)).json()
    assert blocked["total"] == 2 and {i["email"] for i in blocked["items"]} == {
        "owner@acme.test",
        "ghost@elsewhere.test",
    }
    assert (await client.get("/v1/admin/marketing/optouts?kind=blocked&q=ghost", headers=OPS)).json()["total"] == 1
    gone = (await client.get("/v1/admin/marketing/optouts?kind=unsubscribed", headers=OPS)).json()
    assert [i["email"] for i in gone["items"]] == ["ops@example.com"] and gone["items"][0]["reason"] == "link"
    assert (
        await client.delete("/v1/admin/marketing/optouts/blocked/Ghost@Elsewhere.test", headers=OPS)
    ).status_code == 204
    assert (
        await client.delete("/v1/admin/marketing/optouts/blocked/ghost@elsewhere.test", headers=OPS)
    ).status_code == 404
    assert (await client.get("/v1/admin/marketing/optouts?kind=blocked", headers=OPS)).json()["total"] == 1
    assert (await client.get("/v1/admin/marketing/optouts", headers=OWNER)).status_code in (401, 403)
    assert (await client.delete("/v1/admin/marketing/optouts/blocked/owner@acme.test", headers=OWNER)).status_code in (
        401,
        403,
    )


async def _token_for_ops(maker):
    async with maker() as s:
        u = (await s.execute(select(User).where(User.email == "ops@example.com"))).scalar_one()
        pref = await marketing.pref_for(s, u.id)
        await s.commit()
        return pref.token
