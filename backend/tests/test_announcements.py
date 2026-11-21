"""Announcements: a pop-up for customers for a time the team sets, and optionally an email to everyone through the usual campaign rules."""

from datetime import timedelta

import pytest
from sqlalchemy import select

from app.config import get_settings
from app.integrations import registry
from app.models import Announcement, MarketingPref, User
from app.models.base import utcnow
from app.services import marketing_campaigns as mcamp
from tests.conftest import OPS, OWNER
from tests.test_marketing_segments import _person

BODY = {"title": "New: send your story to Kenya", "message": "We now reach outlets in Kenya.", "show_for": 3, "unit": "days", "send_email": False}


async def _make(client, **over):
    r = await client.post("/v1/admin/marketing/announcements", json={**BODY, **over}, headers=OPS)
    assert r.status_code == 201, r.text
    return r.json()


async def _mine(client):
    r = await client.get("/v1/me/announcements", headers=OWNER)
    assert r.status_code == 200, r.text
    return r.json()


@pytest.fixture
def mail_on(monkeypatch):
    monkeypatch.setattr(get_settings(), "marketing_email", "on")


async def test_a_new_announcement_shows_to_customers_until_the_time_is_up(client, workspace, maker):
    a = await _make(client, show_for=2, unit="hours")
    assert a["status"] == "live" and a["email"] is None
    assert [x["title"] for x in await _mine(client)] == [BODY["title"]]
    async with maker() as db:  # time passes
        row = await db.get(Announcement, a["id"])
        row.shows_until = utcnow() - timedelta(minutes=1)
        await db.commit()
    assert await _mine(client) == []
    listed = (await client.get("/v1/admin/marketing/announcements", headers=OPS)).json()
    assert listed["items"][0]["status"] == "ended" and listed["total"] == 1


async def test_the_duration_is_set_in_hours_or_days(client, workspace):
    a = await _make(client, show_for=36, unit="hours")
    b = await _make(client, show_for=5, unit="days")
    gap = lambda x: (__import__("datetime").datetime.fromisoformat(x["shows_until"]) - __import__("datetime").datetime.fromisoformat(x["shows_from"]))  # noqa: E731
    assert gap(a) == timedelta(hours=36) and gap(b) == timedelta(days=5)


async def test_one_that_starts_later_is_scheduled_and_not_shown_yet(client, workspace):
    a = await _make(client, starts_at=(utcnow() + timedelta(days=1)).isoformat())
    assert a["status"] == "scheduled"
    assert await _mine(client) == []


async def test_closing_it_hides_it_for_good_for_that_person_only(client, workspace, maker):
    a = await _make(client)
    assert (await client.post(f"/v1/me/announcements/{a['id']}/dismiss", headers=OWNER)).status_code == 200
    assert await _mine(client) == []
    other = await client.get("/v1/me/announcements", headers=OPS)  # someone else still sees it
    assert [x["id"] for x in other.json()] == [a["id"]]


async def test_the_team_can_end_it_early(client, workspace):
    a = await _make(client)
    r = await client.post(f"/v1/admin/marketing/announcements/{a['id']}/end", headers=OPS)
    assert r.json()["status"] == "ended"
    assert await _mine(client) == []


async def test_a_button_needs_its_words_and_where_it_goes(client, workspace):
    r = await client.post("/v1/admin/marketing/announcements", json={**BODY, "button_label": "See Kenya"}, headers=OPS)
    assert r.status_code == 422
    ok = await _make(client, button_label="See Kenya", button_url="https://www.coverfounder.com/press-distribution")
    assert ok["button_label"] == "See Kenya"


async def test_only_people_who_manage_marketing_can_make_one(client, workspace):
    assert (await client.post("/v1/admin/marketing/announcements", json=BODY, headers=OWNER)).status_code in {401, 403}
    assert (await client.get("/v1/admin/marketing/announcements", headers=OWNER)).status_code in {401, 403}


async def test_the_email_needs_the_server_switch_and_the_audience_to_be_confirmed(client, workspace, maker, mail_on):
    for i in range(3):
        await _person(maker, f"ann{i}@x.test", joined=2)
    aud = (await client.get("/v1/admin/marketing/announcements/audience", headers=OPS)).json()
    assert aud["reachable"] >= 3 and aud["email_engine"] == "on"
    wrong = await client.post("/v1/admin/marketing/announcements", json={**BODY, "send_email": True, "confirm_count": 1}, headers=OPS)
    assert wrong.status_code == 409 and "audience changed" in wrong.text
    ok = await client.post("/v1/admin/marketing/announcements", json={**BODY, "send_email": True, "confirm_count": aud["reachable"]}, headers=OPS)
    assert ok.status_code == 201, ok.text
    mail = ok.json()["email"]
    assert mail["status"] == "scheduled" and mail["audience"] == aud["reachable"]


async def test_with_marketing_email_off_asking_for_the_email_is_refused_not_ignored(client, workspace, monkeypatch):
    monkeypatch.setattr(get_settings(), "marketing_email", "off")
    r = await client.post("/v1/admin/marketing/announcements", json={**BODY, "send_email": True, "confirm_count": 1}, headers=OPS)
    assert r.status_code == 409 and "switched off" in r.text
    assert (await client.get("/v1/admin/marketing/announcements", headers=OPS)).json()["total"] == 0  # nothing half-made


async def test_the_email_goes_to_customers_but_never_to_anyone_who_unsubscribed(client, workspace, maker, mail_on):
    mine = await _person(maker, "keeps@x.test", joined=2)
    out = await _person(maker, "left@x.test", joined=2)
    async with maker() as db:
        db.add(MarketingPref(user_id=out, token="tok-left", opted_out_at=utcnow(), source="link"))
        await db.commit()
    aud = (await client.get("/v1/admin/marketing/announcements/audience", headers=OPS)).json()["reachable"]
    a = await _make(client, send_email=True, confirm_count=aud)
    for _ in range(3):
        await mcamp.deliver_due()
    to = [m["to"] for m in registry.get_email().sent]
    assert "keeps@x.test" in to and "left@x.test" not in to
    assert mine and out
    got = (await client.get("/v1/admin/marketing/announcements", headers=OPS)).json()["items"][0]
    assert got["id"] == a["id"] and got["email"]["status"] in {"sending", "sent"}


async def test_closing_an_announcement_is_remembered_with_the_users_other_data_intact(client, workspace, maker):
    a = await _make(client)
    await client.put("/v1/me/tours/welcome", json={"step": 2}, headers=OWNER)
    await client.post(f"/v1/me/announcements/{a['id']}/dismiss", headers=OWNER)
    async with maker() as db:
        u = (await db.execute(select(User).where(User.email == "owner@acme.test"))).scalars().first()
        assert u.onboarding["tours"]["welcome"]["step"] == 2 and a["id"] in u.onboarding["announcements_seen"]


async def test_an_app_only_announcement_can_be_emailed_later_once(client, workspace, maker, mail_on):
    await _person(maker, "later@x.test", joined=2)
    a = await _make(client)  # in the app only
    assert a["email"] is None
    aud = (await client.get("/v1/admin/marketing/announcements/audience", headers=OPS)).json()["reachable"]
    wrong = await client.post(f"/v1/admin/marketing/announcements/{a['id']}/email", json={"confirm_count": aud + 5}, headers=OPS)
    assert wrong.status_code == 409
    ok = await client.post(f"/v1/admin/marketing/announcements/{a['id']}/email", json={"confirm_count": aud}, headers=OPS)
    assert ok.status_code == 200 and ok.json()["email"]["status"] == "scheduled" and ok.json()["email"]["audience"] == aud
    again = await client.post(f"/v1/admin/marketing/announcements/{a['id']}/email", json={"confirm_count": aud}, headers=OPS)
    assert again.status_code == 409 and "already been emailed" in again.text  # never twice


async def test_an_ended_announcement_cannot_be_emailed_and_neither_can_one_while_email_is_off(client, workspace, monkeypatch):
    a = await _make(client)
    monkeypatch.setattr(get_settings(), "marketing_email", "off")
    off = await client.post(f"/v1/admin/marketing/announcements/{a['id']}/email", json={"confirm_count": 1}, headers=OPS)
    assert off.status_code == 409 and "switched off" in off.text
    await client.post(f"/v1/admin/marketing/announcements/{a['id']}/end", headers=OPS)
    monkeypatch.setattr(get_settings(), "marketing_email", "on")
    late = await client.post(f"/v1/admin/marketing/announcements/{a['id']}/email", json={"confirm_count": 1}, headers=OPS)
    assert late.status_code == 409 and "ended" in late.text
