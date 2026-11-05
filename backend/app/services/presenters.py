"""Which AI presenter looks a customer can choose, and which one a project ends up with."""

import time

from fastapi import HTTPException

from app.config import get_settings
from app.integrations import registry
from app.integrations.avatar.base import Presenter
from app.video_rules import value as rule_value

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
    """The house presenters, offered first. Configured, so a new one is an environment change, not a deploy.
    Each entry is `id|name|gender|voice_id|picture` separated by `;`; only id and name are required. The voice is this presenter's own
    (e.g. a female African-English voice); the picture is a file name in the site's /presenters folder (default `<id>.jpg`).

    HEYGEN_FEATURED_PRESENTERS is the original list: only its first presenter is pickable, the rest show as "coming soon".
    HEYGEN_EXTRA_PRESENTERS are added after it and are all pickable. The default presenter (HEYGEN_DEFAULT_AVATAR_ID) is always pickable
    and is listed first."""
    st = get_settings()
    default = st.heygen_default_avatar_id
    out: list[Presenter] = []
    for group, live in ((st.heygen_featured_presenters, False), (st.heygen_extra_presenters, True)):
        for n, item in enumerate(group.split(";")):
            parts = [x.strip() for x in item.split("|")]
            if len(parts) >= 2 and parts[0]:
                picture = parts[4] if len(parts) > 4 and parts[4] else f"{parts[0]}.jpg"
                out.append(
                    Presenter(
                        parts[0],
                        parts[1],
                        parts[2] if len(parts) > 2 else "",
                        f"/presenters/{picture}",
                        "landscape",
                        soon=not (live or (n == 0 and not out) or parts[0] == default),
                        voice_id=parts[3] if len(parts) > 3 else "",
                    )
                )
    out.sort(key=lambda p: p.id != default)  # the default first (a stable sort: the others keep their order)
    return out


def own_voice(avatar_id: str, required_gender: str | None = None) -> str | None:
    """A house presenter's own voice, when it has one (and, if a gender is required, when she or he is that gender)."""
    for p in featured():
        if p.id == avatar_id and p.voice_id:
            return p.voice_id if not required_gender or p.gender.lower() == required_gender else None
    return None


async def search(q: str = "", gender: str = "", limit: int = 48) -> list[Presenter]:
    q, gender = q.strip().lower(), gender.strip().lower()

    def ok(p: Presenter) -> bool:
        return (not q or q in p.name.lower()) and (not gender or p.gender.lower() == gender)

    house = [p for p in featured() if ok(p)]
    seen = {p.id for p in house}
    from dataclasses import replace

    rest = [replace(p, soon=True) for p in await catalogue() if ok(p) and p.id not in seen]  # the vendor's catalogue: shown, not yet pickable
    if not featured() and rest:  # no house presenters set up: the first look is the default, as it always was
        rest[0] = replace(rest[0], soon=False)
    return (house + rest)[:limit]


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
STANDARD_OUTRO: str = rule_value("BIV-SCR-014")  # the sign-off (Video Rulebook v4)
