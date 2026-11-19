# ruff: noqa: F811
"""Outreach to every outlet by default, several contacts per outlet, and the 'needs a contact' flow for paid requests."""

import pytest
from sqlalchemy import select

from app.config import get_settings
from app.integrations import registry
from app.models import DistributionMail, DistributionPlacement, OutreachThread
from tests.conftest import OPS
from tests.test_distribution import distribution_data  # noqa: F401  (a request with outlets 1 and 2 ready to submit)
from tests.test_outreach import _sent, _submit, engine  # noqa: F401

EMPIRE = "ada@empire.example.com"
TECH = "bayo@techpoint.example.com"


async def _import(client, text, automatic=False):
    r = await client.post("/v1/admin/outreach/contacts/apply", json={"text": text, "enable_automatic": automatic}, headers=OPS)
    assert r.status_code == 200, r.text
    return r.json()


async def _threads(maker):
    async with maker() as db:
        return {t.outlet_name: t for t in (await db.execute(select(OutreachThread))).scalars()}


async def _states(maker):
    async with maker() as db:
        return {p.data["name"]: p.outreach_state for p in (await db.execute(select(DistributionPlacement))).scalars()}


async def _config(client, **changes):
    cfg = (await client.get("/v1/admin/outreach/config", headers=OPS)).json()["config"]
    assert (await client.put("/v1/admin/outreach/config", json={**cfg, **changes}, headers=OPS)).status_code == 200


async def _outlet(client, name):
    cfg = (await client.get("/v1/admin/distribution/config", headers=OPS)).json()
    return next(o for o in cfg["outlets"] if o["name"] == name)


# ---------- several contacts for one outlet ----------
async def test_one_or_several_emails_in_the_import_the_first_is_main_the_rest_are_copied(client, workspace):
    text = 'outlet,contact_name,contact_email\nEmpire Magazine Africa,Ada,"ada@empire.example.com; news@empire.example.com, desk@empire.example.com"\nTribune,Chi,chi@tribune.example.com\n'
    prev = (await client.post("/v1/admin/outreach/contacts/preview", json={"text": text}, headers=OPS)).json()
    assert [r["status"] for r in prev["rows"]] == ["ok", "ok"]
    assert prev["rows"][0]["cc_emails"] == ["news@empire.example.com", "desk@empire.example.com"] and prev["rows"][1]["cc_emails"] == []
    await _import(client, text)
    empire = await _outlet(client, "Empire Magazine Africa")
    assert empire["contact_email"] == EMPIRE and empire["cc_emails"] == ["news@empire.example.com", "desk@empire.example.com"]
    again = (await client.post("/v1/admin/outreach/contacts/preview", json={"text": text}, headers=OPS)).json()
    assert [r["status"] for r in again["rows"]] == ["unchanged", "unchanged"]


async def test_too_many_or_badly_written_emails_are_refused_before_saving(client, workspace):
    many = ";".join(f"p{i}@empire.example.com" for i in range(7))  # a main contact and six more is one too many
    for bad in (many, "ada@empire.example.com; not-an-email"):
        prev = (await client.post("/v1/admin/outreach/contacts/preview", json={"text": f'outlet,contact_email\nTribune,"{bad}"\n'}, headers=OPS)).json()
        assert prev["rows"][0]["status"] == "bad_email"
    assert (await client.post("/v1/admin/outreach/contacts/apply", json={"text": f'outlet,contact_email\nTribune,"{many}"\n'}, headers=OPS)).json() == {"applied": 0}


async def test_the_outlet_form_rejects_other_contacts_without_a_main_one_and_tidies_repeats(client, workspace):
    body = {"credits": "10", "contact_email": None, "cc_emails": ["a@example.com"]}
    assert (await client.put("/v1/admin/distribution/outlets/1", json=body, headers=OPS)).status_code == 422
    ok = await client.put("/v1/admin/distribution/outlets/1", json={"credits": "10", "contact_email": EMPIRE, "cc_emails": ["B@example.com", "b@example.com", EMPIRE]}, headers=OPS)
    assert ok.status_code == 200 and ok.json()["cc_emails"] == ["B@example.com"]  # no repeats, and the main contact is not copied on their own email


async def test_everyone_is_on_one_email_and_the_others_are_copied_on_it_and_on_every_reply(client, distribution_data, engine, maker):
    await _import(client, f'outlet,contact_name,contact_email\nEmpire Magazine Africa,Ada,"{EMPIRE}; news@empire.example.com"\n')
    await _submit(client, distribution_data)
    mails = _sent(EMPIRE)
    assert len(mails) == 1 and mails[0]["cc"] == ["news@empire.example.com"]  # one email to the outlet, not one each
    assert _sent("news@empire.example.com") == []
    t = (await _threads(maker))["Empire Magazine Africa"]
    assert t.cc_emails == ["news@empire.example.com"]
    r = await client.post(f"/v1/admin/outreach/threads/{t.id}/reply", json={"body": "Thanks, here is more.", "send_now": True}, headers=OPS)
    assert r.status_code == 200, r.text
    assert _sent(EMPIRE)[-1]["cc"] == ["news@empire.example.com"]


async def test_the_first_email_carries_the_whole_story_to_publish_not_just_links(client, distribution_data, engine, maker):
    await _import(client, f"outlet,contact_name,contact_email\nEmpire Magazine Africa,Ada,{EMPIRE}\n")
    await _submit(client, distribution_data)
    text = _sent(EMPIRE)[0]["text"]
    assert "ready to publish" in text and "Our edited announcement." in text  # the full announcement, in the email itself
    assert "{story}" not in text and "{assets}" not in text


async def test_story_is_a_placeholder_templates_can_use_and_the_preview_shows_it(client, workspace):
    cfg = (await client.get("/v1/admin/outreach/config", headers=OPS)).json()
    assert "story" in cfg["variables"]
    r = await client.post("/v1/admin/outreach/preview", json={"subject": "Hi", "body": "Please publish:\n{story}"}, headers=OPS)
    assert r.status_code == 200 and "Acme opens its first store in Lagos" in r.json()["body"] and "{story}" not in r.json()["body"]


# ---------- the default: every outlet, unless it opted out ----------
async def test_automatic_outreach_is_on_for_every_outlet_that_has_a_contact(client, distribution_data, engine, maker):
    await _import(client, "outlet,contact_name,contact_email\nEmpire Magazine Africa,Ada,ada@empire.example.com\n", automatic=False)
    assert (await _outlet(client, "Empire Magazine Africa"))["direct_access"] is False  # nobody switched this outlet on by hand
    await _submit(client, distribution_data)
    assert len(_sent(EMPIRE)) == 1 and "Empire Magazine Africa" in await _threads(maker)
    assert (await _states(maker))["Empire Magazine Africa"] == "started"


async def test_an_outlet_can_opt_out_and_is_then_left_alone_without_any_warning(client, distribution_data, engine, maker):
    await _import(client, "outlet,contact_name,contact_email\nEmpire Magazine Africa,Ada,ada@empire.example.com\n")
    e = await _outlet(client, "Empire Magazine Africa")
    keep = {k: e[k] for k in ("credits", "contact_name", "contact_email", "accepts_logo", "accepts_images", "logo_credits", "picture_credits")}
    assert (await client.put(f"/v1/admin/distribution/outlets/{e['id']}", json={**keep, "direct_access": True, "skip_outreach": True}, headers=OPS)).status_code == 200
    await client.put("/v1/admin/distribution/config", json={"team_emails": ["team@example.com"]}, headers=OPS)
    await _submit(client, distribution_data)
    assert _sent(EMPIRE) == [] and "Empire Magazine Africa" not in await _threads(maker)
    assert (await _states(maker))["Empire Magazine Africa"] == ""
    assert not [m for m in registry.get_email().sent if m["to"] == "team@example.com" and "Contact details needed" in m["subject"] and "Empire" in m["text"]]


async def test_the_default_can_be_switched_off_and_an_outlet_switched_on_by_hand_is_still_contacted(client, distribution_data, engine, maker):
    await _import(client, "outlet,contact_name,contact_email\nEmpire Magazine Africa,Ada,ada@empire.example.com\nTechpoint Africa,Bayo,bayo@techpoint.example.com\n")
    tp = await _outlet(client, "Techpoint Africa")
    keep = {k: tp[k] for k in ("credits", "contact_name", "contact_email", "accepts_logo", "accepts_images", "logo_credits", "picture_credits")}
    await client.put(f"/v1/admin/distribution/outlets/{tp['id']}", json={**keep, "direct_access": True}, headers=OPS)
    await _config(client, auto_outreach=False)
    await _submit(client, distribution_data)
    assert _sent(EMPIRE) == [] and len(_sent(TECH)) == 1
    assert set(await _threads(maker)) == {"Techpoint Africa"}


async def test_with_outreach_switched_off_nothing_new_happens(client, distribution_data, maker, monkeypatch):
    monkeypatch.setattr(get_settings(), "outreach_ai", "off")
    await _import(client, "outlet,contact_name,contact_email\nEmpire Magazine Africa,Ada,ada@empire.example.com\nTechpoint Africa,Bayo,bayo@techpoint.example.com\n", automatic=False)
    await _submit(client, distribution_data)
    assert _sent(EMPIRE) == [] and await _threads(maker) == {}  # the original behaviour: only outlets switched on by hand get the one-way email
    assert set((await _states(maker)).values()) == {""}


# ---------- an outlet with no contact ----------
@pytest.fixture
async def waiting(client, distribution_data, engine, maker):
    """A paid request where neither outlet has a contact yet, with a team address to tell."""
    await client.put("/v1/admin/distribution/config", json={"team_emails": ["team@example.com"]}, headers=OPS)
    await _submit(client, distribution_data)


async def test_a_paid_request_with_no_contacts_flags_them_and_tells_the_team(client, waiting, maker):
    assert set((await _states(maker)).values()) == {"needs_contact"}
    assert await _threads(maker) == {} and _sent(EMPIRE) == []
    note = [m for m in registry.get_email().sent if m["to"] == "team@example.com" and "Contact details needed" in m["subject"]]
    assert len(note) == 1 and "Empire Magazine Africa" in note[0]["text"] and "Techpoint Africa" in note[0]["text"] and "/outreach" in note[0]["text"]
    todo = (await client.get("/v1/admin/outreach/needs-contact", headers=OPS)).json()
    assert {i["outlet_name"] for i in todo["needs_contact"]} == {"Empire Magazine Africa", "Techpoint Africa"}
    assert all(i["headline"] and i["request_id"] and i["state"] == "needs_contact" for i in todo["needs_contact"])
    cfg = (await client.get("/v1/admin/outreach/config", headers=OPS)).json()
    assert cfg["needs_contact"] == 2


async def test_adding_a_contact_starts_that_conversation_straight_away_and_saves_it_for_next_time(client, waiting, maker):
    todo = (await client.get("/v1/admin/outreach/needs-contact", headers=OPS)).json()["needs_contact"]
    empire = next(i for i in todo if i["outlet_name"] == "Empire Magazine Africa")
    r = await client.put(f"/v1/admin/outreach/needs-contact/{empire['placement_id']}", json={"contact_name": "Ada", "emails": [EMPIRE, "news@empire.example.com"]}, headers=OPS)
    assert r.status_code == 200 and r.json()["state"] == "started"
    sent = _sent(EMPIRE)
    assert len(sent) == 1 and sent[0]["cc"] == ["news@empire.example.com"]
    left = (await client.get("/v1/admin/outreach/needs-contact", headers=OPS)).json()["needs_contact"]
    assert [i["outlet_name"] for i in left] == ["Techpoint Africa"]
    saved = await _outlet(client, "Empire Magazine Africa")
    assert (saved["contact_email"], saved["cc_emails"]) == (EMPIRE, ["news@empire.example.com"])
    again = await client.put(f"/v1/admin/outreach/needs-contact/{empire['placement_id']}", json={"emails": [EMPIRE]}, headers=OPS)
    assert again.status_code == 404  # it is no longer waiting


async def test_importing_contacts_later_also_starts_the_waiting_conversations(client, waiting, maker):
    assert await _import(client, "outlet,contact_name,contact_email\nTechpoint Africa,Bayo,bayo@techpoint.example.com\n") == {"applied": 1}
    assert len(_sent(TECH)) == 1
    assert (await _states(maker)) == {"Empire Magazine Africa": "needs_contact", "Techpoint Africa": "started"}


async def test_the_background_tick_also_catches_up_when_a_contact_was_added_another_way(client, waiting, maker):
    from app.services import outreach

    e = await _outlet(client, "Empire Magazine Africa")
    await client.put(f"/v1/admin/distribution/outlets/{e['id']}", json={"credits": e["credits"], "contact_name": "Ada", "contact_email": EMPIRE}, headers=OPS)
    assert _sent(EMPIRE) == []  # saving an outlet does not write to anyone by itself
    await outreach.deliver_due()
    assert len(_sent(EMPIRE)) == 1  # the next tick does


async def test_an_outlet_switched_to_never_contact_while_waiting_is_dropped_from_the_list(client, waiting, maker):
    e = await _outlet(client, "Empire Magazine Africa")
    await client.put(f"/v1/admin/distribution/outlets/{e['id']}", json={"credits": e["credits"], "contact_name": "Ada", "contact_email": EMPIRE, "skip_outreach": True}, headers=OPS)
    from app.services import outreach

    await outreach.catch_up()
    assert (await _states(maker))["Empire Magazine Africa"] == "skipped" and _sent(EMPIRE) == []


async def test_only_people_who_manage_operations_can_add_contacts(client, waiting):
    from tests.conftest import OWNER

    todo = (await client.get("/v1/admin/outreach/needs-contact", headers=OPS)).json()["needs_contact"]
    url = f"/v1/admin/outreach/needs-contact/{todo[0]['placement_id']}"
    assert (await client.put(url, json={"emails": [EMPIRE]}, headers=OWNER)).status_code in {401, 403}
    assert (await client.get("/v1/admin/outreach/needs-contact", headers=OWNER)).status_code in {401, 403}
    assert (await client.put(url, json={"emails": []}, headers=OPS)).status_code == 422
    assert (await client.put(url, json={"emails": [f"p{i}@x.example.com" for i in range(7)]}, headers=OPS)).status_code == 422


async def test_the_team_hears_once_not_once_per_outlet_and_not_at_all_when_nobody_is_missing(client, distribution_data, engine, maker):
    await client.put("/v1/admin/distribution/config", json={"team_emails": ["team@example.com"]}, headers=OPS)
    await _import(client, "outlet,contact_name,contact_email\nEmpire Magazine Africa,Ada,ada@empire.example.com\nTechpoint Africa,Bayo,bayo@techpoint.example.com\n")
    await _submit(client, distribution_data)
    assert not [m for m in registry.get_email().sent if "Contact details needed" in m["subject"]]
    async with maker() as db:
        kinds = [m.kind for m in (await db.execute(select(DistributionMail))).scalars()]
    assert "team_needs_contact" not in kinds
