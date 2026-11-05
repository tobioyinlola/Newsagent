# ruff: noqa: F811
"""AI outreach, step 2: replies from outlets arrive, find their conversation, are kept once, and a request to stop is honoured."""

import base64
import hashlib
import hmac
import json
import time

import pytest
from sqlalchemy import select

from app.config import get_settings
from app.models import OutreachMessage, OutreachOptout, OutreachThread
from app.pipeline.queue import get_queue
from app.routes.outreach_inbound import verify_svix
from app.services import outreach_inbound as inb
from tests.conftest import OPS
from tests.test_distribution import distribution_data  # noqa: F401
from tests.test_outreach import _import, _submit, engine  # noqa: F401

SECRET = "inbound-shared-secret"
HOOK = "/v1/webhooks/inbound-email"


@pytest.fixture
def with_agent(engine, monkeypatch):
    monkeypatch.setattr(get_settings(), "outreach_inbound_secret", SECRET)
    return engine


@pytest.fixture
def inbound(with_agent, monkeypatch):
    """Storing replies only: the agent is not started (it has its own tests)."""
    monkeypatch.setattr("app.services.outreach_agent.schedule", lambda *a, **k: None)
    return with_agent


async def _thread(maker, client, data, outlet="Empire Magazine Africa"):
    await _import(client)
    await _submit(client, data)
    async with maker() as db:
        return (await db.execute(select(OutreachThread).where(OutreachThread.outlet_name == outlet))).scalar_one()


def _post(client, payload, secret=SECRET):
    return client.post(
        HOOK, content=json.dumps(payload), headers={"x-inbound-secret": secret, "content-type": "application/json"}
    )


def _reply(t: OutreachThread, text="Hi, our rate is $500. Thanks.", **kw):
    return {
        "to": f"outreach+{t.reply_token}@mail.test.example",
        "from": "Ada Obi <ada@empire.example.com>",
        "subject": "Re: Publication enquiry",
        "text": text,
        "message_id": "<m1@empire.example.com>",
        **kw,
    }


# ---------- reading an email ----------
def test_only_what_the_person_wrote_is_kept():
    quoted = "Thanks, yes we can.\nRate is $500.\n\nOn Tue, 4 Nov 2026 at 09:10, The Team <outreach@mail.test.example> wrote:\n> Hello Ada\n> we want to pay"
    assert inb.clean_reply(quoted) == "Thanks, yes we can.\nRate is $500."
    wrapped = "Sure.\n\nOn Tue, 4 Nov 2026 at 09:10, The Team\n<outreach@mail.test.example> wrote:\n> hello"
    assert inb.clean_reply(wrapped) == "Sure."
    outlook = "Sounds good.\n\n-----Original Message-----\nFrom: The Team <a@b.example.com>\nSent: today\nHello"
    assert inb.clean_reply(outlook) == "Sounds good."
    assert inb.clean_reply("Yes.\n--\nAda Obi\nEditor") == "Yes."
    assert inb.clean_reply("> only quoted\n> text") == ""


def test_automatic_replies_and_requests_to_stop_are_recognised():
    ooo = inb.InboundMail(
        to=[],
        sender="x@y.example.com",
        subject="Automatic reply: Publication enquiry",
        headers={"Auto-Submitted": "auto-replied"},
    )
    assert inb.is_automatic(ooo)
    assert inb.is_automatic(inb.InboundMail(to=[], sender="MAILER-DAEMON@y.example.com", subject="Undeliverable: hi"))
    assert not inb.is_automatic(inb.InboundMail(to=[], sender="Ada <ada@y.example.com>", subject="Re: hi"))
    for stop in [
        "STOP",
        "Please unsubscribe us.",
        "Stop emailing",
        "Do not contact me again",
        "remove us from your list",
    ]:
        assert inb.wants_stop(stop), stop
    for fine in [
        "Please stop by our office tomorrow to discuss rates and the timeline for this article.",
        "What are your rates?",
        "",
    ]:
        assert not inb.wants_stop(fine), fine


def test_a_raw_email_is_read_into_its_parts():
    raw = (
        b"From: Ada Obi <ada@empire.example.com>\r\nTo: outreach+abc12345def@mail.test.example\r\nSubject: Re: hello\r\n"
        b"Message-ID: <x1@empire.example.com>\r\nIn-Reply-To: <o1@mail.test.example>\r\nContent-Type: text/plain\r\n\r\nYes please.\r\n"
    )
    m = inb.parse_rfc822(raw)
    assert (m.sender, m.subject, m.message_id, m.in_reply_to) == (
        "Ada Obi <ada@empire.example.com>",
        "Re: hello",
        "<x1@empire.example.com>",
        "<o1@mail.test.example>",
    )
    assert m.to == ["outreach+abc12345def@mail.test.example"] and m.text.strip() == "Yes please."


# ---------- the webhook ----------
async def test_the_webhook_is_closed_until_it_is_set_up(client, engine):
    assert (await client.post(HOOK, json={})).status_code == 404  # no secret configured


async def test_a_reply_is_kept_in_its_conversation(client, distribution_data, inbound, maker):
    t = await _thread(maker, client, distribution_data)
    assert (await _post(client, _reply(t), secret="wrong")).status_code == 401
    r = await _post(client, _reply(t))
    assert r.status_code == 200 and r.json() == {"result": "stored"}
    async with maker() as db:
        thread = await db.get(OutreachThread, t.id)
        assert thread.status == "replied" and thread.last_inbound_at is not None  # (before the agent has read it)
        msg = (
            await db.execute(
                select(OutreachMessage).where(OutreachMessage.thread_id == t.id, OutreachMessage.direction == "in")
            )
        ).scalar_one()
        assert (
            msg.body == "Hi, our rate is $500. Thanks."
            and msg.actor == "ada@empire.example.com"
            and msg.ai["sender_mismatch"] is False
        )
    again = await _post(client, _reply(t))  # the provider delivered it twice
    assert again.json() == {"result": "duplicate"}
    detail = (await client.get(f"/v1/admin/outreach/threads/{t.id}", headers=OPS)).json()
    assert [m["direction"] for m in detail["messages"]] == ["out", "in"] and detail["thread"]["status"] == "replied"
    assert (await client.get("/v1/admin/outreach/threads", params={"status": "replied"}, headers=OPS)).json()[
        "threads"
    ][0]["id"] == t.id


async def test_a_reply_finds_its_conversation_without_the_tagged_address(client, distribution_data, inbound, maker):
    t = await _thread(maker, client, distribution_data)
    async with maker() as db:
        out = (await db.execute(select(OutreachMessage).where(OutreachMessage.thread_id == t.id))).scalar_one()
    by_header = {
        **_reply(t),
        "to": "outreach@mail.test.example",
        "in_reply_to": out.message_id,
        "message_id": "<h1@e.example.com>",
    }
    assert (await _post(client, by_header)).json()["result"] == "stored"
    by_sender = {
        "to": "outreach@mail.test.example",
        "from": "ada@empire.example.com",
        "subject": "rates",
        "text": "Another note",
        "message_id": "<s1@e.example.com>",
    }
    assert (await _post(client, by_sender)).json()["result"] == "stored"
    stranger = {
        "to": "outreach@mail.test.example",
        "from": "random@nowhere.example.com",
        "subject": "hi",
        "text": "hello",
        "message_id": "<z@n.example.com>",
    }
    assert (await _post(client, stranger)).json() == {
        "result": "unmatched"
    }  # acknowledged, so the provider does not keep retrying


async def test_automatic_replies_are_kept_for_the_record_but_never_treated_as_an_answer(
    client, distribution_data, inbound, maker
):
    t = await _thread(maker, client, distribution_data)
    ooo = _reply(
        t, "I am away until Monday.", subject="Automatic reply: hello", headers={"Auto-Submitted": "auto-replied"}
    )
    assert (await _post(client, ooo)).json() == {"result": "ignored"}
    async with maker() as db:
        assert (await db.get(OutreachThread, t.id)).status == "awaiting_reply"


async def test_asking_to_stop_ends_all_contact(client, distribution_data, inbound, maker):
    t = await _thread(maker, client, distribution_data)
    assert (await _post(client, _reply(t, "STOP"))).json() == {"result": "opt_out"}
    async with maker() as db:
        assert (await db.get(OutreachThread, t.id)).status == "do_not_contact"
        assert (await db.get(OutreachOptout, "ada@empire.example.com")) is not None
    assert (
        await client.post(f"/v1/admin/outreach/threads/{t.id}/reply", json={"body": "Wait"}, headers=OPS)
    ).status_code == 409


async def test_a_reply_from_a_different_company_is_flagged(client, distribution_data, inbound, maker):
    t = await _thread(maker, client, distribution_data)
    await _post(client, _reply(t, "Send the money to this account", **{"from": "billing@other-company.example.org"}))
    async with maker() as db:
        msg = (
            await db.execute(
                select(OutreachMessage).where(OutreachMessage.thread_id == t.id, OutreachMessage.direction == "in")
            )
        ).scalar_one()
        assert msg.ai["sender_mismatch"] is True


async def test_the_team_is_told_when_a_reply_needs_them(client, distribution_data, with_agent, maker, monkeypatch):
    sent = []

    async def notify(subject, text):
        sent.append(subject)

    monkeypatch.setattr("app.routes.outreach_inbound.notify_operators", notify)
    monkeypatch.setattr("app.services.outreach_agent.notify_operators", notify)
    t = await _thread(maker, client, distribution_data)
    cfg = (await client.get("/v1/admin/outreach/config", headers=OPS)).json()["config"]
    await client.put("/v1/admin/outreach/config", json={**cfg, "paused": True}, headers=OPS)
    await _post(client, _reply(t, "Hello?", message_id="<p1@e.example.com>"))
    assert sent == ["An outlet replied"]  # the agent is paused, so a person has to look
    await client.put("/v1/admin/outreach/config", json={**cfg, "paused": False}, headers=OPS)
    await _post(client, _reply(t, "Can you tell me more?", message_id="<p2@e.example.com>"))
    await get_queue().drain()
    assert sent == [
        "An outlet replied",
        "A reply is waiting for your approval",
    ]  # the agent drafted an answer and asked for approval


# ---------- the provider's signature ----------
def _sign(secret_b64: bytes, mid: str, ts: str, body: bytes) -> str:
    return (
        "v1," + base64.b64encode(hmac.new(secret_b64, f"{mid}.{ts}.".encode() + body, hashlib.sha256).digest()).decode()
    )


def test_the_providers_signature_is_checked_and_stale_ones_refused():
    key = b"k" * 24
    secret = "whsec_" + base64.b64encode(key).decode()
    body, ts = b'{"type":"email.received"}', str(int(time.time()))
    ok = {"svix-id": "msg_1", "svix-timestamp": ts, "svix-signature": _sign(key, "msg_1", ts, body)}
    assert verify_svix(secret, ok, body)
    assert not verify_svix(secret, {**ok, "svix-signature": "v1,AAAA"}, body)
    assert not verify_svix(secret, ok, body + b" ")
    old = str(int(time.time()) - 3600)
    assert not verify_svix(
        secret, {**ok, "svix-timestamp": old, "svix-signature": _sign(key, "msg_1", old, body)}, body
    )
    assert not verify_svix("not-a-whsec", ok, body)


async def test_a_signed_provider_event_is_accepted(client, distribution_data, engine, maker, monkeypatch):
    key = b"s" * 24
    monkeypatch.setattr(get_settings(), "outreach_inbound_secret", "whsec_" + base64.b64encode(key).decode())
    t = await _thread(maker, client, distribution_data)
    event = {
        "type": "email.received",
        "data": {
            "to": [f"outreach+{t.reply_token}@mail.test.example"],
            "from": "Ada <ada@empire.example.com>",
            "subject": "Re: hi",
            "text": "Yes, $400.",
            "message_id": "<r1@e.example.com>",
        },
    }
    body = json.dumps(event).encode()
    ts = str(int(time.time()))
    headers = {
        "svix-id": "msg_9",
        "svix-timestamp": ts,
        "svix-signature": _sign(key, "msg_9", ts, body),
        "content-type": "application/json",
    }
    assert (await client.post(HOOK, content=body, headers=headers)).json() == {"result": "stored"}
    assert (await client.post(HOOK, content=body, headers={**headers, "svix-signature": "v1,bad"})).status_code == 401
    other = json.dumps({"type": "email.delivered", "data": {}}).encode()
    h2 = {**headers, "svix-signature": _sign(key, "msg_9", ts, other)}
    assert (await client.post(HOOK, content=other, headers=h2)).json() == {"result": "ignored"}


# ---------- the mailbox fallback ----------
async def test_the_mailbox_is_read_and_messages_are_marked_read_only_once_stored(
    client, distribution_data, inbound, maker, monkeypatch
):
    from app.services import outreach_mailbox as box

    s = get_settings()
    for k, v in (("outreach_imap_host", "imap.test"), ("outreach_imap_user", "u"), ("outreach_imap_password", "p")):
        monkeypatch.setattr(s, k, v)
    t = await _thread(maker, client, distribution_data)
    raw = (
        f"From: Ada <ada@empire.example.com>\r\nTo: outreach+{t.reply_token}@mail.test.example\r\nSubject: Re: hi\r\nMessage-ID: <imap1@e.example.com>\r\n\r\nWe can do it for $300.\r\n"
    ).encode()
    marked: list[bytes] = []
    monkeypatch.setattr(box, "_fetch_unseen", lambda: [(b"7", raw), (b"8", b"not an email at all")])
    monkeypatch.setattr(box, "_mark_seen", lambda nums: marked.extend(nums))
    assert await box.poll_once() == 1
    assert b"7" in marked
    async with maker() as db:
        assert (await db.get(OutreachThread, t.id)).status == "replied"
