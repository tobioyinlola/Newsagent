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


def featured() -> list[Presenter]:
    """The house presenters, offered first. Configured, so a new one is an environment change, not a deploy."""
    out = []
    for item in get_settings().heygen_featured_presenters.split(";"):
        parts = [x.strip() for x in item.split("|")]
        if len(parts) >= 2 and parts[0]:
            out.append(
                Presenter(
                    parts[0], parts[1], parts[2] if len(parts) > 2 else "", f"/presenters/{parts[0]}.jpg", "landscape"
                )
            )
    return out


async def search(q: str = "", gender: str = "", limit: int = 48) -> list[Presenter]:
    q, gender = q.strip().lower(), gender.strip().lower()

    def ok(p: Presenter) -> bool:
        return (not q or q in p.name.lower()) and (not gender or p.gender.lower() == gender)

    house = [p for p in featured() if ok(p)]
    seen = {p.id for p in house}
    return (house + [p for p in await catalogue() if ok(p) and p.id not in seen])[:limit]


async def resolve(requested: str | None) -> str | None:
    """The presenter look to store on a new project. A chosen one must really exist; with none chosen the configured
    default is used; a real (non-demo) run with neither is refused rather than sent to the vendor without an avatar."""
    if requested:
        if requested not in {p.id for p in featured()} | {p.id for p in await catalogue()}:
            raise HTTPException(422, {"error": "unknown_presenter", "message": "That presenter isn't available."})
        return requested
    default = get_settings().heygen_default_avatar_id
    if default:
        return default
    if get_settings().use_mocks:
        return None
    raise HTTPException(422, {"error": "presenter_required", "message": "Choose a presenter for your video."})


# The sign-off every video ends with. It is the same words each time on purpose: the presenter clip for it is made once per
# presenter and voice, then reused by every later video at no vendor cost. (An owner who edits it pays for the new words.)
STANDARD_OUTRO = (
    "This is Cover Founder News. Want to join us as a guest on the show? Visit coverfounder.com to sign up and produce "
    "your news coverage for free. Until our next story, have a great day!"
)
