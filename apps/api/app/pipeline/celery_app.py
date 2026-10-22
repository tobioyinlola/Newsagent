import asyncio

from celery import Celery

from app.config import get_settings

celery_app = Celery("newsagent", broker=get_settings().redis_url, backend=get_settings().redis_url)
celery_app.conf.update(task_acks_late=True, worker_prefetch_multiplier=1, timezone="UTC")
celery_app.conf.beat_schedule = {
    "hourly": {"task": "jobs.hourly", "schedule": 3600.0},
    "daily": {"task": "jobs.daily", "schedule": 86400.0},
}


@celery_app.task(name="pipeline.run_step")
def run_step_task(step: str, payload: dict) -> None:
    from app.db import reset_engine
    from app.pipeline.runner import run_step

    async def _go() -> None:
        try:
            await run_step(step, payload)
        finally:
            await reset_engine()

    asyncio.run(_go())


def _run(coro_fn) -> dict:
    from app.db import reset_engine

    async def go() -> dict:
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
