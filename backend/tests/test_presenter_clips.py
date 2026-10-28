"""The presenter-clip library: operators upload TV-style presenter footage and merged videos mix it in."""

from sqlalchemy import select

from app.integrations import registry
from app.integrations.renderer.base import Analysis
from app.models import AuditLog, PresenterClip
from app.pipeline.queue import get_queue
from tests.conftest import OPS, OWNER
from tests.helpers import api_path, record
from tests.test_live_interview import interviewed_project, state

MP4 = b"\x00\x00\x00\x18ftypmp42" + b"\x00" * 200
BASE = "/v1/admin/presenter-clips"


def good(seconds=8.0, width=1920, height=1080):
    return Analysis(
        duration_s=seconds,
        has_audio=True,
        video_duration_s=seconds,
        audio_duration_s=seconds,
        width=width,
        height=height,
    )


async def add_clip(client, role="intro", title="Evening open", data=MP4, content_type="video/mp4", rights=True):
    r = await client.post(
        BASE,
        json={
            "title": title,
            "role": role,
            "content_type": content_type,
            "size_bytes": len(data),
            "rights_confirmed": rights,
        },
        headers=OPS,
    )
    if r.status_code != 200:
        return r
    slot = r.json()
    assert (await client.put(api_path(slot["upload_url"]), content=data)).status_code == 200
    return await client.post(f"{BASE}/{slot['id']}/confirm", headers=OPS)


async def test_only_operators_manage_the_library(client, workspace):
    assert (await client.get(BASE)).status_code == 401
    assert (await client.get(BASE, headers=OWNER)).status_code == 403
    r = await client.post(
        BASE,
        json={"title": "x", "role": "intro", "content_type": "video/mp4", "size_bytes": 10, "rights_confirmed": True},
        headers=OWNER,
    )
    assert r.status_code == 403
    assert (await client.get(BASE, headers=OPS)).json() == []


async def test_a_clip_is_checked_then_listed_with_a_preview(client, workspace, maker):
    registry.get_renderer().analysis_override = good(8)
    r = await add_clip(client, "intro")
    assert r.status_code == 200, r.text
    clip = r.json()
    assert clip["status"] == "clean" and clip["duration_s"] == 8 and clip["width"] == 1920 and clip["url"]
    assert clip["rights_confirmed_by"] == "ops@example.com"
    assert [c["id"] for c in (await client.get(BASE, headers=OPS)).json()] == [clip["id"]]
    async with maker() as s:
        actions = [a.action for a in (await s.execute(select(AuditLog))).scalars()]
    assert "presenter_clip.upload_started" in actions and "presenter_clip.added" in actions


async def test_rights_must_be_confirmed(client, workspace):
    r = await add_clip(client, rights=False)
    assert r.status_code == 422 and "rights" in r.json()["detail"]


async def test_bad_files_are_refused_and_removed(client, workspace, maker):
    registry.get_renderer().analysis_override = good(8)
    r = await add_clip(client, data=b"not a video at all", content_type="video/mp4")
    assert r.status_code == 422
    assert (await add_clip(client, content_type="application/pdf")).status_code == 422
    r = await client.post(
        BASE,
        json={
            "title": "big",
            "role": "intro",
            "content_type": "video/mp4",
            "size_bytes": 200 * 1024 * 1024,
            "rights_confirmed": True,
        },
        headers=OPS,
    )
    assert r.status_code == 422
    async with maker() as s:
        assert all(c.status == "rejected" for c in (await s.execute(select(PresenterClip))).scalars())
    assert (await client.get(BASE, headers=OPS)).json() == []


async def test_clips_must_suit_their_role_and_the_screen(client, workspace):
    renderer = registry.get_renderer()
    renderer.analysis_override = good(45)
    assert "must last between" in (await add_clip(client, "intro")).json()["detail"]
    renderer.analysis_override = good(1)
    assert (await add_clip(client, "cutaway")).status_code == 422
    renderer.analysis_override = good(5, 480, 270)
    assert "at least 720p" in (await add_clip(client, "cutaway")).json()["detail"]
    renderer.analysis_override = good(5, 1080, 1920)
    assert (await add_clip(client, "cutaway")).status_code == 422  # portrait
    renderer.analysis_override = good(5)
    assert (await add_clip(client, "cutaway")).status_code == 200


async def test_edit_switch_off_and_delete(client, workspace, maker):
    registry.get_renderer().analysis_override = good(6)
    cid = (await add_clip(client, "cutaway")).json()["id"]
    r = await client.patch(f"{BASE}/{cid}", json={"active": False, "title": " Reaction "}, headers=OPS)
    assert r.json()["active"] is False and r.json()["title"] == "Reaction"
    registry.get_renderer().analysis_override = good(6)
    assert (await client.patch(f"{BASE}/{cid}", json={"role": "intro"}, headers=OPS)).status_code == 200
    key = None
    async with maker() as s:
        key = (await s.get(PresenterClip, cid)).key
    assert (await client.delete(f"{BASE}/{cid}", headers=OPS)).status_code == 204
    assert (await client.get(BASE, headers=OPS)).json() == []
    assert (await client.delete(f"{BASE}/{cid}", headers=OPS)).status_code == 404
    async with maker() as s:
        assert (await s.execute(select(PresenterClip).where(PresenterClip.key == key))).first() is None


async def test_merged_videos_mix_in_the_presenter_footage(client, workspace):
    renderer = registry.get_renderer()
    renderer.analysis_override = good(5)
    ids = {}
    for role in ("intro", "cutaway", "outro"):
        ids[role] = (await add_clip(client, role, title=role)).json()["id"]
    renderer.analysis_override = None  # the finished video is measured normally
    pid, token = await interviewed_project(client, answers=(0, 1))
    for q in (2, 3):
        await record(client, token, q)
    await client.post(f"/v1/interview/{token}/submit")
    assert (await client.post(f"/v1/projects/{pid}/interview/merge", headers=OWNER)).status_code == 200
    await get_queue().drain()
    assert await state(client, pid) == "final_ready"
    scenes = renderer.requests[-1].props["scenes"]
    kinds = [s["type"] for s in scenes]
    # opening shot, the AI presenter, then question/answer pairs with a cutaway between answers, the sign-off, a closing shot
    assert kinds == ["clip", "anchor"] + ["question", "answer", "clip"] * 3 + ["question", "answer", "anchor", "clip"]
    assert all(s["seconds"] == 5 for s in scenes if s["type"] == "clip")
    total = sum(s["seconds"] for s in scenes)
    assert abs(renderer.requests[-1].props["totalSeconds"] - total) < 0.01


async def test_without_clips_the_video_is_as_before(client, workspace):
    pid, token = await interviewed_project(client, answers=(0, 1))
    for q in (2, 3):
        await record(client, token, q)
    await client.post(f"/v1/interview/{token}/submit")
    await client.post(f"/v1/projects/{pid}/interview/merge", headers=OWNER)
    await get_queue().drain()
    kinds = [s["type"] for s in registry.get_renderer().requests[-1].props["scenes"]]
    assert "clip" not in kinds and kinds[0] == "anchor"


async def test_switched_off_clips_are_not_used(client, workspace):
    registry.get_renderer().analysis_override = good(5)
    cid = (await add_clip(client, "intro")).json()["id"]
    registry.get_renderer().analysis_override = None
    await client.patch(f"{BASE}/{cid}", json={"active": False}, headers=OPS)
    pid, token = await interviewed_project(client, answers=(0, 1))
    for q in (2, 3):
        await record(client, token, q)
    await client.post(f"/v1/interview/{token}/submit")
    await client.post(f"/v1/projects/{pid}/interview/merge", headers=OWNER)
    await get_queue().drain()
    assert registry.get_renderer().requests[-1].props["scenes"][0]["type"] == "anchor"


async def test_the_presenter_only_video_gets_the_opening_shot_and_sign_off(client, workspace):
    from tests.helpers import make_final_ready

    renderer = registry.get_renderer()
    renderer.analysis_override = good(5)
    for role in ("intro", "cutaway", "outro"):
        assert (await add_clip(client, role, title=role)).status_code == 200
    renderer.analysis_override = None
    pid = await make_final_ready(client)
    assert (await client.get(f"/v1/projects/{pid}", headers=OWNER)).json()["state"] == "final_ready"
    req = [r for r in renderer.requests if r.composition == "NewsStudio" and r.output_prefix.endswith("/final")][-1]
    assert req.props["introClip"]["seconds"] == 5 and req.props["outroClip"]["seconds"] == 5
    assert "cutaway" not in str(req.props)  # cutaways only make sense between founder answers
    # the quality gate measured the whole video, clips included
    assert (
        abs(renderer.duration_s - (req.props["anchorDurationSeconds"] + 10 + 11)) < 0.01
    )  # + the 5 s intro and 6 s outro cards


async def test_without_clips_the_presenter_only_video_is_unchanged(client, workspace):
    from tests.helpers import make_final_ready

    pid = await make_final_ready(client)
    req = [r for r in registry.get_renderer().requests if r.composition == "NewsStudio"][-1]
    assert "introClip" not in req.props and "outroClip" not in req.props
    assert (await client.get(f"/v1/projects/{pid}", headers=OWNER)).json()["state"] == "final_ready"
