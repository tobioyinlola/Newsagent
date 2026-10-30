"""Audience measurement, tenant boundaries and non-additive publisher reports."""

import asyncio
from datetime import timedelta
from uuid import uuid4

import pytest
from sqlalchemy import select

from app.models import (
    Asset,
    AudienceDaily,
    AudienceEvent,
    DistributionMail,
    DistributionPlacement,
    DistributionRequest,
    Project,
    ScriptVersion,
    User,
    Workspace,
)
from app.models.base import utcnow
from app.services import analytics
from tests.conftest import OPS, OWNER


@pytest.fixture
async def story(workspace, maker):
    async with maker() as db:
        p = Project(workspace_id=workspace, state="final_ready", story_slug="analytics-story", published_at=utcnow())
        db.add(p)
        await db.flush()
        db.add(
            ScriptVersion(
                project_id=p.id, story={"headline": "Analytics launch", "sections": [{"text": "A real announcement."}]}
            )
        )
        db.add(Asset(project_id=p.id, type="render", format="16x9", storage_key="test/video.mp4"))
        request = DistributionRequest(
            workspace_id=workspace,
            created_by="owner@acme.test",
            paid_at=utcnow(),
            status="submitted",
            data={"project_id": p.id, "headline": "Analytics launch", "contact_email": "owner@acme.test"},
        )
        db.add(request)
        await db.flush()
        placement = DistributionPlacement(
            request_id=request.id,
            outlet_id="1",
            data={"name": "Empire Magazine Africa"},
            status="published",
            published_url="https://example.com/story",
            contact_email="editor@example.com",
        )
        db.add(placement)
        await db.commit()
        return p.id, placement.id


async def test_events_dedupe_complete_order_and_exclude_previews(client, story, maker):
    session = str(uuid4())
    url = "/v1/public/stories/analytics-story/events"

    async def send(kind, headers=None):
        r = await client.post(url, json={"kind": kind, "session_id": session}, headers=headers)
        assert r.status_code == 200, r.text
        return r.json()["recorded"]

    assert not await send("video_complete")
    assert not await send("story_visit", OWNER)
    assert not await send("story_visit", OPS)
    for headers in ({"DNT": "1"}, {"Sec-GPC": "1"}, {"User-Agent": "Googlebot"}):
        assert not await send("story_visit", headers)
    for kind in ("impression", "story_visit", "video_view", "video_complete"):
        assert await send(kind)
        assert not await send(kind)
    report = (await client.get("/v1/analytics", headers=OWNER)).json()
    assert report["platform"] == {
        "impressions": 1,
        "story_visits": 1,
        "share_visits": 0,
        "video_views": 1,
        "video_completions": 1,
    }
    assert len(report["series"]) == 30
    async with maker() as db:
        rows = (await db.execute(select(AudienceEvent))).scalars().all()
        assert len(rows) == 4 and all(len(r.session_hash) == 64 and session != r.session_hash for r in rows)
    assert (await client.post(url, json={"kind": "share_visit", "session_id": session})).status_code == 422
    assert (await client.post(url, json={"kind": "story_visit", "session_id": "invalid"})).status_code == 422


async def test_concurrent_measurements_are_atomic_and_scoped(client, story, maker):
    same = str(uuid4())

    async def hit(session):
        return await client.post(
            "/v1/public/stories/analytics-story/events", json={"kind": "story_visit", "session_id": session}
        )

    replies = await asyncio.gather(*(hit(same) for _ in range(8)))
    assert sum(r.json()["recorded"] for r in replies) == 1
    await asyncio.gather(*(hit(str(uuid4())) for _ in range(8)))
    async with maker() as db:
        ws = Workspace(name="Other")
        db.add(ws)
        await db.flush()
        db.add(User(email="other@example.com", workspace_id=ws.id))
        await db.commit()
    other = {"Authorization": "Bearer dev:other@example.com"}
    assert (await client.get("/v1/analytics", headers=other)).json()["platform"]["story_visits"] == 0
    assert (await client.get(f"/v1/analytics?project_id={story[0]}", headers=other)).status_code == 404
    assert (await client.get("/v1/admin/analytics", headers=OWNER)).status_code == 403
    assert (await client.get("/v1/admin/analytics", headers=OPS)).json()["platform"]["story_visits"] == 9
    assert (await client.get("/v1/analytics?start=2020-01-01&end=2025-01-01", headers=OWNER)).status_code == 422
    async with maker() as db:
        p = await db.get(Project, story[0])
        p.published_at = None
        await db.commit()
    assert (await hit(same)).status_code == 404


async def test_snapshots_latest_known_not_sum_and_customer_visibility(client, story):
    url = f"/v1/admin/analytics/placements/{story[1]}/snapshots"
    today = analytics.today()
    yesterday = today - timedelta(days=1)

    async def save(day, **values):
        return await client.put(url, headers=OPS, json={"as_of": day.isoformat(), **values})

    assert (await client.put(url, headers=OWNER, json={"as_of": str(today), "views": 10})).status_code == 403
    assert (await save(today)).status_code == 422
    assert (await save(today, views=-1)).status_code == 422
    assert (await save(today + timedelta(days=1), views=1)).status_code == 422
    first = await save(yesterday, views=10, impressions=100, source_note="Publisher report")
    assert first.status_code == 200, first.text
    second = await save(today, views=30)
    assert second.status_code == 200, second.text
    report = (await client.get("/v1/analytics", headers=OWNER)).json()
    assert report["channel_totals"]["views"] == 30
    assert report["channel_totals"]["impressions"] == 100
    assert report["channels"][0]["impressions_as_of"] == str(yesterday)
    assert "updated_by" not in str(report) and len(report["channels"][0]["history"]) == 2
    corrected = await save(today, views=35)
    assert corrected.json()["id"] == second.json()["id"]
    historical = (await client.get(f"/v1/analytics?start={yesterday}&end={yesterday}", headers=OWNER)).json()
    assert historical["channel_totals"]["views"] == 10
    csv = await client.get("/v1/analytics/export.csv", headers=OWNER)
    assert csv.status_code == 200 and "cumulative as reported" in csv.text and "35" in csv.text
    assert (await client.delete(f"/v1/admin/analytics/snapshots/{first.json()['id']}", headers=OPS)).status_code == 200
    report = (await client.get("/v1/analytics", headers=OWNER)).json()
    assert report["channel_totals"]["impressions"] is None
    assert report["channel_totals"]["views"] == 35


async def test_metrics_request_is_logged_deduplicated_and_requires_published_contact(client, story, maker):
    url = f"/v1/admin/analytics/placements/{story[1]}/request-metrics"
    body = {"idempotency_key": "analytics-test-request"}
    for _ in range(2):
        response = await client.post(url, headers=OPS, json=body)
        assert response.status_code == 200, response.text
    async with maker() as db:
        rows = (
            (await db.execute(select(DistributionMail).where(DistributionMail.kind == "metrics_request")))
            .scalars()
            .all()
        )
        assert len(rows) == 1 and rows[0].recipient == "editor@example.com"
        assert "https://example.com/story" in rows[0].body and "impressions" in rows[0].body
        assert rows[0].status == "sent"
        p = await db.get(DistributionPlacement, story[1])
        p.contact_email = ""
        await db.commit()
    assert (await client.post(url, headers=OPS, json=body)).status_code == 409


async def test_pruning_retains_aggregates(client, story, maker):
    async with maker() as db:
        db.add(
            AudienceEvent(
                project_id=story[0],
                day=analytics.today() - timedelta(days=4),
                kind="story_visit",
                session_hash="a" * 64,
            )
        )
        db.add(AudienceDaily(project_id=story[0], day=analytics.today() - timedelta(days=4), story_visits=12))
        await db.commit()
    assert await analytics.prune_events() == 1
    assert (await client.get("/v1/analytics", headers=OWNER)).json()["platform"]["story_visits"] == 12


async def test_shared_video_dedupes_with_public_story_and_rejects_revoked_link(client, story, maker):
    from app.models import ShareLink
    from app.services.sessions import hash_token

    token = "analytics-private-video"
    async with maker() as db:
        db.add(ShareLink(project_id=story[0], token_hash=hash_token(token), views=4))
        await db.commit()
    session = str(uuid4())
    url = f"/v1/share/{token}/events"
    assert (await client.post(url, json={"kind": "share_visit", "session_id": session})).json()["recorded"]
    assert (await client.post(url, json={"kind": "video_view", "session_id": session})).json()["recorded"]
    # Public and private surfaces refer to the same video, so the same session isn't counted twice.
    assert not (
        await client.post(
            "/v1/public/stories/analytics-story/events", json={"kind": "video_view", "session_id": session}
        )
    ).json()["recorded"]
    report = (await client.get("/v1/analytics", headers=OWNER)).json()
    assert report["platform"]["share_visits"] == report["platform"]["video_views"] == 1
    assert report["legacy_share_opens_lifetime"] == 4
    async with maker() as db:
        link = (await db.execute(select(ShareLink))).scalar_one()
        link.revoked_at = utcnow()
        await db.commit()
    assert (await client.post(url, json={"kind": "share_visit", "session_id": str(uuid4())})).status_code == 404


async def test_analytics_export_and_erasure(client, story, maker, workspace):
    from app.models import PublisherSnapshot
    from app.services import privacy

    await client.post(
        "/v1/public/stories/analytics-story/events", json={"kind": "story_visit", "session_id": str(uuid4())}
    )
    saved = await client.put(
        f"/v1/admin/analytics/placements/{story[1]}/snapshots",
        headers=OPS,
        json={"as_of": str(analytics.today()), "views": 0, "source_note": "Confirmed zero"},
    )
    assert saved.status_code == 200
    async with maker() as db:
        ws = await db.get(Workspace, workspace)
        user = (await db.execute(select(User).where(User.email == "owner@acme.test"))).scalar_one()
        exported = await privacy.export_workspace(db, ws, user)
        assert exported["platform_analytics"][0]["story_visits"] == 1
        assert exported["publisher_analytics"][0]["views"] == 0
        assert "session_hash" not in str(exported)
        project = await db.get(Project, story[0])
        await privacy.purge_project(db, project)
        await db.commit()
        assert (await db.execute(select(AudienceDaily))).scalars().all() == []
        assert (await db.execute(select(AudienceEvent))).scalars().all() == []
        snapshot = (await db.execute(select(PublisherSnapshot))).scalar_one()
        assert snapshot.project_id is None
        await privacy.delete_workspace(db, ws)
        await db.commit()
        assert (await db.execute(select(PublisherSnapshot))).scalars().all() == []


async def test_date_boundaries_multiple_outlets_and_csv_formula_guard(client, story, maker, monkeypatch):
    initial = analytics.today()
    session = uuid4()
    async with maker() as db:
        assert await analytics.record(db, story[0], "story_visit", session)
    monkeypatch.setattr(analytics, "today", lambda: initial + timedelta(days=1))
    async with maker() as db:
        assert await analytics.record(db, story[0], "story_visit", session)
        first = await db.get(DistributionPlacement, story[1])
        other = DistributionPlacement(
            request_id=first.request_id,
            outlet_id="2",
            data={"name": "=Spreadsheet formula"},
            status="published",
            published_url="https://example.com/other",
        )
        db.add(other)
        await db.commit()
        other_id = other.id
    for placement, views in ((story[1], 10), (other_id, 20)):
        r = await client.put(
            f"/v1/admin/analytics/placements/{placement}/snapshots",
            headers=OPS,
            json={"as_of": str(initial), "views": views},
        )
        assert r.status_code == 200, r.text
    historical = (await client.get(f"/v1/analytics?start={initial}&end={initial}", headers=OWNER)).json()
    assert historical["platform"]["story_visits"] == 1
    assert historical["channel_totals"]["views"] == 30
    assert historical["channel_totals"]["impressions"] is None
    assert historical["channel_totals"]["outlets_with_reports"] == 2
    csv = (await client.get("/v1/analytics/export.csv", headers=OWNER)).text
    assert "'=Spreadsheet formula" in csv
