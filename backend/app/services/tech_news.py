"""Today's tech headlines for the ticker, after the video's own lines (news-channel style). Read from the Hacker News API
(free, public, no key). Only headlines are used, never article text. Best effort: if the feed is slow or down, the ticker
simply carries the video's own lines."""

import asyncio
import logging
import time

import httpx

from app.config import get_settings
from app.services.safety import find_banned

log = logging.getLogger("tech_news")
API = "https://hacker-news.firebaseio.com/v0"
CACHE_S = 1800
_cache: tuple[float, list[str]] | None = None


def _ok(title: str) -> bool:
    t = title.strip()
    return (
        12 <= len(t) <= 100
        and not t.lower().startswith(("ask hn", "show hn", "tell hn", "launch hn"))
        and not find_banned(t)
    )


async def headlines(limit: int = 6) -> list[str]:
    global _cache
    s = get_settings()
    if s.use_mocks or not s.ticker_tech_news:
        return []
    if _cache and time.monotonic() - _cache[0] < CACHE_S:
        return _cache[1][:limit]
    try:
        async with httpx.AsyncClient(base_url=API, timeout=6) as c:
            ids = (await c.get("/topstories.json")).json()[:30]
            items = await asyncio.gather(*(c.get(f"/item/{i}.json") for i in ids), return_exceptions=True)
        titles = []
        for r in items:
            if isinstance(r, httpx.Response) and r.status_code == 200:
                title = str((r.json() or {}).get("title") or "")
                if _ok(title):
                    titles.append(title.strip())
        _cache = (time.monotonic(), titles)
        return titles[:limit]
    except Exception:  # noqa: BLE001 - the ticker never blocks a render
        log.warning("tech headlines unavailable; the ticker uses the video's own lines")
        return []
