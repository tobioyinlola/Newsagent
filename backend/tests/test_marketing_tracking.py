# ruff: noqa: F811
"""Open and click tracking: what goes into the email, what the public links do, and that they can't be turned into a redirector."""

import re

import pytest
from sqlalchemy import select

from app.config import get_settings
from app.integrations import registry
from app.models import MarketingSend, User
from app.services import marketing
from app.services import marketing_campaigns as mcamp
from app.services import marketing_workflows as wfs
from tests.conftest import OPS
from tests.test_marketing_segments import _person

COPY = {
    "name": "Nudge",
    "category": "activation",
    "subject": "Make a video",
    "preheader": "",
    "body": "Hello {{company}}",
    "button_label": "Go",
    "button_url": "https://example.com/start?x=1",
}
NG = {"match": "all", "conditions": [{"field": "country", "op": "in", "value": ["Nigeria"]}]}


@pytest.fixture
def on(monkeypatch):
    monkeypatch.setattr(get_settings(), "marketing_email", "on")


async def _owner(maker) -> User:
    async with maker() as s:
        return (await s.execute(select(User).where(User.email == "owner@acme.test"))).scalar_one()


async def _send(maker, **kw):
    u = await _owner(maker)
    async with maker() as s:
        out = await marketing.send(
            s, await s.get(User, u.id), "Hi", "Body", button=("Go", "https://example.com/start?x=1"), **kw
        )
        await s.commit()
    return out


def _mail():
    return [m for m in registry.get_email().sent if m["to"] == "owner@acme.test"]


async def _row(maker) -> MarketingSend:
    async with maker() as s:
        return (await s.execute(select(MarketingSend))).scalar_one()


async def test_an_email_carries_a_picture_and_a_button_that_goes_through_our_site(maker, workspace, on):
    assert await _send(maker) == "sent"
    (m,) = _mail()
    row = await _row(maker)
    assert row.track_token and row.click_url == "https://example.com/start?x=1"
    assert f"/v1/m/o/{row.track_token}.gif" in m["html"] and 'width="1" height="1"' in m["html"]
    assert f"/v1/m/c/{row.track_token}" in m["html"] and f"/v1/m/c/{row.track_token}" in m["text"]
    assert "example.com/start" not in m["html"] + m["text"]  # the real address is only kept on our side
    assert "/v1/unsubscribe/" in m["headers"]["List-Unsubscribe"] and "/v1/m/" not in m["headers"]["List-Unsubscribe"]
    assert (
        "/v1/m/" not in m["html"].split("Unsubscribe")[0].rsplit('href="', 1)[-1]
    )  # the unsubscribe link itself is not tracked


async def test_the_picture_counts_opens_and_always_answers_the_same(client, maker, workspace, on):
    await _send(maker)
    t = (await _row(maker)).track_token
    for _ in range(2):
        r = await client.get(f"/v1/m/o/{t}.gif")
        assert r.status_code == 200 and r.headers["content-type"] == "image/gif" and r.content.startswith(b"GIF89a")
        assert "no-store" in r.headers["cache-control"]
    row = await _row(maker)
    assert row.open_count == 2 and row.opened_at is not None and row.click_count == 0
    unknown = await client.get("/v1/m/o/not-a-token.gif")
    assert unknown.status_code == 200 and unknown.content.startswith(b"GIF89a")  # a guess learns nothing


async def test_the_button_counts_a_click_and_goes_to_the_stored_address_only(client, maker, workspace, on):
    await _send(maker)
    t = (await _row(maker)).track_token
    r = await client.get(f"/v1/m/c/{t}?url=https://evil.example&to=//evil.example", follow_redirects=False)
    assert r.status_code == 302 and r.headers["location"] == "https://example.com/start?x=1"
    row = await _row(maker)
    assert row.click_count == 1 and row.clicked_at is not None and row.opened_at is not None  # a click implies an open
    unknown = await client.get("/v1/m/c/not-a-token", follow_redirects=False)
    assert unknown.status_code == 302 and unknown.headers["location"] == get_settings().app_base_url


async def test_a_site_page_button_is_tracked_too(maker, workspace, on):
    u = await _owner(maker)
    async with maker() as s:
        await marketing.send(
            s, await s.get(User, u.id), "Hi", "Body", button=("Go", get_settings().app_base_url + "/dashboard")
        )
        await s.commit()
    assert (await _row(maker)).click_url.endswith("/dashboard")


async def test_with_tracking_off_nothing_is_added_or_stored(client, maker, workspace, on):
    await client.put("/v1/admin/marketing/config", json={"track": False}, headers=OPS)
    await _send(maker)
    (m,) = _mail()
    row = await _row(maker)
    assert row.track_token is None and row.click_url is None
    assert "/v1/m/" not in m["html"] + m["text"] and "https://example.com/start?x=1" in m["html"]


async def test_a_test_email_is_never_tracked(client, workspace):
    r = await client.post("/v1/admin/marketing/copies/test", json=COPY, headers=OPS)
    assert r.status_code == 200
    (m,) = [x for x in registry.get_email().sent if x["to"] == "ops@example.com"]
    assert "/v1/m/" not in m["html"]


async def test_campaign_numbers_count_people_not_hits(client, maker, workspace, on):
    for i in range(3):
        await _person(maker, f"p{i}@x.test", joined=2, country="Nigeria")
    seg = (await client.post("/v1/admin/marketing/segments", json={"name": "NG", "rules": NG}, headers=OPS)).json()[
        "id"
    ]
    copy = (await client.post("/v1/admin/marketing/copies", json=COPY, headers=OPS)).json()["id"]
    cid = (
        await client.post(
            "/v1/admin/marketing/campaigns", json={"name": "C", "segment_id": seg, "copy_id": copy}, headers=OPS
        )
    ).json()["id"]
    await client.post(f"/v1/admin/marketing/campaigns/{cid}/schedule", json={"confirm_count": 3}, headers=OPS)
    await mcamp.deliver_due()
    async with maker() as s:
        tokens = [r.track_token for r in (await s.execute(select(MarketingSend).order_by(MarketingSend.id))).scalars()]
    for _ in range(3):  # the first person opens it three times; it still counts as one person
        await client.get(f"/v1/m/o/{tokens[0]}.gif")
    await client.get(f"/v1/m/c/{tokens[1]}", follow_redirects=False)  # the second only clicks
    k = (await client.get(f"/v1/admin/marketing/campaigns/{cid}", headers=OPS)).json()["counts"]
    assert (k["sent"], k["opened"], k["clicked"]) == (3, 2, 1)


async def test_workflow_numbers_are_per_email(client, maker, workspace, on):
    await _person(maker, "a@x.test", joined=2, country="Nigeria")
    await client.put("/v1/admin/marketing/config", json={"min_gap_days": 0}, headers=OPS)
    seg = (await client.post("/v1/admin/marketing/segments", json={"name": "NG", "rules": NG}, headers=OPS)).json()[
        "id"
    ]
    copy = (await client.post("/v1/admin/marketing/copies", json=COPY, headers=OPS)).json()["id"]
    w = await client.post(
        "/v1/admin/marketing/workflows",
        json={
            "name": "W",
            "trigger_segment_id": seg,
            "steps": [{"type": "email", "copy_id": copy}],
            "hours": {"enabled": False, "start": 9, "end": 18},
        },
        headers=OPS,
    )
    wid = w.json()["id"]
    await client.post(
        f"/v1/admin/marketing/workflows/{wid}/activate",
        json={"include_existing": True, "confirm_count": 1},
        headers=OPS,
    )
    await wfs.tick(10)
    m = [x for x in registry.get_email().sent if x["to"] == "a@x.test"][0]
    token = re.search(r"/v1/m/c/([A-Za-z0-9_-]+)", m["text"]).group(1)
    await client.get(f"/v1/m/c/{token}", follow_redirects=False)
    st = (await client.get(f"/v1/admin/marketing/workflows/{wid}", headers=OPS)).json()["stats"]
    assert st["sent_by_step"] == {"0": 1} and st["opened_by_step"] == {"0": 1} and st["clicked_by_step"] == {"0": 1}
