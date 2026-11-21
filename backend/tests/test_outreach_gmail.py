# ruff: noqa: F811
"""Connecting a Gmail address in the back office: tested in plain words, stored encrypted, never shown again, and nothing is sent without it."""

import imaplib
import json
import smtplib

import pytest
from sqlalchemy import select

from app.config import get_settings
from app.integrations import registry
from app.integrations.email.base import EmailProvider
from app.models import OutreachThread, SystemSetting
from app.services import outreach_gmail as gmail
from tests.conftest import OPS, OWNER
from tests.test_distribution import distribution_data  # noqa: F401
from tests.test_outreach import _sent, _submit  # noqa: F401
from tests.test_outreach_contacts import _import, _states, _threads  # noqa: F401

ADDR = "outreach.cf@gmail.com"
PASSWORD = "abcd efgh ijkl mnop"  # how Google shows an app password: in fours, with spaces
CONTACTS = "outlet,contact_name,contact_email\nEmpire Magazine Africa,Ada,ada@empire.example.com\n"


class FakeGmailSmtp(EmailProvider):
    """Stands in for sending straight through Gmail: records what would have gone."""

    sent: list[dict] = []

    def __init__(self, host, port, user, password, starttls=False, sender=None):
        self.args = (host, port, user, password, starttls, sender)

    async def send(self, to, subject, text, html=None, *, reply_to=None, headers=None, cc=None, bcc=None):
        FakeGmailSmtp.sent.append({"to": to, "subject": subject, "text": text, "reply_to": reply_to, "headers": headers or {}, "cc": list(cc or []), "bcc": list(bcc or []), "via": self.args})


@pytest.fixture
def google(monkeypatch):
    """What Google answers: change `answers` in a test to try each case. Nothing here touches the network."""
    answers = {"smtp": "ok", "imap": "ok"}
    monkeypatch.setattr(gmail, "_check_smtp", lambda addr, pw: answers["smtp"])
    monkeypatch.setattr(gmail, "_check_imap", lambda addr, pw: answers["imap"])
    FakeGmailSmtp.sent = []
    monkeypatch.setattr(gmail, "SmtpEmail", FakeGmailSmtp)
    return answers


@pytest.fixture
def no_route(monkeypatch):
    """Outreach is on, but nothing is set up to send from or read replies at: the situation right after switching it on."""
    s = get_settings()
    monkeypatch.setattr(s, "outreach_ai", "on")
    for k in ("outreach_reply_domain", "outreach_mailbox", "outreach_smtp_host", "outreach_imap_host"):
        monkeypatch.setattr(s, k, "")
    for k, v in (("outreach_reply_delay_minutes", 0), ("outreach_new_gap_minutes", 0), ("outreach_new_daily_cap", 1000)):
        monkeypatch.setattr(s, k, v)
    monkeypatch.setattr("app.services.outreach_agent.schedule", lambda *a, **k: None)
    return s


async def _connect(client, password=PASSWORD, address=ADDR):
    return await client.put("/v1/admin/outreach/mailbox", json={"address": address, "app_password": password}, headers=OPS)


# ---------- the plain words ----------
async def test_before_anything_is_connected_it_says_so_and_nothing_is_ready(client, workspace, no_route):
    st = (await client.get("/v1/admin/outreach/mailbox", headers=OPS)).json()
    assert st["connected"] is False and st["ready"] is False and st["outreach_on"] is True and st["address"] is None


async def test_connecting_stores_the_password_encrypted_and_never_shows_it_again(client, maker, workspace, no_route, google):
    r = await _connect(client)
    assert r.status_code == 200, r.text
    st = r.json()
    assert (st["connected"], st["address"], st["mode"], st["source"], st["ready"]) == (True, ADDR, "smtp", "back office", True)
    assert st["sends_via"] == "Gmail" and st["connected_by"] == "ops@example.com"
    async with maker() as db:
        stored = (await db.get(SystemSetting, gmail.KEY)).value
        assert "abcdefghijklmnop" not in json.dumps(stored) and "abcd" not in json.dumps(stored)  # encrypted, spaces or not
        assert (await gmail.current(db)).password == "abcdefghijklmnop"  # and the spaces Google adds are not part of it
    for url in ("/v1/admin/outreach/mailbox", "/v1/admin/outreach/config", "/v1/admin/outreach/needs-contact"):
        body = (await client.get(url, headers=OPS)).text
        assert "abcdefghijklmnop" not in body and "password" not in body.lower().replace("app password", "")


async def test_a_wrong_password_is_refused_with_the_steps_to_fix_it_and_nothing_is_saved(client, workspace, no_route, google):
    google["smtp"] = "login_failed"
    r = await _connect(client)
    assert r.status_code == 422
    d = r.json()["detail"]
    assert "did not accept" in d["message"] and any("app password" in s for s in d["steps"])
    assert (await client.get("/v1/admin/outreach/mailbox", headers=OPS)).json()["connected"] is False


async def test_imap_being_off_is_explained_separately(client, workspace, no_route, google):
    google["imap"] = "login_failed"
    d = (await _connect(client)).json()["detail"]
    assert "IMAP" in d["message"] and any("IMAP" in s for s in d["steps"])


async def test_gmail_being_unreachable_is_not_saved_and_says_to_try_again(client, workspace, no_route, google):
    google["imap"] = "unreachable"
    d = (await _connect(client)).json()["detail"]
    assert "try again" in d["message"] and (await client.get("/v1/admin/outreach/mailbox", headers=OPS)).json()["connected"] is False


async def test_when_the_host_blocks_sending_through_gmail_it_still_connects_and_says_how_it_will_send(client, workspace, no_route, google):
    google["smtp"] = "blocked"
    st = (await _connect(client)).json()
    assert st["connected"] and st["mode"] == "relay" and "copy to your Gmail" in st["sends_via"]


async def test_trying_an_address_does_not_save_it_and_says_what_would_happen(client, workspace, no_route, google):
    google["smtp"] = "blocked"
    r = await client.post("/v1/admin/outreach/mailbox/test", json={"address": ADDR, "app_password": PASSWORD}, headers=OPS)
    assert r.status_code == 200 and r.json()["ok"] and r.json()["mode"] == "relay" and "blocks sending" in r.json()["message"]
    assert (await client.get("/v1/admin/outreach/mailbox", headers=OPS)).json()["connected"] is False


@pytest.mark.parametrize("address,password", [("not-an-address", PASSWORD), (ADDR, "short"), (ADDR, "   ")])
async def test_nonsense_input_is_refused_in_plain_words(client, workspace, no_route, google, address, password):
    r = await _connect(client, password=password, address=address)
    assert r.status_code == 422 and r.json()["detail"]["message"]


async def test_only_people_who_manage_operations_can_connect_or_disconnect(client, workspace, no_route, google):
    body = {"address": ADDR, "app_password": PASSWORD}
    assert (await client.put("/v1/admin/outreach/mailbox", json=body, headers=OWNER)).status_code in {401, 403}
    assert (await client.post("/v1/admin/outreach/mailbox/test", json=body, headers=OWNER)).status_code in {401, 403}
    assert (await client.get("/v1/admin/outreach/mailbox", headers=OWNER)).status_code in {401, 403}
    assert (await client.delete("/v1/admin/outreach/mailbox", headers=OWNER)).status_code in {401, 403}
    assert (await client.put("/v1/admin/outreach/mailbox", json=body)).status_code in {401, 403}


async def test_disconnecting_forgets_the_password_and_nothing_sends_again(client, maker, workspace, no_route, google):
    await _connect(client)
    st = (await client.delete("/v1/admin/outreach/mailbox", headers=OPS)).json()
    assert st["connected"] is False and st["ready"] is False
    async with maker() as db:
        assert await db.get(SystemSetting, gmail.KEY) is None


# ---------- how it sends ----------
async def test_straight_through_gmail_sends_from_that_address_over_the_gmail_server(client, maker, workspace, no_route, google):
    await _connect(client)
    async with maker() as db:
        p = await gmail.provider(db)
    assert isinstance(p, FakeGmailSmtp) and p.args[:5] == ("smtp.gmail.com", 587, ADDR, "abcdefghijklmnop", True)
    assert ADDR in p.args[5]  # the From address


async def test_in_relay_mode_every_email_also_goes_hidden_to_the_gmail_and_replies_come_to_it(client, distribution_data, maker, workspace, no_route, google):
    google["smtp"] = "blocked"
    await _import(client, CONTACTS)
    await _connect(client)
    await _submit(client, distribution_data)
    t = (await _threads(maker))["Empire Magazine Africa"]
    sent = _sent("ada@empire.example.com")[0]
    assert sent["bcc"] == [ADDR] and sent["reply_to"] == f"outreach.cf+{t.reply_token}@gmail.com"
    assert sent["headers"]["Message-ID"].endswith("@gmail.com>")


# ---------- nothing sends until there is a mailbox ----------
async def test_with_outreach_on_but_no_mailbox_a_paid_request_waits_and_nothing_is_sent(client, distribution_data, maker, workspace, no_route, google):
    await _import(client, CONTACTS)
    await _submit(client, distribution_data)
    assert (await _states(maker))["Empire Magazine Africa"] == "waiting_mailbox"
    assert await _threads(maker) == {} and _sent("ada@empire.example.com") == [] and FakeGmailSmtp.sent == []
    todo = (await client.get("/v1/admin/outreach/needs-contact", headers=OPS)).json()
    assert todo["waiting_mailbox"] == 1  # Empire has a contact and waits for a mailbox
    assert [i["outlet_name"] for i in todo["needs_contact"]] == ["Techpoint Africa"]  # Techpoint has no contact at all


async def test_connecting_the_mailbox_starts_the_waiting_conversations_from_that_gmail(client, distribution_data, maker, workspace, no_route, google):
    await _import(client, CONTACTS)
    await _submit(client, distribution_data)
    assert (await _connect(client)).status_code == 200
    assert (await _states(maker))["Empire Magazine Africa"] == "started"
    t = (await _threads(maker))["Empire Magazine Africa"]
    assert len(FakeGmailSmtp.sent) == 1
    go = FakeGmailSmtp.sent[0]
    assert go["to"] == "ada@empire.example.com" and go["via"][2] == ADDR  # logged in as the Gmail
    assert go["reply_to"] == f"outreach.cf+{t.reply_token}@gmail.com"  # so the reply lands in that Gmail
    assert _sent("ada@empire.example.com") == []  # and did not go out the usual way


async def test_an_email_already_queued_is_held_not_failed_while_there_is_no_mailbox(client, distribution_data, maker, workspace, no_route, google, monkeypatch):
    await _import(client, CONTACTS)
    await _connect(client)
    await _submit(client, distribution_data)
    await client.delete("/v1/admin/outreach/mailbox", headers=OPS)  # connection removed before the held email's time came
    from sqlalchemy import update

    from app.models import DistributionMail
    from app.services import distribution as dist

    async with maker() as db:
        await db.execute(update(DistributionMail).where(DistributionMail.thread_id.is_not(None)).values(status="pending", sent_at=None, attempts=0))
        await db.commit()
        FakeGmailSmtp.sent.clear()
    async with maker() as db:
        rid = (await db.execute(select(OutreachThread.request_id))).scalars().first()
    await dist.deliver_request(rid)
    assert FakeGmailSmtp.sent == []
    async with maker() as db:
        mails = (await db.execute(select(DistributionMail).where(DistributionMail.thread_id.is_not(None)))).scalars().all()
    assert mails and {m.status for m in mails} == {"pending"} and {m.attempts for m in mails} == {0}  # waiting, not failed


async def test_the_test_email_needs_a_mailbox_and_then_goes_out_the_same_way(client, workspace, no_route, google):
    assert (await client.post("/v1/admin/outreach/test-send", json={"to": "me@example.com"}, headers=OPS)).status_code == 409
    await _connect(client)
    assert (await client.post("/v1/admin/outreach/test-send", json={"to": "me@example.com"}, headers=OPS)).json() == {"sent": True}
    assert FakeGmailSmtp.sent[0]["to"] == "me@example.com" and FakeGmailSmtp.sent[0]["reply_to"].startswith("outreach.cf+")


# ---------- reading replies ----------
async def test_replies_are_read_from_the_connected_gmail_and_the_back_office_sees_how_it_went(client, distribution_data, maker, workspace, no_route, google, monkeypatch):
    from app.services import outreach_mailbox as box

    await _import(client, CONTACTS)
    await _connect(client)
    await _submit(client, distribution_data)
    t = (await _threads(maker))["Empire Magazine Africa"]
    raw = f"From: Ada <ada@empire.example.com>\r\nTo: outreach.cf+{t.reply_token}@gmail.com\r\nSubject: Re: hi\r\nMessage-ID: <g1@e.example.com>\r\n\r\nYes we can do it.\r\n".encode()
    seen_creds: list = []
    marked: list = []

    def fetch(creds):
        seen_creds.append(creds)
        return [(b"3", raw)]

    monkeypatch.setattr(box, "_fetch_unseen", fetch)
    monkeypatch.setattr(box, "_mark_seen", lambda creds, nums: marked.extend(nums))
    assert await box.poll_once() == 1
    assert seen_creds[0][:4] == ("imap.gmail.com", 993, ADDR, "abcdefghijklmnop") and marked == [b"3"]
    async with maker() as db:
        assert (await db.get(OutreachThread, t.id)).status == "replied"
    st = (await client.get("/v1/admin/outreach/mailbox", headers=OPS)).json()
    assert st["last_polled_at"] and st["last_error"] == ""


async def test_if_google_stops_accepting_the_password_the_back_office_says_so(client, workspace, no_route, google, monkeypatch):
    from app.services import outreach_mailbox as box

    await _connect(client)

    def broken(creds):
        raise imaplib.IMAP4.error("AUTHENTICATIONFAILED")

    monkeypatch.setattr(box, "_fetch_unseen", broken)
    assert await box.poll_once() == 0
    st = (await client.get("/v1/admin/outreach/mailbox", headers=OPS)).json()
    assert "connect again" in st["last_error"]


async def test_nothing_is_read_when_outreach_is_off(client, workspace, no_route, google, monkeypatch):
    from app.services import outreach_mailbox as box

    await _connect(client)
    monkeypatch.setattr(get_settings(), "outreach_ai", "off")
    monkeypatch.setattr(box, "_fetch_unseen", lambda creds: pytest.fail("must not read the inbox"))
    assert await box.poll_once() == 0 and await box.configured() is False


# ---------- how a connection is judged ----------
def test_the_google_servers_answers_are_sorted_into_plain_cases(monkeypatch):
    class Smtp:
        mode = "ok"

        def __init__(self, *a, **k):
            if Smtp.mode == "down":
                raise OSError("network is unreachable")

        def __enter__(self):
            return self

        def __exit__(self, *a):
            return False

        def starttls(self):
            pass

        def login(self, u, p):
            if Smtp.mode == "bad":
                raise smtplib.SMTPAuthenticationError(535, b"bad credentials")

    monkeypatch.setattr(smtplib, "SMTP", Smtp)
    assert gmail._check_smtp(ADDR, "x" * 16) == "ok"
    Smtp.mode = "bad"
    assert gmail._check_smtp(ADDR, "x" * 16) == "login_failed"
    Smtp.mode = "down"
    assert gmail._check_smtp(ADDR, "x" * 16) == "blocked"  # could not even reach Google: the host does not allow it

    class Imap:
        mode = "ok"

        def __init__(self, *a, **k):
            if Imap.mode == "down":
                raise OSError("timed out")

        def login(self, u, p):
            if Imap.mode == "bad":
                raise imaplib.IMAP4.error("AUTHENTICATIONFAILED")

        def logout(self):
            pass

    monkeypatch.setattr(imaplib, "IMAP4_SSL", Imap)
    assert gmail._check_imap(ADDR, "x" * 16) == "ok"
    Imap.mode = "bad"
    assert gmail._check_imap(ADDR, "x" * 16) == "login_failed"
    Imap.mode = "down"
    assert gmail._check_imap(ADDR, "x" * 16) == "unreachable"


def test_an_app_password_is_cleaned_and_an_address_checked():
    assert gmail.clean_password(" abcd efgh\tijkl mnop ") == "abcdefghijklmnop"
    assert gmail.valid_address("  Name@Gmail.COM ") == "name@gmail.com"
    with pytest.raises(ValueError):
        gmail.valid_address("name at gmail")


async def test_the_old_environment_settings_still_work_when_nothing_is_connected(client, maker, workspace, monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "outreach_ai", "on")
    monkeypatch.setattr(s, "outreach_smtp_host", "smtp.example.test")
    monkeypatch.setattr(s, "outreach_mailbox", "outreach@coverfounder.example.com")
    async with maker() as db:
        assert await gmail.current(db) is None and await gmail.ready(db) is True
        assert await gmail.address(db) == "outreach@coverfounder.example.com"
        assert (await gmail.status(db))["source"] == "environment"
    assert registry.get_outreach_email() is not None


async def test_every_placeholder_a_template_can_use_works_in_the_preview_and_the_test_email(client, workspace, google):
    """A placeholder offered in the template editor must never crash the preview or the test email (it once did for {story})."""
    cfg = (await client.get("/v1/admin/outreach/config", headers=OPS)).json()
    every = "\n".join("{" + v + "}" for v in cfg["variables"])
    p = await client.post("/v1/admin/outreach/preview", json={"subject": "Hi", "body": every}, headers=OPS)
    assert p.status_code == 200, p.text
    assert not any("{" + v + "}" in p.json()["body"] for v in cfg["variables"])
    saved = {**cfg["config"], "templates": [{"id": "intro", "name": "Everything", "subject": "Hi", "body": every}], "default_template": "intro"}
    assert (await client.put("/v1/admin/outreach/config", json=saved, headers=OPS)).status_code == 200
    await client.put("/v1/admin/outreach/mailbox", json={"address": "outreach@gmail.com", "app_password": "abcd efgh ijkl mnop"}, headers=OPS)
    r = await client.post("/v1/admin/outreach/test-send", json={"to": "me@example.com"}, headers=OPS)
    assert r.status_code == 200, r.text
