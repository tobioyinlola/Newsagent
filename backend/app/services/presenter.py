"""The presenter-clip library: real TV-style presenter footage the operator uploads, mixed into merged videos."""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import PresenterClip

ROLES = ("intro", "cutaway", "outro")
# seconds a clip of each role may last: long enough to be a shot, short enough not to bury the founder
DURATION_LIMITS = {"intro": (3.0, 20.0), "cutaway": (2.0, 10.0), "outro": (3.0, 20.0)}
MIN_HEIGHT = 720
MAX_CUTAWAYS = 4


@dataclass
class Selection:
    intro: PresenterClip | None
    cutaways: list[PresenterClip]
    outro: PresenterClip | None

    @property
    def ids(self) -> list[str]:
        return [c.id for c in [self.intro, *self.cutaways, self.outro] if c is not None]


def check_media(role: str, duration_s: float, width: int | None, height: int | None) -> str | None:
    """Why a clip can't be used, or None when it is fine."""
    lo, hi = DURATION_LIMITS[role]
    if not (lo <= duration_s <= hi):
        return f"A {role} clip must last between {lo:g} and {hi:g} seconds (this one is {duration_s:.1f})."
    if not width or not height:
        return "That file has no video."
    if height < MIN_HEIGHT or width < height:
        return f"Clips must be landscape and at least {MIN_HEIGHT}p (this one is {width}×{height})."
    return None


async def select_clips(session: AsyncSession, project_id: str) -> Selection:
    """Pick this project's clips from the active library. Stable for a project (same id, same picks), varied across
    projects so videos don't all open the same way."""
    rows = (
        (
            await session.execute(
                select(PresenterClip)
                .where(PresenterClip.status == "clean", PresenterClip.active.is_(True))
                .order_by(PresenterClip.created_at, PresenterClip.id)
            )
        )
        .scalars()
        .all()
    )
    seed = (
        int(project_id[:8], 16) if all(c in "0123456789abcdef" for c in project_id[:8]) else sum(map(ord, project_id))
    )

    def pick(role: str) -> PresenterClip | None:
        pool = [c for c in rows if c.role == role]
        return pool[seed % len(pool)] if pool else None

    cut = [c for c in rows if c.role == "cutaway"]
    start = seed % len(cut) if cut else 0
    ordered = cut[start:] + cut[:start]
    return Selection(intro=pick("intro"), cutaways=ordered[:MAX_CUTAWAYS], outro=pick("outro"))
