import asyncio
import logging
import time
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select

from app.config import VENDOR_POLICIES
from app.db import session_maker
from app.models import Job, Project
from app.models.base import new_id
from app.pipeline import steps
from app.services import state_machine as sm
from app.services.notifications import notify_owners, vendor_budget_alert
from app.services.spend_guard import LimitReached, SpendGuard

log = logging.getLogger("pipeline")
BACKOFF_SCALE = 1.0  # tests set to 0

STEPS = {
    "question_clips": ("avatar", steps.question_clips, None),
    "merge_render": ("renderer", steps.merge_render, "final_ready"),
    "preview_render": ("renderer", steps.preview_render, None),
    "anchor_render": ("avatar", steps.anchor_render, "anchor_ready"),
    "final_render": ("renderer", steps.final_render, "final_ready"),
}
# State a project must be in for a finished step to move it forward; otherwise a re-run is a no-op.
PREDECESSOR = {
    "question_clips": "anchor_ready",
    "merge_render": "merging",
    "anchor_render": "rendering_anchor",
    "preview_render": "anchor_ready",
    "final_render": "anchor_ready",
}


async def run_step(step: str, payload: dict) -> None:
    if step == "process_take":  # per-take work isn't tied to the project's state
        from app.pipeline.takes import process_take

        await process_take(payload["take_id"])
        return
    vendor_kind, fn, next_state = STEPS[step]
    policy = VENDOR_POLICIES[vendor_kind]
    pid = payload["project_id"]

    async with session_maker()() as session:
        project = await session.get(Project, pid)
        if project is None:
            return
        inputs = await steps.anchor_inputs(session, project)
        if step == "merge_render":
            inputs = {**inputs, **await steps.merge_inputs(session, project)}
        ih = steps.input_hash({"step": step, **inputs})
        job = (
            await session.execute(select(Job).where(Job.project_id == pid, Job.stage == step, Job.input_hash == ih))
        ).scalar_one_or_none()
        if job is None:
            job = Job(id=new_id(), project_id=pid, stage=step, input_hash=ih, status="pending")
            session.add(job)
        stale = timedelta(seconds=policy.timeout_s * 1.5)
        if (
            job.status == "running"
            and job.started_at
            and datetime.now(UTC) - job.started_at.replace(tzinfo=UTC) < stale
        ):
            return  # another worker owns it
        if job.status != "succeeded":
            job.status, job.started_at = "running", datetime.now(UTC)
            await session.commit()

    if job.status != "succeeded":
        ok = await _attempt_loop(step, fn, pid, ih, policy)
        if not ok:
            return
    await _finish(step, pid, next_state)


async def _attempt_loop(step, fn, pid, ih, policy) -> bool:
    for attempt in range(1, policy.max_attempts + 1):
        started = time.monotonic()
        async with session_maker()() as session:
            project = await session.get(Project, pid)
            assert project is not None
            job = (
                await session.execute(select(Job).where(Job.project_id == pid, Job.stage == step, Job.input_hash == ih))
            ).scalar_one()
            job.attempts = attempt
            guard = SpendGuard(session, on_alert=vendor_budget_alert)
            try:
                out = await fn(session, project, guard)
            except LimitReached as e:
                sm.limit_reached(project, e.reason)
                job.status, job.error = "failed", e.reason
                await session.commit()
                await notify_owners(pid, "limit_reached")
                return False  # refused: no retries, nothing was charged
            except Exception as e:  # vendor failure
                await session.rollback()
                async with session_maker()() as s2:
                    j2 = (
                        await s2.execute(
                            select(Job).where(Job.project_id == pid, Job.stage == step, Job.input_hash == ih)
                        )
                    ).scalar_one()
                    j2.attempts, j2.error = attempt, str(e)[:1000]
                    if attempt >= policy.max_attempts:
                        p2 = await s2.get(Project, pid)
                        assert p2 is not None
                        j2.status = "failed"
                        sm.fail(p2, "We couldn't finish this step. Please retry.", retryable=True)
                        await s2.commit()
                        await notify_owners(pid, "failed")
                        return False
                    await s2.commit()
                await asyncio.sleep(policy.backoff_base_s * 2 ** (attempt - 1) * BACKOFF_SCALE)
                continue
            project.cost_total += out.cost
            job.status, job.cost, job.result, job.error = "succeeded", out.cost + out.recorded_cost, out.result, None
            job.duration_s = Decimal(str(round(time.monotonic() - started, 2)))
            job.vendor = STEPS[step][0]
            await session.commit()
            return True
    return False


async def _finish(step: str, pid: str, next_state: str | None) -> None:
    from app.pipeline.advance import advance

    async with session_maker()() as session:
        project = await session.get(Project, pid)
        assert project is not None
        if project.state != PREDECESSOR[step]:
            return
        if step in {"final_render", "merge_render"}:
            job = (
                (
                    await session.execute(
                        select(Job)
                        .where(Job.project_id == pid, Job.stage == step, Job.status == "succeeded")
                        .order_by(Job.created_at.desc())
                    )
                )
                .scalars()
                .first()
            )
            assert job is not None and job.result is not None
            problems = steps.quality_gate(job.result, len(steps.FORMATS))
            if problems:
                sm.fail(project, "Quality check failed: " + "; ".join(problems), retryable=False)
                await session.commit()
                await notify_owners(pid, "failed")
                return
        if next_state:
            sm.transition(project, next_state)
            if next_state == "final_ready":
                project.completed_at = datetime.now(UTC)
        await session.commit()
        if next_state == "final_ready":
            await notify_owners(pid, "render_ready")
        else:
            await advance(session, pid)
