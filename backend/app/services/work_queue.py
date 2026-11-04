"""One durable line for the slow, capacity-limited work: presenter clips and final renders.

With QUEUE_MODE=legacy (the default) none of this runs: steps go straight to the Celery workers as they always did.

With QUEUE_MODE=dispatcher a video joins a line (the work_queue table) and the dispatcher releases it, oldest first, only when
there is free capacity: a free renderer for a render, a free HeyGen slot for a presenter clip. Nothing is refused and nothing
fails because it waited: a video only fails from a real error. Rules:
  * first in, first out; a video keeps its original place when it moves to its next step or is put back after a crash;
  * at most one running item per business (workspace) per lane, so one big customer cannot take every slot;
  * an operator can move a video to the front, take it out, or pause a lane;
  * a released item that goes quiet (its worker died) is put back in line at its original place.
"""

import logging
import math
import statistics
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import VENDOR_POLICIES, get_settings
from app.db import session_maker
from app.models import Job, Project, SystemSetting, WorkItem
from app.models.base import new_id

log = logging.getLogger("work_queue")

AVATAR, RENDER = "avatar", "render"
LANES = (AVATAR, RENDER)
LANE_OF = {
    "anchor_render": AVATAR,
    "question_clips": AVATAR,
    "preview_render": RENDER,
    "final_render": RENDER,
    "merge_render": RENDER,
}
PAUSED_KEY = "queue_paused_lanes"
MIN_SAMPLES_FOR_ETA = 3


def enabled() -> bool:
    return get_settings().queue_mode == "dispatcher"


def max_busy_wait() -> timedelta:
    """How long a video may wait for a free vendor slot before it is reported as failed."""
    return timedelta(hours=get_settings().queue_max_wait_hours) if enabled() else timedelta(hours=3)


def slots(lane: str) -> int:
    """How many items of this lane may run at once."""
    s = get_settings()
    if lane == AVATAR:
        return max(1, VENDOR_POLICIES["avatar"].max_concurrency)
    if s.render_queue_slots > 0:
        return s.render_queue_slots
    from app.integrations.renderer.http import parse_renderer_urls

    n = len(parse_renderer_urls(s.renderer_urls, s.renderer_url)) or 1
    return max(1, n * max(1, s.render_jobs_concurrency))


def _aware(t: datetime | None) -> datetime | None:
    return t if t is None or t.tzinfo else t.replace(tzinfo=UTC)


async def submit(session: AsyncSession, step: str, project_id: str) -> None:
    """Put a video in line for `step` (or send it straight to the workers when the line is off or the step is not limited)."""
    from app.pipeline.queue import enqueue

    if not enabled() or step not in LANE_OF:
        enqueue(step, {"project_id": project_id})
        return
    project = await session.get(Project, project_id)
    if project is None:
        return
    lane = LANE_OF[step]
    item = (await session.execute(select(WorkItem).where(WorkItem.project_id == project_id))).scalar_one_or_none()
    if item is None:
        try:
            session.add(
                WorkItem(id=new_id(), project_id=project_id, workspace_id=project.workspace_id, lane=lane, step=step)
            )
            await session.commit()
        except IntegrityError:  # another process added it a moment ago: it is already in line
            await session.rollback()
    elif item.step != step:  # its next step: back in line, but at the place the video first took
        item.step, item.lane, item.state, item.dispatched_at = step, lane, "waiting", None
        await session.commit()
    try:
        await dispatch_once()
    except Exception:  # noqa: BLE001  the dispatcher runs again within seconds
        log.exception("dispatch after joining the line failed")


async def _lock(session: AsyncSession) -> None:
    """One dispatcher decides at a time (Postgres); on SQLite there is only ever one process."""
    if session.bind is not None and session.bind.dialect.name == "postgresql":
        await session.execute(select(func.pg_advisory_xact_lock(7_340_021)))


async def paused_lanes(session: AsyncSession) -> set[str]:
    row = await session.get(SystemSetting, PAUSED_KEY)
    lanes = set(row.value.get("lanes", [])) if row else set()
    from app.services.spend_guard import is_paused

    if await is_paused(session):  # the operator's emergency stop holds the line too, instead of failing everyone in it
        lanes |= set(LANES)
    return lanes


async def _reap(session: AsyncSession, now: datetime) -> None:
    """Drop items whose video has moved on (finished, failed, cancelled) and put back items whose worker went quiet."""
    from app.pipeline.runner import PREDECESSOR, lease_for

    for step, predecessor in PREDECESSOR.items():
        if step not in LANE_OF:
            continue
        gone = select(Project.id).where(Project.state != predecessor)
        await session.execute(delete(WorkItem).where(WorkItem.step == step, WorkItem.project_id.in_(gone)))
    grace = timedelta(seconds=get_settings().queue_dispatch_grace_s)
    running = (await session.execute(select(WorkItem).where(WorkItem.state == "running"))).scalars().all()
    for it in running:
        dispatched = _aware(it.dispatched_at)
        if dispatched and now - dispatched < grace:
            continue
        last = (
            await session.execute(
                select(func.max(Job.started_at)).where(Job.project_id == it.project_id, Job.stage == it.step)
            )
        ).scalar_one_or_none()
        last = _aware(last)
        if last and now - last < lease_for(it.step):
            continue  # its worker is still alive
        log.warning("a released job went quiet; back in line", extra={"project_id": it.project_id, "stage": it.step})
        it.state, it.dispatched_at, it.attempts = "waiting", None, it.attempts + 1
    await session.commit()


async def dispatch_once(now: datetime | None = None) -> int:
    """Release as many waiting items as there is free capacity for. Safe to run from several processes at once."""
    if not enabled():
        return 0
    from app.pipeline.queue import enqueue

    now = now or datetime.now(UTC)
    released: list[tuple[str, str, bool]] = []
    async with session_maker()() as s:
        await _lock(s)
        await _reap(s, now)
        paused = await paused_lanes(s)
        for lane in LANES:
            if lane in paused:
                continue
            running = (
                (
                    await s.execute(
                        select(WorkItem.workspace_id).where(WorkItem.lane == lane, WorkItem.state == "running")
                    )
                )
                .scalars()
                .all()
            )
            free = slots(lane) - len(running)
            if free <= 0:
                continue
            taken = set(running)  # one running item per business per lane
            waiting = (
                (
                    await s.execute(
                        select(WorkItem)
                        .where(WorkItem.lane == lane, WorkItem.state == "waiting")
                        .order_by(WorkItem.priority.desc(), WorkItem.enqueued_at, WorkItem.id)
                        .limit(free * 8 + 50)
                        .with_for_update(skip_locked=True)
                    )
                )
                .scalars()
                .all()
            )
            for it in waiting:
                if free <= 0:
                    break
                if it.workspace_id in taken:
                    continue
                taken.add(it.workspace_id)
                free -= 1
                waited = now - (_aware(it.enqueued_at) or now)
                first = it.attempts == 0
                it.state, it.dispatched_at = "running", now
                released.append((it.step, it.project_id, first and waited > timedelta(minutes=10)))
        await s.commit()
    for step, pid, was_waiting in released:
        enqueue(step, {"project_id": pid})
        if was_waiting and step in {"final_render", "merge_render"}:
            from app.services.notifications import notify_owners

            await notify_owners(pid, "render_started")
    return len(released)


async def kick() -> None:
    """A slot may just have been freed: release the next waiting item now rather than at the next 10-second tick."""
    if not enabled():
        return
    try:
        await dispatch_once()
    except Exception:  # noqa: BLE001
        log.exception("dispatch failed; it runs again shortly")


# ---------- what people see ----------
async def _typical_seconds(session: AsyncSession, step: str) -> float | None:
    since = datetime.now(UTC) - timedelta(days=7)
    rows = (
        (
            await session.execute(
                select(Job.duration_s)
                .where(
                    Job.stage == step, Job.status == "succeeded", Job.duration_s.is_not(None), Job.created_at > since
                )
                .order_by(Job.created_at.desc())
                .limit(50)
            )
        )
        .scalars()
        .all()
    )
    secs = [float(r) for r in rows if r is not None]
    return statistics.median(secs) if len(secs) >= MIN_SAMPLES_FOR_ETA else None


async def position_of(session: AsyncSession, project_id: str) -> dict | None:
    """Where this video is in line: {lane, state, position, eta_seconds}. None when it is not in line."""
    if not enabled():
        return None
    it = (await session.execute(select(WorkItem).where(WorkItem.project_id == project_id))).scalar_one_or_none()
    if it is None:
        return None
    if it.state == "running":
        return {"lane": it.lane, "state": "running", "position": 0, "eta_seconds": None}
    ahead = (
        await session.execute(
            select(func.count())
            .select_from(WorkItem)
            .where(
                WorkItem.lane == it.lane,
                WorkItem.state == "waiting",
                (WorkItem.priority > it.priority)
                | ((WorkItem.priority == it.priority) & (WorkItem.enqueued_at < it.enqueued_at))
                | (
                    (WorkItem.priority == it.priority)
                    & (WorkItem.enqueued_at == it.enqueued_at)
                    & (WorkItem.id < it.id)
                ),
            )
        )
    ).scalar_one()
    position = int(ahead) + 1
    typical = await _typical_seconds(session, it.step)
    eta = math.ceil(position / slots(it.lane)) * typical if typical else None
    return {"lane": it.lane, "state": "waiting", "position": position, "eta_seconds": int(eta) if eta else None}


async def lane_summary(session: AsyncSession) -> list[dict]:
    """For the back office: how many are waiting and running in each lane, and how long the oldest has waited."""
    now = datetime.now(UTC)
    out = []
    paused = await paused_lanes(session)
    for lane in LANES:
        rows = (
            await session.execute(
                select(WorkItem.state, func.count(), func.min(WorkItem.enqueued_at))
                .where(WorkItem.lane == lane)
                .group_by(WorkItem.state)
            )
        ).all()
        by = {state: (n, oldest) for state, n, oldest in rows}
        waiting_n, oldest = by.get("waiting", (0, None))
        oldest = _aware(oldest)
        step = "anchor_render" if lane == AVATAR else "final_render"
        out.append(
            {
                "lane": lane,
                "waiting": int(waiting_n),
                "running": int(by.get("running", (0, None))[0]),
                "slots": slots(lane),
                "oldest_wait_s": int((now - oldest).total_seconds()) if oldest else 0,
                "typical_s": await _typical_seconds(session, step),
                "paused": lane in paused,
            }
        )
    return out


async def set_lane_paused(session: AsyncSession, lane: str, paused: bool, by: str | None) -> None:
    row = await session.get(SystemSetting, PAUSED_KEY)
    lanes = set(row.value.get("lanes", [])) if row else set()
    lanes = lanes | {lane} if paused else lanes - {lane}
    if row is None:
        session.add(SystemSetting(key=PAUSED_KEY, value={"lanes": sorted(lanes)}, updated_by=by))
    else:
        row.value, row.updated_by, row.updated_at = {"lanes": sorted(lanes)}, by, datetime.now(UTC)
    await session.commit()


async def move_to_front(session: AsyncSession, project_id: str) -> bool:
    top = (await session.execute(select(func.max(WorkItem.priority)))).scalar_one() or 0
    done = await session.execute(
        update(WorkItem).where(WorkItem.project_id == project_id, WorkItem.state == "waiting").values(priority=top + 1)
    )
    await session.commit()
    return getattr(done, "rowcount", 0) == 1


async def remove(session: AsyncSession, project_id: str) -> None:
    await session.execute(delete(WorkItem).where(WorkItem.project_id == project_id))
    await session.commit()
