"""Standalone editorial video generation. No customer pipeline, project or wallet mutations."""

import asyncio
import logging
from copy import deepcopy
from datetime import timedelta
from decimal import Decimal
from pathlib import Path

import httpx
from sqlalchemy import select, update

from app.config import get_settings
from app.db import session_maker
from app.integrations import registry
from app.integrations.avatar.base import AvatarRequest
from app.integrations.errors import ProviderError
from app.integrations.renderer.base import RenderRequest
from app.models import NewsImage, NewsVideo, VendorBudget
from app.models.base import utcnow
from app.services import news_video_rules as rules

log = logging.getLogger("news_video")
_tasks: set[asyncio.Task] = set()


def enqueue(id: str) -> None:
    if get_settings().queue_backend == "celery":
        from app.pipeline.celery_app import celery_app

        try:
            celery_app.send_task("news_desk.render", args=[id], queue="newsdesk")
        except Exception:
            log.exception("News Desk job remains queued for the dedicated recovery sweep")
    else:
        task = asyncio.create_task(run(id))
        _tasks.add(task)
        task.add_done_callback(_tasks.discard)


async def video_out(row: NewsVideo | None) -> dict | None:
    if row is None:
        return None
    key = row.media.get("output_key") if row.status == "ready" else None
    return {
        "id": row.id,
        "revision": row.story_revision,
        "status": row.status,
        "progress": row.progress,
        "error": row.error,
        "duration_s": row.media.get("duration_s"),
        "url": registry.get_storage().presign_get(key, 900) if key else None,
    }


async def run(id: str) -> None:
    async with session_maker()() as db:
        row = (
            await db.execute(
                update(NewsVideo)
                .where(NewsVideo.id == id, NewsVideo.status == "queued")
                .values(status="running", updated_at=utcnow(), error="")
                .returning(NewsVideo)
            )
        ).scalar_one_or_none()
        await db.commit()
        if row is None:
            return
        try:
            await generate(db, row)
        except Exception as exc:
            await db.rollback()
            row = await db.get(NewsVideo, id)
            if row:
                row.status = "failed"
                row.error = (
                    str(exc)[:600]
                    if isinstance(exc, ValueError)
                    else "Video generation could not finish. Your saved story is safe. Retry this job to resume, or shorten the script and save a new version."
                )
                row.updated_at = utcnow()
                await db.commit()
            log.exception("News Desk render failed: %s", id)


async def checkpoint(db, row, progress: int, media: dict | None = None):
    row.progress, row.updated_at = progress, utcnow()
    if media is not None:
        row.media = deepcopy(media)
    await db.commit()


async def generate(db, row: NewsVideo):
    data = row.snapshot
    rules.validate_copy(data)
    storage, renderer = registry.get_storage(), registry.get_renderer()
    if not row.provider_name:
        providers = await registry.avatar_chain(db)
        row.provider_name = providers[0].name
        await checkpoint(db, row, 5)
    avatar = registry.get_avatar_named(row.provider_name)
    request = AvatarRequest(
        script_text=data["presenter_script"],
        voice_accent="british",
        avatar_id=get_settings().news_desk_avatar_id or get_settings().heygen_default_avatar_id or None,
        transparent=False,
    )
    media = dict(row.media)
    if not media.get("anchor_key"):
        await reserve_presenter_budget(db, row, media, avatar.name, avatar.estimate_cost(request))
        if avatar.supports_async:
            if not row.provider_id:
                # Persist submission intent before purchasing: ambiguous submissions require manual review.
                row.provider_id = "submission_started"
                await checkpoint(db, row, 10)
                row.provider_id = await avatar.submit(request)
                await checkpoint(db, row, 15)
            if row.provider_id == "submission_started":
                raise ValueError(
                    "The presenter submission was interrupted before its reference was saved. Contact support to reconcile the provider request before generating again."
                )
            for _ in range(450):
                result = await avatar.poll(row.provider_id, request)
                if result.status == "completed" and result.result:
                    clip = result.result
                    break
                if result.status == "failed":
                    raise ValueError(
                        "The presenter provider could not finish this recording. Contact the team before retrying a paid provider job."
                    )
                await asyncio.sleep(2)
                await checkpoint(db, row, 20)
            else:
                raise ValueError(
                    "The presenter is still processing. Retry to check the same provider job; no new presenter request will be submitted."
                )
        else:
            if row.provider_id:
                raise ValueError(
                    "This provider request was interrupted. Reconcile it with the provider before retrying to avoid a duplicate charge."
                )
            row.provider_id = "submission_started"
            await checkpoint(db, row, 10)
            clip = await avatar.generate(request)
            row.provider_id = clip.vendor_video_id
        await settle_presenter_budget(db, row, media, clip.cost)
        rules.timeline(clip.duration_s)
        key = f"news-desk/{row.story_id}/video/{row.id}/presenter.mp4"
        if clip.video_url.startswith("mock://"):
            file = get_settings().mock_anchor_file
            content = Path(file).read_bytes() if file else b"mock-news-presenter"
        else:
            async with httpx.AsyncClient(timeout=300, follow_redirects=True) as client:
                async with client.stream("GET", clip.video_url) as response:
                    response.raise_for_status()
                    chunks, size = [], 0
                    async for chunk in response.aiter_bytes():
                        size += len(chunk)
                        if size > 200 * 1024 * 1024:
                            raise ValueError("Presenter video exceeds the News Desk file-size limit.")
                        chunks.append(chunk)
                    content = b"".join(chunks)
        await storage.put(key, content, "video/mp4")
        media.update(anchor_key=key, presenter_seconds=clip.duration_s, provider_cost=str(clip.cost))
        await checkpoint(db, row, 40, media)
    # Probe the real media, rather than trusting just the vendor's duration estimate.
    if media.get("measured_presenter_seconds"):
        seconds = float(media["measured_presenter_seconds"])
    else:
        measured = await renderer.analyze(storage.presign_get(media["anchor_key"], 3600))
        if not measured.has_audio:
            raise ValueError("The presenter recording has no audio. It cannot be rendered.")
        seconds = max(
            media["presenter_seconds"],
            measured.duration_s,
            measured.audio_duration_s or 0,
            measured.video_duration_s or 0,
        )
        media["measured_presenter_seconds"] = seconds
        await checkpoint(db, row, 45, media)
    frames, duration = rules.timeline(seconds)
    if not row.renderer_id:
        ids = [p["id"] for p in data["pictures"]]
        images = {
            i.id: i
            for i in (
                await db.execute(
                    select(NewsImage).where(
                        NewsImage.id.in_(ids), NewsImage.story_id == row.story_id, NewsImage.status == "clean"
                    )
                )
            ).scalars()
        }
        if len(images) != len(ids):
            raise ValueError("A selected story image is no longer available. Save and generate a new draft version.")
        scenes = data.get("scenes", [])
        pictures = [
            {
                "src": storage.presign_get(images[p["id"]].key, 21600),
                "caption": p.get("caption", ""),
                "duration_s": next((s["duration_s"] for s in scenes if s.get("image_id") == p["id"]), 5),
                "motion": next((s["motion"] for s in scenes if s.get("image_id") == p["id"]), "slow_zoom_in"),
            }
            for p in data["pictures"]
        ]
        props = {
            "headline": data["headline"],
            "summary": data["summary"],
            "anchorSrc": storage.presign_get(media["anchor_key"], 21600),
            "presenterFrames": frames,
            "pictures": pictures,
            "anchorDurationSeconds": frames / 30,
            "brandIntroSeconds": rules.INTRO_SECONDS + rules.STING_SECONDS,
            "brandOutroSeconds": rules.OUTRO_SECONDS,
        }
        row.renderer_id = await renderer.submit(
            RenderRequest(
                composition="NewsBreaking",
                props=props,
                outputs=[{"format": "16x9", "width": 1920, "height": 1080, "name": "breaking-news"}],
                input_urls={},
                output_prefix=f"news-desk/{row.story_id}/video/{row.id}",
            )
        )
        await checkpoint(db, row, 50)
    for _ in range(600):
        try:
            render_result = await renderer.status(row.renderer_id)
        except ProviderError as error:
            if error.category == "temporary":
                row.renderer_id = ""
                await checkpoint(db, row, 50)
                raise ValueError(
                    "The renderer restarted. Retry to render again using the saved presenter recording."
                ) from None
            raise
        if render_result.status == "succeeded":
            break
        if render_result.status == "failed":
            row.renderer_id = ""  # Presenter media survives; a retry only rerenders the existing recording.
            await checkpoint(db, row, 50)
            raise ValueError("The renderer could not finish. Retry to reuse the existing presenter recording.")
        await asyncio.sleep(2)
        await checkpoint(db, row, min(95, 50 + round(render_result.progress * 45)))
    else:
        raise ValueError("The render is still running. Retry to check the same render job.")
    output_key = next((k for k in render_result.output_keys if k.endswith("/breaking-news.mp4")), None)
    if not output_key:
        raise ValueError("The renderer did not return the expected News Desk video.")
    check = await renderer.analyze(storage.presign_get(output_key, 3600))
    try:
        rules.measured_output(check.duration_s, check.has_audio, check.video_duration_s, check.audio_duration_s)
        if check.duration_s < duration - 0.1:
            raise ValueError("The rendered video is incomplete. It has not been published.")
    except ValueError:
        # An invalid final file never remains available as a completed News Desk video.
        await storage.delete(output_key)
        row.renderer_id = ""
        await checkpoint(db, row, 95)
        raise
    media.update(output_key=output_key, duration_s=check.duration_s)
    row.status = "ready"
    await checkpoint(db, row, 100, media)


async def recover() -> dict:
    async with session_maker()() as db:
        await db.execute(
            update(NewsVideo)
            .where(NewsVideo.status == "running", NewsVideo.updated_at < utcnow() - timedelta(hours=1))
            .values(status="queued")
        )
        ids = list((await db.execute(select(NewsVideo.id).where(NewsVideo.status == "queued"))).scalars())
        await db.commit()
    for id in ids:
        enqueue(id)
    return {"news_desk_jobs_queued": len(ids)}


async def reserve_presenter_budget(db, row: NewsVideo, media: dict, vendor: str, estimate: float) -> None:
    """Hold company vendor budget only; never touch a customer's credits or spend cap."""
    if media.get("presenter_budget"):
        return
    from app.services.spend_guard import ensure_vendor_budget, is_paused

    period = utcnow().strftime("%Y-%m")
    amount = Decimal(str(estimate))
    enforce = get_settings().enforce_limits
    if enforce and await is_paused(db):
        raise ValueError("Paid video generation is paused. The News Desk draft has been saved.")
    budget = (
        await db.execute(
            select(VendorBudget).where(VendorBudget.vendor == vendor, VendorBudget.period == period).with_for_update()
        )
    ).scalar_one_or_none()
    if budget is None and not enforce:
        budget = await ensure_vendor_budget(db, vendor, Decimal("0"))
    if budget is None or (enforce and budget.spent + amount > budget.limit):
        raise ValueError(
            "The presenter vendor budget is unavailable or exhausted. Update the company vendor budget before retrying."
        )
    budget.spent += amount
    media["presenter_budget"] = {"vendor": vendor, "period": period, "estimate": str(amount), "settled": False}
    await checkpoint(db, row, 8, media)


async def settle_presenter_budget(db, row: NewsVideo, media: dict, actual: float) -> None:
    hold = media["presenter_budget"]
    if hold["settled"]:
        return
    budget = (
        await db.execute(
            select(VendorBudget)
            .where(VendorBudget.vendor == hold["vendor"], VendorBudget.period == hold["period"])
            .with_for_update()
        )
    ).scalar_one()
    budget.spent += Decimal(str(actual)) - Decimal(hold["estimate"])
    media["presenter_budget"] = {**hold, "settled": True, "actual": str(actual)}
    await checkpoint(db, row, 30, media)
