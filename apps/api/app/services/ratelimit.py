"""Sliding-window limiter. In-memory for the pilot (single API instance); move to Redis before scaling out."""

import time
from collections import defaultdict, deque

from fastapi import HTTPException, Request

_hits: dict[str, deque[float]] = defaultdict(deque)


def reset() -> None:
    _hits.clear()


def limit(name: str, max_calls: int, per_s: int):
    async def dep(request: Request) -> None:
        ident = request.headers.get("authorization", "")[-24:] or (request.client.host if request.client else "?")
        for key in (f"{name}:{ident}", f"{name}:ip:{request.client.host if request.client else '?'}"):
            q = _hits[key]
            now = time.monotonic()
            while q and now - q[0] > per_s:
                q.popleft()
            if len(q) >= max_calls:
                raise HTTPException(429, "Too many requests. Please slow down.")
            q.append(now)

    return dep
