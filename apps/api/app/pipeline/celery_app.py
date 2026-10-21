import asyncio

from celery import Celery

from app.config import get_settings

celery_app = Celery("newsagent", broker=get_settings().redis_url, backend=get_settings().redis_url)
celery_app.conf.update(task_acks_late=True, worker_prefetch_multiplier=1, timezone="UTC")
celery_app.conf.beat_schedule = {}  # periodic jobs (founder reminders, retention) arrive in Phase 2/3


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
