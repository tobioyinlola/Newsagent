"""Which AI presenter looks a customer can choose, and which one a project ends up with."""

import time

from fastapi import HTTPException

from app.config import get_settings
from app.integrations import registry
from app.integrations.avatar.base import Presenter

TTL_S = 900
_cache: dict[str, tuple[float, list[Presenter]]] = {}


def reset() -> None:
    _cache.clear()


async def catalogue() -> list[Presenter]:
    """The primary avatar provider's looks, kept for 15 minutes (the account has hundreds; the vendor pages 50 at a time)."""
    provider = registry.get_avatar()
    hit = _cache.get(provider.name)
    if hit and time.monotonic() - hit[0] < TTL_S:
        return hit[1]
    looks = await provider.list_presenters()
    _cache[provider.name] = (time.monotonic(), looks)
    return looks


async def search(q: str = "", gender: str = "", limit: int = 48) -> list[Presenter]:
    q, gender = q.strip().lower(), gender.strip().lower()
    return [
        p for p in await catalogue() if (not q or q in p.name.lower()) and (not gender or p.gender.lower() == gender)
    ][:limit]


async def resolve(requested: str | None) -> str | None:
    """The presenter look to store on a new project. A chosen one must really exist; with none chosen the configured
    default is used; a real (non-demo) run with neither is refused rather than sent to the vendor without an avatar."""
    if requested:
        if requested not in {p.id for p in await catalogue()}:
            raise HTTPException(422, {"error": "unknown_presenter", "message": "That presenter isn't available."})
        return requested
    default = get_settings().heygen_default_avatar_id
    if default:
        return default
    if get_settings().use_mocks:
        return None
    raise HTTPException(422, {"error": "presenter_required", "message": "Choose a presenter for your video."})
