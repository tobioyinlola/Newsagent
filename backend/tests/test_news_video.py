import pytest
from sqlalchemy import select

from app.integrations import registry
from app.integrations.avatar.base import AvatarResult
from app.integrations.renderer.base import Analysis
from app.models import Job, NewsVideo, Project, Workspace
from app.services import news_video
from app.services import news_video_rules as rules
from tests.conftest import OPS
from tests.helpers import api_path
from tests.test_news_desk import BASE, PNG, publish, ready


async def with_picture(client):
    row = await ready(client)
    image = (
        await client.post(
            f"{BASE}/{row['id']}/images",
            headers=OPS,
            json={"filename": "cover.png", "content_type": "image/png", "size_bytes": len(PNG)},
        )
    ).json()
    await client.put(api_path(image["upload_url"]), content=PNG)
    await client.post(f"{BASE}/{row['id']}/images/confirm", headers=OPS, json={"image_id": image["image_id"]})
    result = await client.put(
        f"{BASE}/{row['id']}",
        headers=OPS,
        json={
            **row["data"],
            "revision": row["revision"],
            "pictures": [{"id": image["image_id"], "caption": "Cover picture", "credit": "Editor"}],
            "cover_image_id": image["image_id"],
        },
    )
    assert result.status_code == 200, result.text
    return result.json()


async def start(client, row, monkeypatch):
    monkeypatch.setattr(news_video, "enqueue", lambda id: None)
    response = await client.post(f"{BASE}/{row['id']}/generate-video", headers=OPS, json={"revision": row["revision"]})
    assert response.status_code == 200, response.text
    return response.json()["video"]["id"]


async def test_isolated_render_ready_publish_and_deduplicated_retry(client, workspace, maker, monkeypatch):
    row = await with_picture(client)
    async with maker() as db:
        balance = (await db.get(Workspace, workspace)).credit_balance
    job = await start(client, row, monkeypatch)
    duplicate = await start(client, row, monkeypatch)
    assert job == duplicate
    await news_video.run(job)
    await news_video.run(job)
    async with maker() as db:
        video = await db.get(NewsVideo, job)
        assert video.status == "ready", video.error
        assert video.media["duration_s"] <= 60
        assert not list((await db.execute(select(Project))).scalars())
        assert not list((await db.execute(select(Job))).scalars())
        assert (await db.get(Workspace, workspace)).credit_balance == balance
    render = registry.get_renderer().requests[-1]
    assert render.composition == "NewsBreaking"
    assert render.props["brandIntroSeconds"] == 7 and render.props["brandOutroSeconds"] == 6
    assert render.props["pictures"]
    response = await publish(client, row)
    assert response.status_code == 200, response.text
    page = (await client.get(f"/v1/public/stories/{row['slug']}")).json()
    assert page["has_video"] and page["video_url"] and page["duration_s"] <= 60
    assert page["thumbnail_url"]
    current = response.json()
    assert current["video"]["matches_draft"]
    # Republish-only revisions do not purchase the same video again.
    assert await start(client, current, monkeypatch) == job
    changed = (
        await client.put(
            f"{BASE}/{row['id']}",
            headers=OPS,
            json={
                **current["data"],
                "headline": "A genuinely different headline for a new revision",
                "revision": current["revision"],
            },
        )
    ).json()
    assert not changed["video"]["matches_draft"]
    assert (await client.get(f"/v1/public/stories/{row['slug']}")).json()["title"] == row["data"]["headline"]


async def test_publish_waits_for_inflight_video_and_stale_copy_is_rejected(client, workspace, monkeypatch):
    row = await with_picture(client)
    await start(client, row, monkeypatch)
    assert (await publish(client, row)).status_code == 409
    assert (
        await client.post(f"{BASE}/{row['id']}/generate-video", headers=OPS, json={"revision": 1})
    ).status_code == 409
    for field, text in [("body", "too short"), ("presenter_script", "word " * 200)]:
        edited = await client.put(
            f"{BASE}/{row['id']}", headers=OPS, json={**row["data"], field: text, "revision": row["revision"]}
        )
        assert edited.status_code == 200
        row = edited.json()
        assert (await publish(client, row)).status_code == 422


async def test_overlong_presenter_or_render_never_becomes_ready(client, workspace, maker, monkeypatch):
    row = await with_picture(client)
    avatar = registry.get_avatar_named("mock")

    async def long_clip(request):
        return AvatarResult("mock://anchor.mp4", 47.001, 1, "overlong")

    monkeypatch.setattr(avatar, "generate", long_clip)
    job = await start(client, row, monkeypatch)
    await news_video.run(job)
    async with maker() as db:
        video = await db.get(NewsVideo, job)
        assert video.status == "failed" and "47-second" in video.error
    assert not registry.get_renderer().requests
    assert (await client.get(f"/v1/public/stories/{row['slug']}")).status_code == 404


async def test_overlong_measured_output_and_retry_reuses_presenter(client, workspace, maker, monkeypatch):
    row = await with_picture(client)
    job = await start(client, row, monkeypatch)
    renderer = registry.get_renderer()
    original_analyze = renderer.analyze
    calls = 0

    async def analyze(url):
        nonlocal calls
        calls += 1
        if calls > 1:
            return Analysis(60.0001, True, 60.0001, 60.0001)
        return await original_analyze(url)

    monkeypatch.setattr(renderer, "analyze", analyze)
    await news_video.run(job)
    async with maker() as db:
        video = await db.get(NewsVideo, job)
        assert video.status == "failed"
        assert "60-second" in video.error and "output_key" not in video.media
        assert video.media["anchor_key"]
    monkeypatch.setattr(renderer, "analyze", original_analyze)

    async def must_not_generate(request):
        raise AssertionError("Retry purchased another presenter")

    monkeypatch.setattr(registry.get_avatar_named("mock"), "generate", must_not_generate)
    assert await start(client, row, monkeypatch) == job
    await news_video.run(job)
    async with maker() as db:
        assert (await db.get(NewsVideo, job)).status == "ready"


@pytest.mark.parametrize("value", [47.0001, 48, float("nan"), float("inf"), 0, -1])
def test_strict_presenter_duration(value):
    with pytest.raises(ValueError):
        rules.timeline(value)


def test_complete_minute_counts_intro_sting_and_outro():
    assert rules.timeline(47) == (1410, 60)
    assert rules.timeline(30) == (900, 43)
    for duration in [60.000001, float("nan"), float("inf"), 0]:
        with pytest.raises(ValueError):
            rules.measured_output(duration, True)
    rules.measured_output(60, True, 60, 60)


async def test_lost_renderer_job_can_retry_without_a_second_presenter(client, workspace, maker, monkeypatch):
    from app.integrations.errors import ProviderError

    row = await with_picture(client)
    job = await start(client, row, monkeypatch)
    renderer = registry.get_renderer()
    original_status = renderer.status

    async def missing(id):
        raise ProviderError("renderer restarted", "temporary")

    monkeypatch.setattr(renderer, "status", missing)
    await news_video.run(job)
    async with maker() as db:
        video = await db.get(NewsVideo, job)
        assert video.status == "failed" and not video.renderer_id
        assert video.media["anchor_key"]
    monkeypatch.setattr(renderer, "status", original_status)

    async def must_not_generate(request):
        raise AssertionError("A renderer retry must not repurchase the presenter")

    monkeypatch.setattr(registry.get_avatar_named("mock"), "generate", must_not_generate)
    await start(client, row, monkeypatch)
    await news_video.run(job)
    async with maker() as db:
        assert (await db.get(NewsVideo, job)).status == "ready"


async def test_editorial_provider_budget_is_enforced_without_customer_charges(client, workspace, maker, monkeypatch):
    from sqlalchemy import delete

    from app.models import VendorBudget

    row = await with_picture(client)
    async with maker() as db:
        await db.execute(delete(VendorBudget).where(VendorBudget.vendor == "mock"))
        await db.commit()
    job = await start(client, row, monkeypatch)

    async def must_not_generate(request):
        raise AssertionError("No provider call may bypass an approved company budget")

    monkeypatch.setattr(registry.get_avatar_named("mock"), "generate", must_not_generate)
    await news_video.run(job)
    async with maker() as db:
        video = await db.get(NewsVideo, job)
        assert video.status == "failed" and "budget" in video.error
        assert not video.provider_id


async def test_cover_selection_is_independent_of_gallery_order(client, workspace):
    row = await with_picture(client)
    second = (
        await client.post(
            f"{BASE}/{row['id']}/images",
            headers=OPS,
            json={"filename": "second.png", "content_type": "image/png", "size_bytes": len(PNG)},
        )
    ).json()
    await client.put(api_path(second["upload_url"]), content=PNG)
    await client.post(f"{BASE}/{row['id']}/images/confirm", headers=OPS, json={"image_id": second["image_id"]})
    response = await client.put(
        f"{BASE}/{row['id']}",
        headers=OPS,
        json={
            **row["data"],
            "revision": row["revision"],
            "pictures": row["data"]["pictures"] + [{"id": second["image_id"], "caption": "Second image", "credit": ""}],
            "cover_image_id": second["image_id"],
        },
    )
    assert response.status_code == 200
    assert (await publish(client, response.json())).status_code == 200
    public = (await client.get(f"/v1/public/stories/{row['slug']}")).json()
    assert second["image_id"] in public["thumbnail_url"]
