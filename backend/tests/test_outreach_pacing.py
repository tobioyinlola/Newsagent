# ruff: noqa: F811
"""Outreach through a mailbox, and the pacing that keeps it out of spam: replies wait, first emails are spread out, daily limits, plain text."""

import smtplib
from datetime import timedelta

import pytest
from sqlalchemy import select, update

from app.config import get_settings
from app.integrations import registry
from app.integrations.email.mock import MockEmail
from app.integrations.email.smtp import SmtpEmail
from app.models import DistributionMail, OutreachThread
from app.models.base import utcnow
from app.pipeline.queue import get_queue
from app.services import outreach
from tests.conftest import OPS, OWNER
from tests.test_distribution import distribution_data  # noqa: F401
from tests.test_outreach import _import, _sent, _submit, engine  # noqa: F401
from tests.test_outreach_inbound import SECRET, _post, _reply  # noqa: F401

_n = 0


@pytest.fixture
def paced(engine, monkeypatch):
    monkeypatch.setattr(get_settings(), "outreach_inbound_secret", SECRET)
    monkeypatch.setattr("app.services.outreach_agent.schedule", lambda *a, **k: None)  # the agent has its own tests
    return engine


async def _config(client, **changes):
    cfg = (await client.get("/v1/admin/outreach/config", headers=OPS)).json()["config"]
    assert (await client.put("/v1/admin/outreach/config", json={**cfg, **changes}, headers=OPS)).status_code == 200


async def _threads(maker):
    async with maker() as db:
        return {t.outlet_name: t for t in (await db.execute(select(OutreachThread))).scalars()}


async def _mails(maker, **where):
    async with maker() as db:
        q = (
            select(DistributionMail)
            .where(DistributionMail.thread_id.is_not(None))
            .order_by(DistributionMail.created_at)
        )
        return [m for m in (await db.execute(q)).scalars() if all(getattr(m, k) == v for k, v in where.items())]


async def _hear_from(client, thread, text="Yes, we can do it."):
    global _n
    _n += 1
    assert (await _post(client, _reply(thread, text, message_id=f"<p{_n}@empire.example.com>"))).status_code == 200


# ---------- a reply waits a while ----------
async def test_a_reply_waits_ten_minutes_after_the_outlet_wrote(client, distribution_data, paced, maker):
    await _import(client)
    await _submit(client, distribution_data)
    await _config(client, reply_delay_minutes=10)
    t = (await _threads(maker))["Empire Magazine Africa"]
    await _hear_from(client, t)
    before = len(_sent("ada@empire.example.com"))
    r = await client.post(
        f"/v1/admin/outreach/threads/{t.id}/reply", json={"body": "Thanks Ada, here are the details."}, headers=OPS
    )
    assert r.status_code == 200
    assert len(_sent("ada@empire.example.com")) == before  # not yet
    held = (await _mails(maker, status="pending"))[-1]
    wait = (
        (held.send_after - utcnow().replace(tzinfo=None)).total_seconds() / 60
        if held.send_after.tzinfo is None
        else (held.send_after - utcnow()).total_seconds() / 60
    )
    assert 9 <= wait <= 14.5  # ten minutes, with a little give so it is not on a clock

    async with maker() as db:  # ten minutes pass
        await db.execute(
            update(DistributionMail)
            .where(DistributionMail.id == held.id)
            .values(send_after=utcnow() - timedelta(seconds=1))
        )
        await db.commit()
    assert await outreach.deliver_due() == 1
    assert (
        len(_sent("ada@empire.example.com")) == before + 1
        and "here are the details" in _sent("ada@empire.example.com")[-1]["text"]
    )
    assert await outreach.deliver_due() == 0  # nothing left to do


async def test_a_person_can_skip_the_wait_and_an_old_message_needs_none(client, distribution_data, paced, maker):
    await _import(client)
    await _submit(client, distribution_data)
    await _config(client, reply_delay_minutes=10)
    t = (await _threads(maker))["Empire Magazine Africa"]
    await _hear_from(client, t)
    before = len(_sent("ada@empire.example.com"))
    await client.post(
        f"/v1/admin/outreach/threads/{t.id}/reply", json={"body": "Urgent: please call.", "send_now": True}, headers=OPS
    )
    assert len(_sent("ada@empire.example.com")) == before + 1
    async with maker() as db:  # the outlet wrote an hour ago
        await db.execute(
            update(OutreachThread)
            .where(OutreachThread.id == t.id)
            .values(last_inbound_at=utcnow() - timedelta(hours=1))
        )
        await db.commit()
    await client.post(f"/v1/admin/outreach/threads/{t.id}/reply", json={"body": "Following up."}, headers=OPS)
    assert len(_sent("ada@empire.example.com")) == before + 2  # already waited long enough


async def test_the_agents_automatic_reply_waits_too(client, distribution_data, engine, maker, monkeypatch):
    monkeypatch.setattr(get_settings(), "outreach_inbound_secret", SECRET)
    await _import(client)
    await _submit(client, distribution_data)
    await _config(client, reply_delay_minutes=10, mode="policy")
    t = (await _threads(maker))["Empire Magazine Africa"]
    before = len(_sent("ada@empire.example.com"))
    await _hear_from(client, t, "Yes, we can do it.")
    await get_queue().drain()
    assert len(_sent("ada@empire.example.com")) == before  # written, but held for ten minutes
    held = (await _mails(maker, status="pending"))[-1]
    assert held.send_after is not None
    async with maker() as db:
        await db.execute(
            update(DistributionMail)
            .where(DistributionMail.id == held.id)
            .values(send_after=utcnow() - timedelta(seconds=1))
        )
        await db.commit()
    await outreach.deliver_due()
    assert len(_sent("ada@empire.example.com")) == before + 1


# ---------- first emails are spread out ----------
async def test_first_emails_are_spread_out_not_sent_in_a_burst(client, distribution_data, paced, maker, monkeypatch):
    monkeypatch.setattr(outreach, "_jitter", lambda m: timedelta(minutes=m))
    await _import(client)
    await _config(client, new_gap_minutes=3)
    await _submit(client, distribution_data)
    mails = await _mails(maker)
    assert len(mails) == 2
    assert len(_sent("ada@empire.example.com")) + len(_sent("bayo@techpoint.example.com")) == 1  # the first goes now
    held = [m for m in mails if m.status == "pending"]
    assert len(held) == 1 and held[0].send_after is not None
    assert (
        2.5
        <= (
            (held[0].send_after if held[0].send_after.tzinfo else held[0].send_after.replace(tzinfo=utcnow().tzinfo))
            - utcnow()
        ).total_seconds()
        / 60
        <= 3.1
    )


async def test_a_day_has_a_limit_on_first_emails(client, distribution_data, paced, maker, monkeypatch):
    monkeypatch.setattr(outreach, "_jitter", lambda m: timedelta(minutes=m))
    await _import(client)
    await _config(client, new_gap_minutes=0, new_daily_cap=1)
    await _submit(client, distribution_data)
    held = [m for m in await _mails(maker) if m.status == "pending"]
    assert len(held) == 1
    when = held[0].send_after if held[0].send_after.tzinfo else held[0].send_after.replace(tzinfo=utcnow().tzinfo)
    assert when.date() > utcnow().date() and when.hour == 8  # tomorrow morning


async def test_the_whole_mailbox_has_a_daily_sending_limit(client, distribution_data, paced, maker):
    await _import(client)
    await _config(client, send_cap_per_day=1)
    await _submit(client, distribution_data)
    mails = await _mails(maker)
    assert sorted(m.status for m in mails) == ["pending", "sent"]  # one went; the other waits for tomorrow
    await outreach.deliver_due()
    assert sorted(m.status for m in await _mails(maker)) == ["pending", "sent"]


# ---------- the mailbox ----------
async def test_outreach_goes_out_as_plain_text_and_other_emails_keep_their_design(
    client, distribution_data, paced, maker
):
    await _import(client)
    await _submit(client, distribution_data)
    mail = _sent("ada@empire.example.com")[0]
    assert (
        mail["html"] is None and "Hello Ada Obi" in mail["text"] and "reply STOP" in mail["text"]
    )  # a person-to-person email
    receipt = [m for m in registry.get_email().sent if "confirmed" in m["subject"].lower()]
    assert receipt and receipt[0]["html"]  # the receipt keeps its branded design


async def test_replies_come_back_to_the_mailbox_with_a_plus_address(
    client, distribution_data, paced, maker, monkeypatch
):
    monkeypatch.setattr(get_settings(), "outreach_mailbox", "outreach@coverfounder.example.com")
    monkeypatch.setattr(get_settings(), "outreach_reply_domain", "")
    await _import(client)
    await _submit(client, distribution_data)
    t = (await _threads(maker))["Empire Magazine Africa"]
    sent = _sent("ada@empire.example.com")[0]
    assert sent["reply_to"] == f"outreach+{t.reply_token}@coverfounder.example.com"
    assert sent["headers"]["Message-ID"].endswith("@coverfounder.example.com>")
    reply = {
        "to": sent["reply_to"],
        "from": "Ada <ada@empire.example.com>",
        "subject": "Re: x",
        "text": "Hello there",
        "message_id": "<g1@empire.example.com>",
    }
    assert (await _post(client, reply)).json() == {"result": "stored"}  # found by its plus address
    monkeypatch.setattr(get_settings(), "outreach_mailbox", "ngozi+old@coverfounder.example.com")
    assert outreach.reply_address("a" * 20) == f"ngozi+{'a' * 20}@coverfounder.example.com"


async def test_the_smtp_sender_logs_in_over_starttls_and_sets_the_headers(monkeypatch):
    calls = []

    class FakeSMTP:
        def __init__(self, host, port, timeout=None):
            calls.append(("connect", host, port))

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def starttls(self):
            calls.append(("starttls",))

        def login(self, u, p):
            calls.append(("login", u, p))

        def send_message(self, msg):
            calls.append(
                (
                    "send",
                    msg["From"],
                    msg["To"],
                    msg["Reply-To"],
                    msg["Message-ID"],
                    msg["In-Reply-To"],
                    msg.get_content().strip(),
                )
            )

    monkeypatch.setattr(smtplib, "SMTP", FakeSMTP)
    mailer = SmtpEmail(
        "smtp.gmail.com",
        587,
        "me@x.example.com",
        "app-password",
        starttls=True,
        sender="Cover Founder <me@x.example.com>",
    )
    await mailer.send(
        "ada@y.example.com",
        "Hi",
        "Body",
        reply_to="me+abc@x.example.com",
        headers={"Message-ID": "<1@x.example.com>", "In-Reply-To": "<0@y.example.com>"},
    )
    assert calls == [
        ("connect", "smtp.gmail.com", 587),
        ("starttls",),
        ("login", "me@x.example.com", "app-password"),
        (
            "send",
            "Cover Founder <me@x.example.com>",
            "ada@y.example.com",
            "me+abc@x.example.com",
            "<1@x.example.com>",
            "<0@y.example.com>",
            "Body",
        ),
    ]


async def test_outreach_uses_the_mailbox_only_when_one_is_set(monkeypatch):
    s = get_settings()
    registry.reset_providers()
    assert isinstance(registry.get_outreach_email(), MockEmail)  # none set: the usual sender
    for k, v in (
        ("outreach_smtp_host", "smtp.gmail.com"),
        ("outreach_smtp_user", "o@x.example.com"),
        ("outreach_smtp_password", "pw"),
        ("outreach_mailbox", "o@x.example.com"),
    ):
        monkeypatch.setattr(s, k, v)
    registry.reset_providers()
    mailer = registry.get_outreach_email()
    assert isinstance(mailer, SmtpEmail) and mailer.starttls and mailer.sender == "Cover Founder <o@x.example.com>"


async def test_a_test_email_can_be_sent_to_yourself_the_way_real_ones_go(client, workspace, engine, monkeypatch):
    out = MockEmail()
    registry.override(outreach_email=out)
    monkeypatch.setattr(
        get_settings(), "outreach_smtp_host", "smtp.gmail.com"
    )  # a mailbox is set, so the override is used
    r = await client.post("/v1/admin/outreach/test-send", json={"to": "me@example.com"}, headers=OPS)
    assert r.status_code == 200 and out.sent[0]["subject"].startswith("[Test] ") and out.sent[0]["html"] is None
    assert out.sent[0]["reply_to"].startswith("outreach+")
    assert (
        await client.post("/v1/admin/outreach/test-send", json={"to": "me@example.com"}, headers=OWNER)
    ).status_code in {401, 403}

    class Down(MockEmail):
        async def send(self, *a, **k):
            raise RuntimeError("smtp down")

    registry.override(outreach_email=Down())
    assert (
        await client.post("/v1/admin/outreach/test-send", json={"to": "me@example.com"}, headers=OPS)
    ).status_code == 502
