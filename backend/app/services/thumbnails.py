"""The cover picture of a video is the guest, not the presenter.

Every video opens on the presenter, so a cover taken from the start makes all the videos look the same. The cover is a frame
from the first answer, where the guest is on screen and talking. New renders are told which second to use
(`thumbnailAtSeconds`); videos made before that are fixed after the fact by cutting the frame out of the finished file, which
costs nothing at the presenter vendor (no new clip, no new render). A cover made this way is marked (`Asset.hash == GUEST`),
so the fix runs once per video.
"""

import asyncio
import logging
import tempfile
from pathlib import Path

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations import registry
from app.models import Asset, Job, Project
from app.services.scene_plan import FOUNDER_LAYOUT

log = logging.getLogger("thumbnails")
GUEST = "guest"  # Asset.hash on a thumbnail that shows the guest
INTO_ANSWER_S = 2.5  # far enough in that they are mid-sentence, not mid-breath
MIN_ANSWER_S = 1.0


def guest_moment_s(scene_plan: dict | None, lead_s: float = 0.0) -> float | None:
    """The second (in the finished video, after any branded opening) of a frame where the guest is on screen and talking:
    a little way into the first answer that has video. None when no answer has the guest on camera."""
    at = float(lead_s)
    for sc in (scene_plan or {}).get("scenes", []):
        dur = float(sc.get("duration_s") or 0)
        if (
            sc.get("type") in FOUNDER_LAYOUT
            and (sc.get("asset") or {}).get("kind") == "take_video"
            and dur >= MIN_ANSWER_S
        ):
            return round(at + min(INTO_ANSWER_S, dur * 0.4), 2)
        at += dur
    return None


async def _lead_s(session: AsyncSession, project: Project) -> float:
    """The branded opening this video was rendered with (recorded when it was made); 0 for older videos with none."""
    job = (
        (
            await session.execute(
                select(Job)
                .where(
                    Job.project_id == project.id,
                    Job.stage.in_(["merge_render", "final_render"]),
                    Job.status == "succeeded",
                )
                .order_by(Job.created_at.desc())
            )
        )
        .scalars()
        .first()
    )
    props = ((job.result or {}).get("props") or {}) if job else {}
    return float(props.get("brandIntroSeconds") or 0)


async def _frame(url: str, at_s: float) -> bytes | None:
    """One still from the video at `at_s`, as PNG (ffmpeg reads just the part it needs over the link)."""
    with tempfile.TemporaryDirectory() as d:
        out = Path(d) / "frame.png"
        proc = await asyncio.create_subprocess_exec(
            "ffmpeg", "-y", "-v", "error", "-ss", f"{at_s:.2f}", "-i", url, "-frames:v", "1", str(out),
            stdout=asyncio.subprocess.DEVNULL, stderr=asyncio.subprocess.PIPE,
        )  # fmt: skip
        try:
            _, err = await asyncio.wait_for(proc.communicate(), timeout=120)
        except TimeoutError:
            proc.kill()
            log.warning("ffmpeg timed out cutting a cover frame")
            return None
        if proc.returncode != 0 or not out.exists() or out.stat().st_size < 100:
            log.warning("ffmpeg could not cut a cover frame: %s", err.decode(errors="replace")[:300])
            return None
        return out.read_bytes()


async def refresh(session: AsyncSession, project: Project) -> bool:
    """Replace this video's cover with a frame of the guest talking. False if it can't (no answer on camera, no finished
    file, or the frame couldn't be cut); the existing cover is then left alone."""
    assets = list((await session.execute(select(Asset).where(Asset.project_id == project.id))).scalars())
    video = next((a for a in assets if a.type == "render" and a.format == "16x9"), None)
    thumb = next((a for a in assets if a.type == "thumbnail"), None)
    if video is None or project.scene_plan is None:
        return False
    at = guest_moment_s(project.scene_plan, await _lead_s(session, project))
    if at is None:
        return False
    storage = registry.get_storage()
    local = getattr(storage, "path", None)  # development storage is a folder: read the file itself
    source = str(local(video.storage_key)) if callable(local) else storage.presign_get(video.storage_key, 900)
    png = await _frame(source, at)
    if png is None:
        return False
    key = thumb.storage_key if thumb else f"projects/{project.id}/final/thumbnail.png"
    await storage.put(key, png, "image/png")
    if thumb is None:
        thumb = Asset(project_id=project.id, type="thumbnail", storage_key=key, format="16x9")
        session.add(thumb)
    thumb.hash = GUEST
    await session.commit()
    return True


async def refresh_all(limit: int = 200) -> dict:
    """Fix the cover of every finished video that doesn't show the guest yet. Safe to run again and again."""
    from app.db import session_maker

    done = skipped = 0
    async with session_maker()() as s:
        ids = (
            (
                await s.execute(
                    select(Project.id)
                    .where(Project.scene_plan.is_not(None), Project.state == "final_ready")
                    .order_by(Project.created_at.desc())
                )
            )
            .scalars()
            .all()
        )
    for pid in ids[: limit * 4]:
        if done + skipped >= limit:
            break
        async with session_maker()() as s:
            thumb_hash = (
                await s.execute(select(Asset.hash).where(Asset.project_id == pid, Asset.type == "thumbnail"))
            ).scalar_one_or_none()
            if thumb_hash == GUEST:
                continue
            project = await s.get(Project, pid)
            try:
                ok = project is not None and await refresh(s, project)
            except Exception:  # noqa: BLE001 - one bad video must not stop the rest
                log.exception("could not refresh the cover for a video", extra={"project_id": pid})
                ok = False
        done, skipped = done + ok, skipped + (not ok)
    return {"updated": done, "skipped": skipped}
