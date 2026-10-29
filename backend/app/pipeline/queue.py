"""Thin queue interface so Celery can be swapped (e.g. for Temporal) without touching business logic.

Work is split into LANES so a slow job can never hold up a quick one: a founder's recording is processed within seconds even
while presenter clips and long renders are in progress. Each lane has its own worker pool (see start.sh), so each can be sized
and scaled on its own.
"""

import asyncio
import logging
from abc import ABC, abstractmethod

from app.config import get_settings

log = logging.getLogger("queue")

# lane -> what runs there
INTERACTIVE, AVATAR, RENDER, DEFAULT = "interactive", "avatar", "render", "default"
LANES = (INTERACTIVE, AVATAR, RENDER, DEFAULT)
STEP_LANE = {
    "process_take": INTERACTIVE,  # a person is waiting on the page for this
    "anchor_render": AVATAR,  # minutes of polling a vendor
    "question_clips": AVATAR,
    "preview_render": RENDER,  # minutes of waiting on the renderer
    "final_render": RENDER,
    "merge_render": RENDER,
}
DEDUPE_FLOOR_S = 900  # a queued marker outlives its message by this much; shorter than the stuck-project sweep, so a lost message is re-sent


def lane_for(step: str) -> str:
    return STEP_LANE.get(step, DEFAULT)


def dedupe_key(step: str, payload: dict) -> str | None:
    ident = payload.get("project_id") or payload.get("take_id")
    return f"q:{step}:{ident}" if ident else None


class Queue(ABC):
    @abstractmethod
    def enqueue(self, step: str, payload: dict, delay: float = 0.0) -> None: ...


class InlineQueue(Queue):
    """Runs steps as asyncio tasks in-process. Local development and tests only."""

    def __init__(self) -> None:
        self.tasks: set[asyncio.Task] = set()

    def enqueue(self, step: str, payload: dict, delay: float = 0.0) -> None:
        from app.pipeline.runner import run_step

        async def go() -> None:
            if delay > 0:
                await asyncio.sleep(delay)
            await run_step(step, payload)

        t = asyncio.get_running_loop().create_task(go())
        self.tasks.add(t)
        t.add_done_callback(self.tasks.discard)

    async def drain(self) -> None:
        while self.tasks:
            await asyncio.gather(*list(self.tasks))


_sync_redis = None


def _redis():
    global _sync_redis
    if _sync_redis is None:
        import redis

        _sync_redis = redis.Redis.from_url(
            get_settings().redis_url, socket_timeout=2, socket_connect_timeout=2, decode_responses=True
        )
    return _sync_redis


def release_marker(step: str, payload: dict) -> None:
    """A worker calls this when it picks the message up, so the same step can be queued again from then on."""
    key = dedupe_key(step, payload)
    if key:
        try:
            _redis().delete(key)
        except Exception:  # noqa: BLE001  the marker expires on its own
            pass


class CeleryQueue(Queue):
    def enqueue(self, step: str, payload: dict, delay: float = 0.0) -> None:
        """Never raises: if the broker is down the work is not lost, because the stuck-project sweep re-sends it within
        minutes (the caller has already committed the state change that makes the project 'due')."""
        from app.pipeline.celery_app import celery_app

        key = dedupe_key(step, payload)
        if key:
            try:
                # the same step for the same project/take already waiting in line: one message is enough
                if not _redis().set(key, "1", nx=True, ex=int(delay) + DEDUPE_FLOOR_S):
                    return
            except Exception:  # noqa: BLE001  without Redis we may queue a duplicate, which the runner tolerates
                key = None
        try:
            celery_app.send_task(
                "pipeline.run_step",
                args=[step, payload],
                queue=lane_for(step),
                countdown=delay or None,
                retry=True,
                retry_policy={"max_retries": 3, "interval_start": 0.2, "interval_step": 0.4, "interval_max": 2},
            )
        except Exception:  # noqa: BLE001
            log.exception("could not queue %s; the sweep will re-send it", step, extra={"stage": step})
            if key:
                release_marker(step, payload)


_queue: Queue | None = None


def get_queue() -> Queue:
    global _queue
    if _queue is None:
        _queue = CeleryQueue() if get_settings().queue_backend == "celery" else InlineQueue()
    return _queue


def set_queue(q: Queue) -> None:
    global _queue
    _queue = q


def enqueue(step: str, payload: dict, delay: float = 0.0) -> None:
    get_queue().enqueue(step, payload, delay)


async def lane_depths() -> dict[str, int]:
    """Messages waiting in each lane (Redis list lengths), for the readiness check and the operator console."""
    import redis.asyncio as aioredis

    r = aioredis.from_url(get_settings().redis_url, socket_timeout=2, socket_connect_timeout=2)
    try:
        return {lane: int(await r.llen(lane)) for lane in LANES}
    finally:
        await r.aclose()
