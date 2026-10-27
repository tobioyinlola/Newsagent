"""Sliding-window rate limiting. Memory for local/single instance; Redis when running several API instances."""

import hashlib
import logging
import time
import uuid
from collections import defaultdict, deque

from fastapi import HTTPException, Request

from app.config import get_settings

log = logging.getLogger("ratelimit")
_hits: dict[str, deque[float]] = defaultdict(deque)
_redis = None


def reset() -> None:
    _hits.clear()


def client_ip(request: Request) -> str:
    if get_settings().trust_proxy_headers:
        fwd = request.headers.get("x-forwarded-for", "")
        if fwd:
            return fwd.split(",")[0].strip()  # first hop = the real client; the proxy appends the rest
    return request.client.host if request.client else "?"


def identity(request: Request) -> str:
    auth = request.headers.get("authorization", "")
    return hashlib.sha256(auth.encode()).hexdigest()[:16] if auth else "anon"


async def _memory_hit(key: str, max_calls: int, per_s: int) -> bool:
    q = _hits[key]
    now = time.monotonic()
    while q and now - q[0] > per_s:
        q.popleft()
    if len(q) >= max_calls:
        return False
    q.append(now)
    return True


def _get_redis():
    global _redis
    if _redis is None:
        import redis.asyncio as aioredis

        _redis = aioredis.from_url(get_settings().redis_url)
    return _redis


async def _redis_hit(key: str, max_calls: int, per_s: int) -> bool:
    r = _get_redis()
    now = time.time()
    k = f"rl:{key}"
    pipe = r.pipeline()
    pipe.zremrangebyscore(k, 0, now - per_s)
    pipe.zcard(k)
    _, count = await pipe.execute()
    if count >= max_calls:
        return False
    pipe = r.pipeline()
    pipe.zadd(k, {uuid.uuid4().hex: now})
    pipe.expire(k, per_s + 1)
    await pipe.execute()
    return True


async def hit(key: str, max_calls: int, per_s: int) -> bool:
    """True if the call is allowed. If Redis is unreachable we fail OPEN (log loudly) rather than take the app down."""
    if get_settings().rate_limit_store == "redis":
        try:
            return await _redis_hit(key, max_calls, per_s)
        except Exception:  # noqa: BLE001
            log.exception("rate limiter backend unavailable; allowing request")
            return True
    return await _memory_hit(key, max_calls, per_s)


ALWAYS_LIMITED = {"webhook", "share-view", "share", "export", "account-delete", "checkout"}


def limit(name: str, max_calls: int, per_s: int):
    async def dep(request: Request) -> None:
        if name not in ALWAYS_LIMITED and not get_settings().enforce_limits:
            return
        for key in (f"{name}:u:{identity(request)}", f"{name}:ip:{client_ip(request)}"):
            if not await hit(key, max_calls, per_s):
                raise HTTPException(429, "Too many requests. Please slow down.")

    return dep
