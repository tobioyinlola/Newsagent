import asyncio

from celery import Celery

from app.config import get_settings

celery_app = Celery("newsagent", broker=get_settings().redis_url, backend=get_settings().redis_url)
celery_app.conf.update(task_acks_late=True, worker_prefetch_multiplier=1, timezone="UTC")
# With acks_late, a message a dead worker never acknowledged is redelivered after the visibility timeout. It must be LONGER
# than the slowest step (the avatar vendor's timeout is 15 min x 3 attempts), or a healthy long step is run twice.
celery_app.conf.broker_transport_options = {"visibility_timeout": 3 * 3600}
celery_app.conf.beat_schedule = {
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
    from app.pipeline.runner import run_step

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
