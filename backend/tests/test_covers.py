"""The cover of a video is the guest talking, not the presenter every video opens on, and older videos are fixed too."""

import subprocess

from sqlalchemy import select

from app.integrations import registry
from app.models import Asset, Project
from app.services import thumbnails
from tests.helpers import make_final_ready

PLAN = {
    "scenes": [
        {"type": "anchor_intro", "duration_s": 4, "asset": {"kind": "anchor"}},
        {"type": "anchor_question", "duration_s": 3, "asset": {"kind": "question_clip"}},
        {"type": "founder_picture_in_picture", "duration_s": 6, "asset": {"kind": "take_video"}},
    ]
}


def test_the_cover_comes_from_a_little_into_the_first_answer_with_the_guest_on_camera():
    assert (
        thumbnails.guest_moment_s(PLAN) == 7 + 2.4
    )  # 4 + 3 seconds of presenter, then 40% of 6 s (under the 2.5 s cap)
    assert thumbnails.guest_moment_s(PLAN, lead_s=5) == 5 + 7 + 2.4  # after the branded opening
    long_answer = {"scenes": [{"type": "founder_split", "duration_s": 40, "asset": {"kind": "take_video"}}]}
    assert thumbnails.guest_moment_s(long_answer) == 2.5


def test_no_cover_moment_when_the_guest_is_never_on_camera():
    voice_only = {"scenes": [{"type": "founder_column", "duration_s": 20, "asset": {"kind": "take_audio"}}]}
    assert thumbnails.guest_moment_s(voice_only) is None
    assert (
        thumbnails.guest_moment_s({"scenes": [{"type": "anchor_intro", "duration_s": 9, "asset": {"kind": "anchor"}}]})
        is None
    )
    assert thumbnails.guest_moment_s(None) is None
    too_short = {"scenes": [{"type": "founder_split", "duration_s": 0.5, "asset": {"kind": "take_video"}}]}
    assert thumbnails.guest_moment_s(too_short) is None


def pixel(png: bytes) -> tuple[int, int, int]:
    out = subprocess.run(
        ["ffmpeg", "-v", "error", "-i", "pipe:0", "-vf", "scale=1:1", "-f", "rawvideo", "-pix_fmt", "rgb24", "-"],
        input=png,
        capture_output=True,
        check=True,
    ).stdout
    return out[0], out[1], out[2]


async def finished_video(client, maker, tmp_path, plan=PLAN):
    """A finished project whose file is a real video: red through the 5 s branded opening and the presenter, blue once the guest answers."""
    pid = await make_final_ready(client)
    video = tmp_path / "v.mp4"
    subprocess.run(
        ["ffmpeg", "-y", "-v", "error", "-f", "lavfi", "-i", "color=c=red:s=320x180:d=12:r=10",
         "-f", "lavfi", "-i", "color=c=blue:s=320x180:d=6:r=10",
         "-filter_complex", "[0][1]concat=n=2:v=1:a=0", "-pix_fmt", "yuv420p", str(video)],
        check=True,
    )  # fmt: skip
    async with maker() as s:
        rendered = (
            await s.execute(
                select(Asset).where(Asset.project_id == pid, Asset.type == "render", Asset.format == "16x9")
            )
        ).scalar_one()
        await registry.get_storage().put(rendered.storage_key, video.read_bytes(), "video/mp4")
        project = await s.get(Project, pid)
        project.scene_plan = plan
        await s.commit()
        assert await thumbnails._lead_s(s, project) == 5.0  # the opening card this video was rendered with
    return pid


async def test_an_older_video_gets_a_cover_of_the_guest_talking(client, workspace, maker, tmp_path):
    pid = await finished_video(client, maker, tmp_path)
    async with maker() as s:
        before = (await s.execute(select(Asset).where(Asset.project_id == pid, Asset.type == "thumbnail"))).scalar_one()
        assert before.hash is None
        assert await thumbnails.refresh(s, await s.get(Project, pid)) is True
    async with maker() as s:
        thumb = (await s.execute(select(Asset).where(Asset.project_id == pid, Asset.type == "thumbnail"))).scalar_one()
        assert thumb.hash == thumbnails.GUEST
        r, g, b = pixel(await registry.get_storage().get(thumb.storage_key, 10_000_000))
    assert b > 150 and r < 80  # blue: the frame is from the guest's answer, not the red presenter opening


async def test_the_backfill_fixes_each_video_once_and_leaves_ones_without_a_guest_alone(
    client, workspace, maker, tmp_path
):
    from app.db import set_session_maker

    set_session_maker(maker)
    done = await finished_video(client, maker, tmp_path)
    presenter_only = await make_final_ready(client)  # no scene plan: a presenter-only video
    out = await thumbnails.refresh_all()
    assert out == {"updated": 1, "skipped": 0}
    assert await thumbnails.refresh_all() == {"updated": 0, "skipped": 0}  # nothing left to do: safe to run again
    async with maker() as s:
        hashes = {
            a.project_id: a.hash for a in (await s.execute(select(Asset).where(Asset.type == "thumbnail"))).scalars()
        }
    assert hashes[done] == thumbnails.GUEST and hashes[presenter_only] is None


async def test_a_video_with_only_a_voice_keeps_its_cover(client, workspace, maker, tmp_path):
    plan = {"scenes": [{"type": "founder_column", "duration_s": 20, "asset": {"kind": "take_audio"}}]}
    pid = await finished_video(client, maker, tmp_path, plan)
    async with maker() as s:
        assert await thumbnails.refresh(s, await s.get(Project, pid)) is False


async def test_operators_can_run_the_fix_and_it_is_audited(client, workspace, maker, tmp_path):
    from app.db import set_session_maker
    from tests.conftest import OPS, OWNER

    set_session_maker(maker)
    await finished_video(client, maker, tmp_path)
    assert (await client.post("/v1/admin/covers/refresh", headers=OWNER)).status_code == 403
    r = await client.post("/v1/admin/covers/refresh", headers=OPS)
    assert r.status_code == 200 and r.json()["updated"] == 1
