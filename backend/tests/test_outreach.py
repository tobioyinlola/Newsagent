# ruff: noqa: F811
"""AI outreach to outlets, step 1: templates, contacts, a conversation per placement, a reply address that finds its way back."""

import pytest
from sqlalchemy import select

from app.config import get_settings
from app.integrations import registry
from app.models import OutreachMessage, OutreachOptout, OutreachThread
from tests.conftest import OPS, OWNER
from tests.test_distribution import distribution_data, draft  # noqa: F401  (the fixture and helper that build a paid-ready request)

CONTACTS = """outlet,contact_name,contact_email,template
Empire Magazine Africa,Ada Obi,ada@empire.example.com,intro
Techpoint Africa,Bayo Ade,bayo@techpoint.example.com,rates
Not An Outlet,Nobody,nobody@nowhere.example.com,
Tribune,Chi,not-an-email,
"""


@pytest.fixture
def engine(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "outreach_ai", "on")
    monkeypatch.setattr(s, "outreach_reply_domain", "mail.test.example")
    for k, v in (("outreach_reply_delay_minutes", 0), ("outreach_new_gap_minutes", 0), ("outreach_new_daily_cap", 1000)):
        monkeypatch.setattr(s, k, v)  # these tests are about the conversation itself; the waiting has its own tests
    return s


async def _import(client, text=CONTACTS):
    return await client.post(
        "/v1/admin/outreach/contacts/apply", json={"text": text, "enable_automatic": True}, headers=OPS
    )


async def _submit(client, data):
    id = await draft(client, data)
    r = await client.post(f"/v1/distribution/{id}/submit", headers=OWNER)
    assert r.status_code == 200, r.text
    return id


def _sent(to):
    return [m for m in registry.get_email().sent if m["to"] == to]


async def test_contacts_are_previewed_then_saved_for_the_outlets_that_match(client, workspace):
    prev = (await client.post("/v1/admin/outreach/contacts/preview", json={"text": CONTACTS}, headers=OPS)).json()
    assert [r["status"] for r in prev["rows"]] == ["ok", "ok", "unknown_outlet", "bad_email"]
    assert prev["will_change"] == 2
    assert (await _import(client)).json() == {"applied": 2}
    cfg = (await client.get("/v1/admin/distribution/config", headers=OPS)).json()
    empire = next(o for o in cfg["outlets"] if o["name"] == "Empire Magazine Africa")
    assert (empire["contact_email"], empire["contact_name"], empire["direct_access"], empire["outreach_template"]) == (
        "ada@empire.example.com",
        "Ada Obi",
        True,
        "intro",
    )
    again = (await client.post("/v1/admin/outreach/contacts/preview", json={"text": CONTACTS}, headers=OPS)).json()
    assert again["rows"][0]["status"] == "unchanged"
    assert (
        await client.post(
            "/v1/admin/outreach/contacts/apply", json={"text": "Tribune,X,x@y.example.com,nosuchtemplate"}, headers=OPS
        )
    ).status_code == 422
    assert (
        await client.post("/v1/admin/outreach/contacts/apply", json={"text": CONTACTS}, headers=OWNER)
    ).status_code in {401, 403}


async def test_a_paid_request_opens_a_conversation_with_each_contacted_outlet(client, distribution_data, engine, maker):
    await _import(client)
    id = await _submit(client, distribution_data)
    async with maker() as db:
        threads = (await db.execute(select(OutreachThread).where(OutreachThread.request_id == id))).scalars().all()
        assert {t.outlet_name for t in threads} == {"Empire Magazine Africa", "Techpoint Africa"}
        empire = next(t for t in threads if t.outlet_name == "Empire Magazine Africa")
        assert empire.template_id == "intro" and empire.status == "awaiting_reply" and len(empire.reply_token) == 20
        msg = (await db.execute(select(OutreachMessage).where(OutreachMessage.thread_id == empire.id))).scalar_one()
        assert (
            msg.direction == "out"
            and msg.kind == "template"
            and msg.status == "sent"
            and msg.message_id.endswith("@mail.test.example>")
        )
    mail = _sent("ada@empire.example.com")[0]
    assert (
        mail["reply_to"] == f"outreach+{empire.reply_token}@mail.test.example"
    )  # replies come back to this conversation
    assert mail["headers"]["Message-ID"] == msg.message_id
    assert "Hello Ada Obi" in mail["text"] and "Acme" in mail["text"] and "reply STOP" in mail["text"]
    short = _sent("bayo@techpoint.example.com")[0]
    assert short["subject"].startswith(
        "Rates for a sponsored article on Techpoint Africa"
    )  # the other outlet got the other template


async def test_with_the_engine_off_nothing_changes(client, distribution_data, maker):
    await _import(client)
    await _submit(client, distribution_data)
    async with maker() as db:
        assert (await db.execute(select(OutreachThread))).first() is None
    assert _sent("ada@empire.example.com")[0]["reply_to"] is None


async def test_a_contact_who_opted_out_is_never_emailed(client, distribution_data, engine, maker):
    await _import(client)
    async with maker() as db:
        db.add(OutreachOptout(email="ada@empire.example.com", reason="asked to stop"))
        await db.commit()
    await _submit(client, distribution_data)
    assert _sent("ada@empire.example.com") == []
    assert len(_sent("bayo@techpoint.example.com")) == 1


async def test_templates_are_edited_checked_and_previewed(client, workspace, engine):
    cfg = (await client.get("/v1/admin/outreach/config", headers=OPS)).json()
    assert [t["id"] for t in cfg["config"]["templates"]] == ["intro", "rates", "formal"] and cfg["engine_on"] is True
    p = (await client.post("/v1/admin/outreach/preview", json={"template_id": "intro"}, headers=OPS)).json()
    assert "Hello" in p["body"] and "Acme opens its first store in Lagos" in p["subject"]
    mine = {"subject": "Hi {contact_name}", "body": "From {sender_name} about {headline}"}
    assert "Hi Ada" in (await client.post("/v1/admin/outreach/preview", json=mine, headers=OPS)).json()["subject"]
    bad = {
        **cfg["config"],
        "templates": [{"id": "x", "name": "X", "subject": "Hi", "body": "Hello {nope}"}],
        "default_template": "x",
    }
    assert (await client.put("/v1/admin/outreach/config", json=bad, headers=OPS)).status_code == 422
    good = {**cfg["config"], "sender_name": "Ngozi Eze", "footer_address": "1 Marina Road, Lagos"}
    assert (await client.put("/v1/admin/outreach/config", json=good, headers=OPS)).status_code == 200
    assert (
        "1 Marina Road, Lagos"
        in (await client.post("/v1/admin/outreach/preview", json={"template_id": "rates"}, headers=OPS)).json()["body"]
    )
    assert (await client.put("/v1/admin/outreach/config", json=good, headers=OWNER)).status_code in {401, 403}


async def test_the_team_can_read_a_conversation_and_reply_in_it(client, distribution_data, engine, maker):
    await _import(client)
    await _submit(client, distribution_data)
    listing = (await client.get("/v1/admin/outreach/threads", headers=OPS)).json()
    assert listing["counts"] == {"awaiting_reply": 2} and len(listing["threads"]) == 2
    empire = next(t for t in listing["threads"] if t["outlet_name"] == "Empire Magazine Africa")
    assert (await client.get("/v1/admin/outreach/threads", params={"q": "techpoint"}, headers=OPS)).json()["threads"][
        0
    ]["outlet_name"] == "Techpoint Africa"
    detail = (await client.get(f"/v1/admin/outreach/threads/{empire['id']}", headers=OPS)).json()
    assert detail["messages"][0]["status"] == "sent" and detail["request"]["headline"]

    r = await client.post(
        f"/v1/admin/outreach/threads/{empire['id']}/reply",
        json={"body": "Thanks Ada, here are the details."},
        headers=OPS,
    )
    assert r.status_code == 200, r.text
    reply = _sent("ada@empire.example.com")[-1]
    assert (
        reply["subject"].startswith("Re: ")
        and reply["headers"]["In-Reply-To"] == detail["messages"][0]["id"]
        or reply["headers"].get("In-Reply-To")
    )
    assert "Thanks Ada" in reply["text"] and reply["reply_to"].startswith("outreach+")

    assert (
        await client.post(
            f"/v1/admin/outreach/threads/{empire['id']}/status", json={"status": "do_not_contact"}, headers=OPS
        )
    ).status_code == 200
    assert (
        await client.post(f"/v1/admin/outreach/threads/{empire['id']}/reply", json={"body": "Again?"}, headers=OPS)
    ).status_code == 409
    assert (await client.get("/v1/admin/outreach/threads", headers=OWNER)).status_code in {401, 403}
