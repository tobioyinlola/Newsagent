# ruff: noqa: F811
"""A/B test of a campaign's subject line: who gets which, how the winner is chosen, and the checks around it."""

from datetime import UTC, datetime, timedelta

import pytest
from sqlalchemy import select

from app.config import get_settings
from app.integrations import registry
from app.models import MarketingRecipient, MarketingSend, User
from app.services import marketing_campaigns as mcamp
from tests.conftest import OPS
from tests.test_marketing_segments import _person

COPY = {
    "name": "Nudge",
    "category": "activation",
    "subject": "Subject A",
    "preheader": "",
    "body": "Hello {{company}}",
    "button_label": "Go",
    "button_url": "https://example.com/go",
}
NG = {"match": "all", "conditions": [{"field": "country", "op": "in", "value": ["Nigeria"]}]}


@pytest.fixture
def on(monkeypatch):
    monkeypatch.setattr(get_settings(), "marketing_email", "on")


async def _setup(client, maker, monkeypatch, n, **test):
    ids = []
    for i in range(n):
        ids.append(await _person(maker, f"p{i:02d}@x.test", joined=2, country="Nigeria"))
    order = {uid: i * 100 // n for i, uid in enumerate(sorted(ids))}  # an even, known spread instead of luck
    monkeypatch.setattr(mcamp, "bucket", lambda cid, uid: order[uid])
    await client.put("/v1/admin/marketing/config", json={"per_minute": 600, "min_gap_days": 2}, headers=OPS)
    seg = (await client.post("/v1/admin/marketing/segments", json={"name": "NG", "rules": NG}, headers=OPS)).json()[
        "id"
    ]
    copy = (await client.post("/v1/admin/marketing/copies", json=COPY, headers=OPS)).json()["id"]
    body = {"name": "Test", "segment_id": seg, "copy_id": copy, "subject_b": "Subject B", **test}
    r = await client.post("/v1/admin/marketing/campaigns", json=body, headers=OPS)
    assert r.status_code == 201, r.text
    return r.json()["id"], body


async def _go(client, cid, n):
    return await client.post(f"/v1/admin/marketing/campaigns/{cid}/schedule", json={"confirm_count": n}, headers=OPS)


def _subjects():
    return {m["to"]: m["subject"] for m in registry.get_email().sent if m["to"].endswith("@x.test")}


async def _variants(maker, cid) -> dict[str, str]:
    async with maker() as s:
        rows = (
            await s.execute(
                select(MarketingRecipient, User)
                .join(User, User.id == MarketingRecipient.user_id)
                .where(MarketingRecipient.campaign_id == cid)
            )
        ).all()
        return {u.email: r.variant for r, u in rows}


async def _open(client, maker, cid, variant):
    async with maker() as s:
        rows = (
            (
                await s.execute(
                    select(MarketingSend.track_token)
                    .join(
                        MarketingRecipient,
                        (MarketingRecipient.campaign_id == MarketingSend.ref)
                        & (MarketingRecipient.user_id == MarketingSend.user_id),
                    )
                    .where(MarketingRecipient.campaign_id == cid, MarketingRecipient.variant == variant)
                )
            )
            .scalars()
            .all()
        )
    for t in rows:
        await client.get(f"/v1/m/o/{t}.gif")
    return len(rows)


async def test_split_sends_each_person_their_own_subject_and_reports_both(client, maker, workspace, on, monkeypatch):
    cid, _ = await _setup(client, maker, monkeypatch, 24)
    assert (await _go(client, cid, 24)).status_code == 200
    await mcamp.deliver_due()
    v, subj = await _variants(maker, cid), _subjects()
    assert sorted(set(v.values())) == ["A", "B"] and len(subj) == 24
    assert all(subj[e] == ("Subject A" if x == "A" else "Subject B") for e, x in v.items())
    res = (await client.get(f"/v1/admin/marketing/campaigns/{cid}", headers=OPS)).json()
    assert res["counts"]["variants"] == {
        "A": {"sent": 12, "opened": 0, "clicked": 0},
        "B": {"sent": 12, "opened": 0, "clicked": 0},
    }
    assert res["email_b"]["subject"] == "Subject B" and res["test"]["mode"] == "split"
    n = await _open(client, maker, cid, "B")
    res = (await client.get(f"/v1/admin/marketing/campaigns/{cid}", headers=OPS)).json()
    assert n == 12 and res["counts"]["variants"]["B"]["opened"] == 12 and res["counts"]["variants"]["A"]["opened"] == 0


async def test_winner_mode_tests_a_few_then_sends_the_better_subject_to_everyone_else(
    client, maker, workspace, on, monkeypatch
):
    cid, _ = await _setup(client, maker, monkeypatch, 30, ab_mode="winner", test_percent=20, wait_hours=4)
    assert (await _go(client, cid, 30)).status_code == 200
    await mcamp.deliver_due()
    assert len(_subjects()) == 6  # 3 got A, 3 got B; the other 24 are waiting
    k = (await client.get(f"/v1/admin/marketing/campaigns/{cid}", headers=OPS)).json()
    assert k["status"] == "sending" and k["counts"]["held"] == 24 and k["counts"]["variants"]["A"]["sent"] == 3
    await mcamp.deliver_due()  # the test group is done: the clock for the winner starts
    soon = datetime.now(UTC) + timedelta(hours=1)
    await mcamp.deliver_due(soon)
    assert len(_subjects()) == 6  # too early
    await _open(client, maker, cid, "B")  # everyone who got B opened it; nobody who got A did
    await mcamp.deliver_due(datetime.now(UTC) + timedelta(hours=5))
    assert len(_subjects()) == 30
    waiting = [e for e, x in (await _variants(maker, cid)).items() if x in {"a", "b"}]
    assert len(waiting) == 24 and {_subjects()[e] for e in waiting} == {"Subject B"}
    done = (await client.get(f"/v1/admin/marketing/campaigns/{cid}", headers=OPS)).json()
    assert done["status"] == "sent" and done["test"]["winner"] == "B"
    assert (
        done["counts"]["variants"]["A"]["sent"] == 3 and done["counts"]["variants"]["B"]["sent"] == 3
    )  # the test results stay as they were


async def test_no_difference_keeps_the_original_and_clicks_can_decide_instead(
    client, maker, workspace, on, monkeypatch
):
    cid, _ = await _setup(client, maker, monkeypatch, 30, ab_mode="winner", test_percent=20)
    await _go(client, cid, 30)
    for _ in range(2):
        await mcamp.deliver_due()
    await mcamp.deliver_due(datetime.now(UTC) + timedelta(hours=5))
    assert (await client.get(f"/v1/admin/marketing/campaigns/{cid}", headers=OPS)).json()["test"]["winner"] == "A"
    assert (
        mcamp.pick_winner(
            {"A": {"sent": 10, "opened": 9, "clicked": 1}, "B": {"sent": 10, "opened": 2, "clicked": 4}}, "clicks"
        )
        == "B"
    )
    assert (
        mcamp.pick_winner(
            {"A": {"sent": 10, "opened": 9, "clicked": 1}, "B": {"sent": 10, "opened": 2, "clicked": 4}}, "opens"
        )
        == "A"
    )
    assert mcamp.pick_winner({}, "opens") == "A"
    assert (
        mcamp.pick_winner(
            {"A": {"sent": 50, "opened": 10, "clicked": 0}, "B": {"sent": 5, "opened": 2, "clicked": 0}}, "opens"
        )
        == "B"
    )  # rates, not counts


async def test_cancelling_during_the_wait_stops_those_who_were_held(client, maker, workspace, on, monkeypatch):
    cid, _ = await _setup(client, maker, monkeypatch, 30, ab_mode="winner")
    await _go(client, cid, 30)
    await mcamp.deliver_due()
    c = (await client.post(f"/v1/admin/marketing/campaigns/{cid}/cancel", headers=OPS)).json()
    assert (
        c["counts"]["sent"] == 6 and c["counts"]["skipped_by_reason"] == {"cancelled": 24} and c["counts"]["held"] == 0
    )
    await mcamp.deliver_due(datetime.now(UTC) + timedelta(hours=9))
    assert len(_subjects()) == 6


async def test_a_campaign_without_a_test_is_unchanged(client, maker, workspace, on, monkeypatch):
    cid, body = await _setup(client, maker, monkeypatch, 6)
    r = await client.put(f"/v1/admin/marketing/campaigns/{cid}", json={**body, "subject_b": ""}, headers=OPS)
    assert r.json()["test"]["subject_b"] is None
    await _go(client, cid, 6)
    await mcamp.deliver_due()
    assert set(_subjects().values()) == {"Subject A"} and set((await _variants(maker, cid)).values()) == {""}
    assert (await client.get(f"/v1/admin/marketing/campaigns/{cid}", headers=OPS)).json()["counts"]["variants"] == {}


@pytest.mark.parametrize(
    "test,message",
    [
        ({"subject_b": "Hi {{nickname}}"}, "isn't a tag we know"),
        ({"subject_b": "Hi {{first_name}}"}, "write a fallback"),
        ({"subject_b": "Two\nlines"}, "one line"),
        ({"ab_mode": "bogus"}, ""),
        ({"test_percent": 90}, ""),
    ],
)
async def test_bad_test_settings_are_refused(client, maker, workspace, monkeypatch, test, message):
    seg = (await client.post("/v1/admin/marketing/segments", json={"name": "NG", "rules": NG}, headers=OPS)).json()[
        "id"
    ]
    copy = (await client.post("/v1/admin/marketing/copies", json=COPY, headers=OPS)).json()["id"]
    r = await client.post(
        "/v1/admin/marketing/campaigns",
        json={"name": "T", "segment_id": seg, "copy_id": copy, "subject_b": "B", **test},
        headers=OPS,
    )
    assert r.status_code == 422 and message in r.text


async def test_scheduling_checks_the_test(client, maker, workspace, on, monkeypatch):
    cid, body = await _setup(client, maker, monkeypatch, 24)
    same = await client.put(
        f"/v1/admin/marketing/campaigns/{cid}", json={**body, "subject_b": " Subject A "}, headers=OPS
    )
    assert same.status_code == 200
    r = await _go(client, cid, 24)
    assert r.status_code == 422 and "the same" in r.json()["detail"]
    await client.put(f"/v1/admin/marketing/campaigns/{cid}", json={**body, "ab_mode": "winner"}, headers=OPS)
    small = await _go(client, cid, 24)
    assert small.status_code == 200  # 24 people is enough for a winner test


async def test_a_winner_test_needs_tracking_and_enough_people(client, maker, workspace, on, monkeypatch):
    cid, _ = await _setup(client, maker, monkeypatch, 10, ab_mode="winner")
    r = await _go(client, cid, 10)
    assert r.status_code == 422 and "at least 20" in r.json()["detail"]
    await client.put("/v1/admin/marketing/config", json={"track": False}, headers=OPS)
    r = await _go(client, cid, 10)
    assert r.status_code == 409 and "Count opens and clicks" in r.json()["detail"]
