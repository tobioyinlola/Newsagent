"""A gate in front of every writing call: a rush of people pressing "Continue" waits its turn at the model provider (and a busy answer
is retried after a short wait) instead of all arriving at once and being refused."""

import asyncio
import logging
import random
import weakref
from collections.abc import Awaitable, Callable

from app.config import get_settings
from app.integrations.errors import classify

log = logging.getLogger("llm")
RETRY = {"rate_limited", "temporary", "timeout", "busy"}
MAX_WAIT_S = 20.0
_sems: "weakref.WeakKeyDictionary[asyncio.AbstractEventLoop, asyncio.Semaphore]" = weakref.WeakKeyDictionary()


def _semaphore() -> asyncio.Semaphore:
    """One per event loop (each Celery task has its own loop, and a semaphore only works in the loop that made it)."""
    loop = asyncio.get_running_loop()
    sem = _sems.get(loop)
    if sem is None:
        sem = _sems[loop] = asyncio.Semaphore(max(1, get_settings().llm_max_concurrency))
    return sem


async def run(call: Callable[[], Awaitable[str]]) -> str:
    retries = max(0, get_settings().llm_retries)
    for attempt in range(retries + 1):
        try:
            async with _semaphore():  # the slot is given back while waiting to retry
                return await call()
        except Exception as e:  # noqa: BLE001
            c = classify(e)
            if attempt >= retries or c.category not in RETRY:
                raise
            wait = min(MAX_WAIT_S, max(c.retry_after or 0.0, 1.5 * 2**attempt) * random.uniform(0.8, 1.4))  # noqa: S311 (spread the retries)
            log.warning(
                "the writing provider was busy; trying again",
                extra={"category": c.category, "retry_in_s": round(wait, 1)},
            )
            await asyncio.sleep(wait)
    raise AssertionError("unreachable")
