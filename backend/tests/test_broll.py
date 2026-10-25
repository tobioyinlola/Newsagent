"""Product footage: the owner's own images and clips, optional AI shots (always labelled synthetic), used in the video."""

import pytest
from sqlalchemy import select

from app.integrations import registry
from app.integrations.broll.mock import MockBrollProvider
from app.integrations.renderer.base import Analysis
from app.models import Project, User, Workspace
from app.pipeline.queue import get_queue
from app.services import scene_plan as sp
from tests.conftest import OPS, OWNER
from tests.helpers import BRIEF, record
from tests.test_live_interview import interviewed_project, state
from tests.test_uploads import PNG, confirm, upload

MP4 = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 200


def clip(seconds=10.0, w=1280, h=720):
    return Analysis(duration_s=seconds, has_audio=True, video_duration_s=seconds, width=w, height=h)


async def add_image(client, headers=OWNER):
    key = await upload(client, PNG, kind="product_image", headers=headers)
    assert (await confirm(client, key, headers=headers)).status_code == 200
    return key


async def add_video(client, analysis=None):
    registry.get_renderer().analysis_override = analysis or clip()
    key = await upload(client, MP4, kind="product_video", content_type="video/mp4")
    r = await confirm(client, key)
    registry.get_renderer().analysis_override = None
    return key, r


async def interview_project(client, **kw):
    pid, token = await interviewed_project(client, answers=(0, 1), **kw)
    return pid, token


async def finish(client, pid, token):
    for q in (2, 3):
        await record(client, token, q)
    await client.post(f"/v1/interview/{token}/submit")
    assert (await client.post(f"/v1/projects/{pid}/interview/merge", headers=OWNER)).status_code == 200
    await get_queue().drain()


# ---------- uploads ----------
async def test_a_product_video_is_measured_and_listed(client, workspace):
    key, r = await add_video(client)
    assert r.status_code == 200 and r.json()["duration_s"] == 10 and r.json()["kind"] == "product_video"
    listed = (await client.get("/v1/brand-kit/assets", headers=OWNER)).json()
    assert [a["duration_s"] for a in listed if a["key"] == key] == [10]


@pytest.mark.parametrize("analysis", [clip(1), clip(300), clip(10, 200, 100)])
async def test_unusable_product_videos_are_refused(client, workspace, analysis):
    _key, r = await add_video(client, analysis)
    assert r.status_code == 422
    assert (await client.get("/v1/brand-kit/assets", headers=OWNER)).json() == []


# ---------- choosing ----------
async def test_the_owner_picks_product_footage_within_limits(client, workspace):
    pid, _t = await interview_project(client)
    img, (vid, _r) = await add_image(client), await add_video(client)
    got = (await client.get(f"/v1/projects/{pid}/broll", headers=OWNER)).json()
    assert {c["key"] for c in got["candidates"]} == {img, vid} and got["items"] == [] and got["ai_available"]
    put = await client.put(
        f"/v1/projects/{pid}/broll",
        json={"items": [{"key": img, "caption": " Our app ", "seconds": 4}, {"key": vid, "seconds": 6}]},
        headers=OWNER,
    )
    assert put.status_code == 200, put.text
    items = put.json()["items"]
    assert [(i["kind"], i["caption"], i["seconds"], i["synthetic"]) for i in items] == [
        ("image", "Our app", 4, False),
        ("video", "", 6, False),
    ]
    bad = [
        {"items": [{"key": img, "seconds": 2}]},  # an image needs at least 3 s
        {"items": [{"key": "not-mine", "seconds": 4}]},
        {"items": [{"key": img, "seconds": 4}] * 6},
    ]
    for body in bad:
        assert (await client.put(f"/v1/projects/{pid}/broll", json=body, headers=OWNER)).status_code == 422


async def test_footage_is_private_to_the_workspace_and_to_interview_videos(client, workspace, maker):
    pid, _t = await interview_project(client)
    async with maker() as s:
        ws = Workspace(name="Other")
        s.add(ws)
        await s.flush()
        s.add(User(email="someone@else.test", workspace_id=ws.id))
        await s.commit()
    theirs = {"Authorization": "Bearer dev:someone@else.test"}
    other_key = await add_image(client, headers=theirs)
    r = await client.put(f"/v1/projects/{pid}/broll", json={"items": [{"key": other_key, "seconds": 4}]}, headers=OWNER)
    assert r.status_code == 422  # another customer's file is not a candidate
    assert (await client.get(f"/v1/projects/{pid}/broll", headers=theirs)).status_code == 404
    plain = (await client.post("/v1/projects", json=BRIEF, headers=OWNER)).json()["id"]
    assert (await client.put(f"/v1/projects/{plain}/broll", json={"items": []}, headers=OWNER)).status_code == 409


# ---------- in the video ----------
async def test_chosen_footage_plays_after_the_presenter_and_before_the_interview(client, workspace, maker):
    pid, token = await interview_project(client)
    img = await add_image(client)
    await client.put(
        f"/v1/projects/{pid}/broll", json={"items": [{"key": img, "caption": "Our app", "seconds": 4}]}, headers=OWNER
    )
    await finish(client, pid, token)
    assert await state(client, pid) == "final_ready"
    async with maker() as s:
        saved = sp.ScenePlan.model_validate((await s.get(Project, pid)).scene_plan)
    kinds = [s.type for s in saved.scenes]
    assert kinds[:3] == ["anchor_intro", "product_broll", "anchor_question"]
    broll = saved.scenes[1]
    assert broll.provenance == "owner_media" and broll.headline == "Our app" and broll.asset.kind == "broll_image"
    rendered = registry.get_renderer().requests[-1].props["scenes"][1]
    assert rendered["type"] == "broll" and rendered["synthetic"] is False and rendered["kind"] == "image"


async def test_without_footage_nothing_changes(client, workspace):
    pid, token = await interview_project(client)
    await finish(client, pid, token)
    assert "broll" not in [s["type"] for s in registry.get_renderer().requests[-1].props["scenes"]]


async def test_deleted_footage_stops_the_video_with_a_clear_reason_before_rendering(client, workspace):
    pid, token = await interview_project(client)
    img = await add_image(client)
    await client.put(f"/v1/projects/{pid}/broll", json={"items": [{"key": img, "seconds": 4}]}, headers=OWNER)
    await registry.get_storage().delete(img)
    await finish(client, pid, token)
    p = (await client.get(f"/v1/projects/{pid}", headers=OWNER)).json()
    assert p["state"] == "failed" and "scene 2 (product broll)" in p["failure_reason"]
    assert not any(r.composition == "InterviewMerge" for r in registry.get_renderer().requests)


# ---------- AI-generated shots ----------
async def test_an_ai_shot_is_billed_stored_and_always_marked_synthetic(client, workspace, maker):
    pid, token = await interview_project(client)
    ai = MockBrollProvider()
    registry.override(broll=ai)
    r = await client.post(
        f"/v1/projects/{pid}/broll/generate",
        json={"prompt": "A busy farmers market at sunrise", "seconds": 5},
        headers=OWNER,
    )
    assert r.status_code == 200, r.text
    gen = [c for c in r.json()["candidates"] if c["source"] == "generated"]
    assert len(gen) == 1 and gen[0]["synthetic"] is True and ai.calls == [("A busy farmers market at sunrise", 5)]
    put = await client.put(
        f"/v1/projects/{pid}/broll", json={"items": [{"key": gen[0]["key"], "seconds": 5}]}, headers=OWNER
    )
    assert put.json()["items"][0]["synthetic"] is True
    await finish(client, pid, token)
    assert await state(client, pid) == "final_ready"
    assert registry.get_renderer().requests[-1].props["scenes"][1]["synthetic"] is True
    async with maker() as s:
        assert (await s.get(Project, pid)).cost_total > 0
    from app.models import CreditTransaction

    async with maker() as s:
        rows = (await s.execute(select(CreditTransaction).where(CreditTransaction.stage == "broll"))).scalars().all()
    assert rows and rows[0].vendor == "mock"


async def test_ai_shots_say_so_when_no_provider_is_set_up(client, workspace):
    pid, _t = await interview_project(client)
    registry.override(broll=None)
    got = (await client.get(f"/v1/projects/{pid}/broll", headers=OWNER)).json()
    assert got["ai_available"] is False and "aren't set up" in got["note"]
    r = await client.post(
        f"/v1/projects/{pid}/broll/generate", json={"prompt": "A busy farmers market at sunrise"}, headers=OWNER
    )
    assert r.status_code == 503


async def test_ai_prompts_are_screened_and_budgeted(client, workspace):
    pid, _t = await interview_project(client)
    registry.override(broll=MockBrollProvider())
    bad = await client.post(
        f"/v1/projects/{pid}/broll/generate", json={"prompt": "We are selling cocaine to students"}, headers=OWNER
    )
    assert bad.status_code == 422
    await client.put("/v1/admin/vendor-budgets", json={"vendor": "mock", "limit": "0"}, headers=OPS)
    r = await client.post(
        f"/v1/projects/{pid}/broll/generate", json={"prompt": "A busy farmers market at sunrise"}, headers=OWNER
    )
    assert r.status_code == 402
