"""Founder take processing (stage 9): join uploaded chunks, clean up, transcribe, flag problems.

Runs per take as soon as the founder keeps it, so a bad take can be caught while they are still on the page.
Take failures never change the project's state: the founder or owner just sees the take as failed and retries.
"""

import asyncio
import logging
from decimal import Decimal

from sqlalchemy import select

from app.config import VENDOR_POLICIES
from app.db import session_maker
from app.integrations import registry
from app.integrations.renderer.base import ProcessRequest
from app.models import Asset, Job, Project, Take
from app.models.base import new_id
from app.pipeline import runner
from app.pipeline.steps import input_hash
from app.services import language_audit
from app.services.audit import audit
from app.services.interview import BLOCKING_FLAGS
from app.services.notifications import low_balance_alert, notify_owners, vendor_budget_alert
from app.services.spend_guard import LimitReached, SpendGuard

log = logging.getLogger("takes")
PROCESS_COST = Decimal("0.02")  # renderer minutes for cleanup/transcode; replace with measured cost
TRANSCRIBE_PER_MIN = Decimal("0.006")
TRANSCRIBE_RESERVE = Decimal("0.012")  # 2 minute cap


def chunk_key(project_id: str, take_id: str, idx: int) -> str:
    return f"projects/{project_id}/takes/{take_id}/raw/{idx:05d}"


def out_prefix(project_id: str, take_id: str) -> str:
    return f"projects/{project_id}/takes/{take_id}/out"


async def _fail(take_id: str, reason: str, notify: str | None = None) -> None:
    async with session_maker()() as s:
        take = await s.get(Take, take_id)
        if take is None:
            return
        take.status, take.error = "failed", reason
        pid = take.project_id
        await s.commit()
    if notify:
        await notify_owners(pid, notify)


async def process_take(take_id: str) -> None:
    policy = VENDOR_POLICIES["renderer"]
    async with session_maker()() as s:
        take = await s.get(Take, take_id)
        if take is None or take.status != "uploaded":
            return  # already handled (idempotent re-delivery)
        take.status, take.error = "processing", None
        pid = take.project_id
        ih = input_hash({"take": take.id, "chunks": take.chunks, "kind": take.kind})
        job = (
            await s.execute(select(Job).where(Job.project_id == pid, Job.stage == "process_take", Job.input_hash == ih))
        ).scalar_one_or_none()
        if job is None:
            s.add(
                Job(
                    id=new_id(),
                    project_id=pid,
                    stage="process_take",
                    input_hash=ih,
                    status="running",
                    vendor="renderer",
                )
            )
        else:
            job.status, job.error = "running", None
        await s.commit()

    for attempt in range(1, policy.max_attempts + 1):
        async with session_maker()() as s:
            take = await s.get(Take, take_id)
            project = await s.get(Project, pid)
            assert take is not None and project is not None
            job = (
                await s.execute(
                    select(Job).where(Job.project_id == pid, Job.stage == "process_take", Job.input_hash == ih)
                )
            ).scalar_one()
            job.attempts = attempt
            job_id = job.id  # read now: attributes expire after a rollback
            guard = SpendGuard(s, on_alert=vendor_budget_alert, on_low_balance=low_balance_alert)
            try:
                res_r = await guard.reserve(
                    project.workspace_id, "renderer", PROCESS_COST, project_id=pid, stage="process_take"
                )
                res_t = await guard.reserve(
                    project.workspace_id, "transcription", TRANSCRIBE_RESERVE, project_id=pid, stage="transcribe"
                )
            except LimitReached as e:
                await s.rollback()
                async with session_maker()() as s2:  # a partial reservation was rolled back; nothing was charged
                    j2 = (await s2.execute(select(Job).where(Job.id == job_id))).scalar_one()
                    j2.status, j2.error = "failed", e.reason
                    await s2.commit()
                await _fail(take_id, e.reason, notify="limit_reached")
                return
            # Commit the holds now. Left open, this transaction keeps the workspace and the renderer's budget row locked for the
            # whole processing time, and every other reservation for that vendor (all customers') would wait behind it.
            await s.commit()
            storage = registry.get_storage()
            urls = [storage.presign_get(chunk_key(pid, take.id, int(i)), 3600) for i in sorted(take.chunks, key=int)]
            try:
                pr = await registry.get_renderer().process(
                    ProcessRequest(
                        chunk_urls=urls, kind=take.kind, ext=take.ext, output_prefix=out_prefix(pid, take.id)
                    )
                )
                flags = list(pr.flags)
                transcript = None
                if "no_speech" not in flags:
                    transcript = await registry.get_transcription().transcribe(storage.presign_get(pr.audio_key, 1800))
                    if not transcript.has_speech:
                        flags.append("no_speech")
            except Exception as e:  # noqa: BLE001 - vendor failure: retry with backoff, charge nothing
                await guard.release(res_r)
                await guard.release(res_t)
                await s.commit()
                log.warning("process_take attempt %s failed: %s", attempt, e)
                if attempt >= policy.max_attempts:
                    async with session_maker()() as s2:
                        j2 = (await s2.execute(select(Job).where(Job.id == job_id))).scalar_one()
                        j2.status, j2.error = "failed", str(e)[:500]
                        await s2.commit()
                    await _fail(take_id, "We couldn't process this recording. Please try again.")
                    return
                await asyncio.sleep(policy.backoff_base_s * 2 ** (attempt - 1) * runner.BACKOFF_SCALE)
                continue

            minutes = Decimal(str(pr.duration_s)) / 60
            if transcript is not None:
                cost_t = await guard.settle(res_t, TRANSCRIBE_PER_MIN * minutes)
            else:
                await guard.release(res_t)
                cost_t = Decimal("0")
            cost_r = await guard.settle(res_r, PROCESS_COST)
            take.processed_video_key, take.processed_audio_key = pr.video_key, pr.audio_key
            take.duration_s = Decimal(str(round(pr.duration_s, 2)))
            take.transcript = transcript.text if transcript else ""
            take.srt = transcript.srt if transcript else ""
            if language_audit.has_abusive_language(take.transcript):
                flags.append("abusive_language")
                audit(
                    s,
                    "system",
                    "interview.abusive_language",
                    target_type="take",
                    target_id=take.id,
                    detail={"project_id": pid, "question_index": take.question_index, "action": "retake_required"},
                )
            take.flags, take.stats, take.error = sorted(set(flags)), pr.stats, None
            take.status = "needs_retake" if BLOCKING_FLAGS & set(flags) else "ready"
            s.add(
                Asset(
                    project_id=pid,
                    type="founder_take",
                    storage_key=pr.video_key or pr.audio_key,
                    format=f"q{take.question_index}",
                    duration=take.duration_s,
                )
            )
            project.cost_total += cost_r + cost_t
            job.status, job.cost, job.result = "succeeded", cost_r + cost_t, {"flags": flags}
            await s.commit()
            return


async def requeue_stuck(minutes: int = 20) -> int:
    """Sweeper: a worker that died mid-take leaves it 'processing'. Put it back so it runs again."""
    from datetime import UTC, datetime, timedelta

    from app.pipeline.queue import enqueue

    cutoff = datetime.now(UTC) - timedelta(minutes=minutes)
    ids: list[str] = []
    async with session_maker()() as s:
        for t in (await s.execute(select(Take).where(Take.status == "processing", Take.created_at < cutoff))).scalars():
            t.status = "uploaded"
            ids.append(t.id)
        await s.commit()
    for take_id in ids:  # enqueue only after the commit, so the worker sees the new status
        enqueue("process_take", {"take_id": take_id})
    return len(ids)
