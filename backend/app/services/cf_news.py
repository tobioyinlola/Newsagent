"""The scrolling ticker: news from the businesses on Cover Founder. After a video's own lines, the ticker carries the headlines of
other businesses' published stories (a finished video with a live share link, from a workspace that allows sharing), newest first.
A business that never shared its video is never named in anyone else's ticker."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Project, ScriptVersion, ShareLink, Workspace
from app.services.safety import find_banned

LIMIT = 8


def _ok(headline: str) -> bool:
    return 8 <= len(headline.strip()) <= 100 and not find_banned(headline)


async def ticker_items(session: AsyncSession, *, exclude_project: str | None = None, limit: int = LIMIT) -> list[str]:
    rows = (
        await session.execute(
            select(Project.id)
            .join(ShareLink, ShareLink.project_id == Project.id)
            .join(Workspace, Workspace.id == Project.workspace_id)
            .where(
                Project.state == "final_ready",
                ShareLink.revoked_at.is_(None),
                Workspace.suspended.is_(False),
                Workspace.share_disabled.is_(False),
                Project.id != (exclude_project or ""),
            )
            .order_by(Project.created_at.desc())
            .limit(limit * 3)
        )
    ).scalars()
    out: list[str] = []
    for pid in rows:
        sv = (
            (
                await session.execute(
                    select(ScriptVersion)
                    .where(ScriptVersion.project_id == pid, ScriptVersion.story.is_not(None))
                    .order_by(ScriptVersion.version.desc())
                )
            )
            .scalars()
            .first()
        )
        headline = str((sv.story or {}).get("headline") or "").strip() if sv else ""
        if headline and _ok(headline) and headline not in out:
            out.append(headline)
        if len(out) >= limit:
            break
    return [f"ON COVER FOUNDER: {h}" for h in out]
