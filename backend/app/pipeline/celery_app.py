import asyncio

from celery import Celery
from kombu import Queue

from app.config import get_settings
from app.pipeline.queue import LANES

celery_app = Celery("newsagent", broker=get_settings().redis_url, backend=get_settings().redis_url)
celery_app.conf.update(
    task_acks_late=True,
    task_reject_on_worker_lost=True,  # a worker killed mid-step (out of memory, deploy) puts the message back, not lost
    worker_prefetch_multiplier=1,  # a worker takes one message at a time, so a long step never hides others behind it
    worker_max_tasks_per_child=200,  # recycle processes so a slow leak can never grow without bound
    broker_connection_retry_on_startup=True,
    task_time_limit=3 * 3600 - 600,  # a hung step is killed; must stay below the visibility timeout
    timezone="UTC",
    task_default_queue="default",
    task_queues=[Queue(lane) for lane in LANES],
    task_routes={"jobs.*": {"queue": "default"}},
)
# With acks_late, a message a dead worker never acknowledged is redelivered after the visibility timeout. It must be LONGER
# than the slowest step (the avatar vendor's timeout is 15 min x 3 attempts), or a healthy long step is run twice.
celery_app.conf.broker_transport_options = {
    "visibility_timeout": 3 * 3600,
    "socket_timeout": 10,
    "socket_connect_timeout": 5,
    "retry_on_timeout": True,
    "health_check_interval": 30,
}
celery_app.conf.beat_schedule = {
    "sweep": {"task": "jobs.sweep", "schedule": 300.0},  # re-send work whose queue message was lost, every 5 minutes
    "hourly": {"task": "jobs.hourly", "schedule": 3600.0},
    "daily": {"task": "jobs.daily", "schedule": 86400.0},
}


def _fresh_providers() -> None:
    """Every task runs in its own event loop, and the vendor clients (httpx) are tied to the loop that created them. A client kept
    from an earlier task fails with "Event loop is closed" (take processing, emails, renders). Build them anew for each task."""
    from app.integrations import registry

    registry.reset_providers()


@celery_app.task(name="pipeline.run_step")
def run_step_task(step: str, payload: dict) -> None:
    from app.db import reset_engine
    from app.pipeline.queue import release_marker
    from app.pipeline.runner import run_step

    release_marker(step, payload)  # picked up: the same step may be queued again from now on

    async def _go() -> None:
        _fresh_providers()
        try:
            await run_step(step, payload)
        finally:
            await reset_engine()

    asyncio.run(_go())


def _run(coro_fn) -> dict:
    from app.db import reset_engine

    async def go() -> dict:
        _fresh_providers()
        try:
            return await coro_fn()
        finally:
            await reset_engine()

    return asyncio.run(go())


@celery_app.task(name="jobs.hourly")
def hourly() -> dict:
    from app.jobs import run_hourly

    return _run(run_hourly)


@celery_app.task(name="jobs.daily")
def daily() -> dict:
    from app.jobs import run_daily

    return _run(run_daily)


@celery_app.task(name="jobs.sweep")
def sweep() -> dict:
    from app.jobs import run_sweep

    return _run(run_sweep)
