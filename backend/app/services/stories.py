"""Latest Stories: every finished video with a written story gets a public page, made automatically.

The page shows the video and the press release (without the media contact). The owner can take it down and put it back; a
workspace an operator has suspended or switched off sharing for is never shown. The page address is made once from the headline
and kept (`/latest-stories/<slug>`), so a link that has been shared keeps working.
"""

import re
import unicodedata
from datetime import UTC, datetime

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations import registry
from app.models import Asset, Project, ScriptVersion, Workspace
from app.services.industries import INDUSTRIES

PUBLIC_URL_TTL_S = 6 * 3600  # media links on the public pages; fresh ones are made on every request
PATH_PREFIX = "/latest-stories/"


def slugify(text: str, limit: int = 70) -> str:
    plain = unicodedata.normalize("NFKD", text).encode("ascii", "ignore").decode()
    words = re.sub(r"[^a-z0-9]+", "-", plain.lower()).strip("-")
    if len(words) > limit:
        words = words[:limit].rsplit("-", 1)[0] or words[:limit]
    return words


def make_slug(headline: str, company: str, project_id: str) -> str:
    return f"{slugify(headline or company or 'story')}-{project_id[:6]}"


async def story_of(session: AsyncSession, project_id: str) -> dict | None:
    """The written story of the version the video was made from (the latest that has one)."""
    sv = (
        (
            await session.execute(
                select(ScriptVersion)
                .where(ScriptVersion.project_id == project_id, ScriptVersion.story.is_not(None))
                .order_by(ScriptVersion.version.desc())
            )
        )
        .scalars()
        .first()
    )
    return sv.story if sv is not None else None


def listed(project: Project, ws: Workspace | None) -> bool:
    """May this project's page be shown to the public right now?"""
    return (
        project.state == "final_ready"
        and project.story_slug is not None
        and project.published_at is not None
        and ws is not None
        and not ws.suspended
        and not ws.share_disabled
        and ws.deleted_at is None
    )


async def publish(session: AsyncSession, project: Project, *, force: bool = False) -> bool:
    """Make the page for a finished video. Done once, automatically: a story the owner has since taken down stays down unless
    `force` (the owner asking). Returns whether the page is live afterwards."""
    if project.state != "final_ready":
        return False
    story = await story_of(session, project.id)
    if not story:
        return False  # no written story, nothing to publish (the original script-first videos)
    ws = await session.get(Workspace, project.workspace_id)
    if ws is None or ws.suspended or ws.share_disabled:
        return False
    if project.story_slug is None:
        project.story_slug = make_slug(
            str(story.get("headline") or ""), str(story.get("company") or ws.name), project.id
        )
        project.published_at = datetime.now(UTC)
    elif project.published_at is None and force:
        project.published_at = datetime.now(UTC)
    return project.published_at is not None


def unpublish(project: Project) -> None:
    project.published_at = None


def industry_label(ws: Workspace | None) -> str | None:
    if ws is None or not ws.industry:
        return None
    if ws.industry == "other":
        return (ws.industry_other or "").strip() or INDUSTRIES["other"][0]
    return INDUSTRIES.get(ws.industry, (ws.industry, ""))[0]


async def card(session: AsyncSession, project: Project, ws: Workspace | None, story: dict, assets: list[Asset]) -> dict:
    storage = registry.get_storage()
    video = next((a for a in assets if a.type == "render" and a.format == "16x9"), None)
    thumb = next((a for a in assets if a.type == "thumbnail"), None)
    return {
        "slug": project.story_slug,
        "title": str(story.get("headline") or ""),
        "summary": str(story.get("dek") or ""),
        "company": str(story.get("company") or (ws.name if ws else "")),
        "industry": industry_label(ws),
        "published_at": project.published_at,
        "duration_s": float(video.duration) if video is not None and video.duration is not None else None,
        "thumbnail_url": storage.presign_get(thumb.storage_key, PUBLIC_URL_TTL_S) if thumb else None,
    }
