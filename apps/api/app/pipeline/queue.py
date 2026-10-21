"""Thin queue interface so Celery can be swapped (e.g. for Temporal) without touching business logic."""

import asyncio
from abc import ABC, abstractmethod

from app.config import get_settings


class Queue(ABC):
    @abstractmethod
    def enqueue(self, step: str, payload: dict) -> None: ...


class InlineQueue(Queue):
    """Runs steps as asyncio tasks in-process. Local development and tests only."""

    def __init__(self) -> None:
        self.tasks: set[asyncio.Task] = set()

    def enqueue(self, step: str, payload: dict) -> None:
        from app.pipeline.runner import run_step

        t = asyncio.get_running_loop().create_task(run_step(step, payload))
        self.tasks.add(t)
        t.add_done_callback(self.tasks.discard)

    async def drain(self) -> None:
        while self.tasks:
            await asyncio.gather(*list(self.tasks))


class CeleryQueue(Queue):
    def enqueue(self, step: str, payload: dict) -> None:
        from app.pipeline.celery_app import celery_app

        celery_app.send_task("pipeline.run_step", args=[step, payload])


_queue: Queue | None = None


def get_queue() -> Queue:
    global _queue
    if _queue is None:
        _queue = CeleryQueue() if get_settings().queue_backend == "celery" else InlineQueue()
    return _queue


def set_queue(q: Queue) -> None:
    global _queue
    _queue = q


def enqueue(step: str, payload: dict) -> None:
    get_queue().enqueue(step, payload)
