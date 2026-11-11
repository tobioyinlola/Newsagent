"""Marketing copy: merge tags are checked when saved, every edit is a new version, and a test goes to the operator only."""

import pytest
from sqlalchemy import select

from app.integrations import registry
from app.models import MarketingSend, Project, User
from app.services import marketing
from app.services import marketing_copy as mc
from tests.conftest import OPS, OWNER

COPY = {
    "name": "Day 3 nudge",
    "category": "activation",
    "subject": "{{first_name|there}}, make your first video",
    "preheader": "It takes about 20 minutes.",
    "body": "Hi {{first_name|there}},\n\n{{company}} has {{credits_left}} credits waiting.",
    "button_label": "Make my video",
    "button_url": "/dashboard",
}


async def _post(client, **over):
    return await client.post("/v1/admin/marketing/copies", json={**COPY, **over}, headers=OPS)


async def test_save_then_every_edit_is_a_new_version_and_old_ones_stay(client, workspace):
    r = await _post(client)
    assert r.status_code == 201 and r.json()["current_version"] == 1
    cid = r.json()["id"]
    r2 = await client.put(f"/v1/admin/marketing/copies/{cid}", json={**COPY, "subject": "Still there?"}, headers=OPS)
    assert r2.status_code == 200 and r2.json()["current_version"] == 2
    got = (await client.get(f"/v1/admin/marketing/copies/{cid}", headers=OPS)).json()
    assert [v["version"] for v in got["versions"]] == [2, 1]
    assert got["versions"][1]["subject"].startswith("{{first_name|there}}")  # version 1 is untouched
    assert got["current"]["subject"] == "Still there?"
    assert [c["id"] for c in (await client.get("/v1/admin/marketing/copies", headers=OPS)).json()["items"]] == [cid]


@pytest.mark.parametrize(
    "over,message",
    [
        ({"body": "Hi {{nickname}}"}, "isn't a tag we know"),
        ({"body": "Hi {{first_name}}"}, "write a fallback"),
        ({"subject": "Hey {{first_name|}}"}, "write a fallback"),
        ({"body": "Hi {{company"}, "stray"),
        ({"subject": "Two\nlines"}, "one line"),
        ({"button_url": "javascript:alert(1)"}, "must start with https://"),
        ({"button_url": "//evil.example"}, "must start with https://"),
        ({"button_url": "http://plain.example"}, "must start with https://"),
        ({"button_url": "/x/{{company}}"}, "can't contain tags"),
        ({"button_label": ""}, "both its text and its link"),
        ({"category": "spam"}, "category"),
    ],
)
async def test_bad_copy_is_refused_in_plain_words(client, workspace, over, message):
    r = await _post(client, **over)
    assert r.status_code == 422 and message in r.json()["detail"], r.text


async def test_preview_fills_tags_and_uses_the_fallback_when_there_is_no_value(client, workspace):
    r = (await client.post("/v1/admin/marketing/copies/preview", json=COPY, headers=OPS)).json()
    assert r["subject"] == "Ada, make your first video"
    assert "Acme Foods has 4 credits" in r["text"] and "Make my video" in r["html"]
    assert (
        "It takes about 20 minutes." in r["html"] and "display:none" in r["html"]
    )  # the preview line is hidden in the body
    assert "{{" not in r["html"] + r["text"]
    assert mc.fill("Hi {{first_name|there}}", {"first_name": ""}) == "Hi there"
    assert mc.fill("Hi {{ first_name | friend }}", {}) == "Hi friend"


async def test_real_values_use_the_founder_name_and_company(maker, workspace):
    async with maker() as s:
        u = (await s.execute(select(User).where(User.email == "owner@acme.test"))).scalar_one()
        assert (await mc.values_for(s, u))["first_name"] == ""  # nobody is named yet: the fallback will be used
        s.add(Project(workspace_id=u.workspace_id, founder_name="Bola Ade Okoye"))
        await s.commit()
        v = await mc.values_for(s, u)
    assert (
        v["first_name"] == "Bola"
        and v["company"] == "Acme"
        and v["videos_started"] == "1"
        and v["credits_left"] == "10"
    )


async def test_test_email_goes_to_the_signed_in_operator_only_and_works_with_the_engine_off(client, maker, workspace):
    r = await client.post("/v1/admin/marketing/copies/test", json=COPY, headers=OPS)
    assert r.status_code == 200 and r.json()["sent_to"] == "ops@example.com"
    (m,) = registry.get_email().sent
    assert m["to"] == "ops@example.com" and m["subject"].startswith("[Test] Ada,")
    async with maker() as s:
        assert [x.status for x in (await s.execute(select(MarketingSend))).scalars()] == ["test"]
        # a test never uses up the person's one-email-in-two-days allowance
        ops = (await s.execute(select(User).where(User.email == "ops@example.com"))).scalar_one()
        assert await marketing._skip_reason(s, ops, marketing.MarketingConfig(), marketing.utcnow()) == ""


async def test_a_failing_mail_provider_gives_a_plain_error(client, workspace, monkeypatch):
    async def boom(*a, **k):
        raise RuntimeError("down")

    monkeypatch.setattr(registry.get_email(), "send", boom)
    r = await client.post("/v1/admin/marketing/copies/test", json=COPY, headers=OPS)
    assert r.status_code == 502 and "couldn't be sent" in r.json()["detail"]


async def test_archive_and_permissions(client, workspace):
    cid = (await _post(client)).json()["id"]
    assert (await client.post("/v1/admin/marketing/copies", json=COPY, headers=OWNER)).status_code in (401, 403)
    assert (await client.post("/v1/admin/marketing/copies/test", json=COPY, headers=OWNER)).status_code in (401, 403)
    assert (await client.delete(f"/v1/admin/marketing/copies/{cid}", headers=OPS)).status_code == 204
    assert (await client.get(f"/v1/admin/marketing/copies/{cid}", headers=OPS)).status_code == 404
    assert (await client.get("/v1/admin/marketing/copy-options", headers=OPS)).json()["tags"][0][
        "needs_fallback"
    ] is True
