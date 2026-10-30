"""Latest Stories: the public lists and pages, and the owner's control over their own story's page."""

from html import escape

from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse, RedirectResponse
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import Principal, current_principal
from app.config import get_settings
from app.db import get_session
from app.integrations import registry
from app.models import Asset, Project, Workspace
from app.schemas.api import PublicationOut, StoryCardOut, StoryPageOut, StoryPictureOut
from app.services import stories
from app.services.ratelimit import limit

router = APIRouter(tags=["stories"])


async def _assets(session: AsyncSession, project_id: str) -> list[Asset]:
    return list((await session.execute(select(Asset).where(Asset.project_id == project_id))).scalars().all())


@router.get(
    "/v1/public/stories", response_model=list[StoryCardOut], dependencies=[Depends(limit("public-stories", 120, 600))]
)
async def public_stories(
    limit_: int = Query(24, alias="limit", ge=1, le=60),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
) -> list[dict]:
    """The newest published stories, for the Latest Stories page and the home page row (no sign-in needed)."""
    rows = (
        await session.execute(
            select(Project, Workspace)
            .join(Workspace, Workspace.id == Project.workspace_id)
            .where(
                Project.state == "final_ready",
                Project.published_at.is_not(None),
                Workspace.suspended.is_(False),
                Workspace.share_disabled.is_(False),
                Workspace.deleted_at.is_(None),
            )
            .order_by(Project.published_at.desc())
            .offset(offset)
            .limit(limit_)
        )
    ).all()
    out = []
    for project, ws in rows:
        story = await stories.story_of(session, project.id)
        if not story:
            continue
        out.append(await stories.card(session, project, ws, story, await _assets(session, project.id)))
    return out


@router.get(
    "/v1/public/stories/{slug}", response_model=StoryPageOut, dependencies=[Depends(limit("public-story", 120, 600))]
)
async def public_story(slug: str, session: AsyncSession = Depends(get_session)) -> dict:
    project = (await session.execute(select(Project).where(Project.story_slug == slug))).scalar_one_or_none()
    gone = HTTPException(404, "This story isn't available")
    if project is None:
        raise gone
    ws = await session.get(Workspace, project.workspace_id)
    if not stories.listed(project, ws):
        raise gone
    story = await stories.story_of(session, project.id)
    assets = await _assets(session, project.id)
    # the Light file starts faster on a web page; fall back to the HD one
    video = next((a for a in assets if a.type == "render_light" and a.format == "16x9"), None) or next(
        (a for a in assets if a.type == "render" and a.format == "16x9"), None
    )
    if not story or video is None:
        raise gone
    storage = registry.get_storage()
    page = await stories.card(session, project, ws, story, assets)
    sections = [
        {"heading": s.get("heading", ""), "paragraphs": list(s.get("paragraphs", []))}
        for s in story.get("sections", [])
    ]
    pictures = [
        StoryPictureOut(
            url=storage.presign_get(i["key"], stories.PUBLIC_URL_TTL_S), caption=str(i.get("caption") or "")
        )
        for i in (project.broll or [])
        if i.get("key")
    ]
    return {
        **page,
        "dateline": story.get("dateline"),
        "sections": sections,
        "about": str(story.get("about") or ""),
        "pictures": pictures,
        "video_url": storage.presign_get(video.storage_key, stories.PUBLIC_URL_TTL_S),
        "disclosure": "The presenter is AI-generated, but the business story was recorded by real people.",
    }


async def _listed(session: AsyncSession, slug: str) -> tuple[Project, Workspace | None, dict, list[Asset]]:
    project = (await session.execute(select(Project).where(Project.story_slug == slug))).scalar_one_or_none()
    gone = HTTPException(404, "This story isn't available")
    if project is None:
        raise gone
    ws = await session.get(Workspace, project.workspace_id)
    story = await stories.story_of(session, project.id)
    if not stories.listed(project, ws) or not story:
        raise gone
    return project, ws, story, await _assets(session, project.id)


@router.get("/v1/public/stories/{slug}/image", dependencies=[Depends(limit("public-story", 120, 600))])
async def story_image(slug: str, session: AsyncSession = Depends(get_session)) -> RedirectResponse:
    """A steady address for a story's cover picture (the stored file's own link expires), for link previews."""
    _, _, _, assets = await _listed(session, slug)
    thumb = next((a for a in assets if a.type == "thumbnail"), None)
    if thumb is None:
        raise HTTPException(404, "No picture")
    return RedirectResponse(registry.get_storage().presign_get(thumb.storage_key, stories.PUBLIC_URL_TTL_S), 302)


@router.get(
    "/v1/public/stories/{slug}/preview",
    response_class=HTMLResponse,
    dependencies=[Depends(limit("public-story", 120, 600))],
)
async def story_preview(slug: str, session: AsyncSession = Depends(get_session)) -> HTMLResponse:
    """What WhatsApp, LinkedIn, X, Facebook and Slack read to draw a link preview. The site serves this page, instead of the app,
    to those crawlers only (see vercel.json); people always get the app."""
    project, ws, story, assets = await _listed(session, slug)
    base = get_settings().app_base_url.rstrip("/")
    url = f"{base}{stories.PATH_PREFIX}{slug}"
    title = escape(str(story.get("headline") or "Cover Founder News"), quote=True)
    desc = escape(str(story.get("dek") or ""), quote=True)
    has_image = any(a.type == "thumbnail" for a in assets)
    image = f"{base}/v1/public/stories/{slug}/image"
    tags = [
        ("property", "og:type", "article"),
        ("property", "og:site_name", "Cover Founder News"),
        ("property", "og:title", title),
        ("property", "og:description", desc),
        ("property", "og:url", url),
        ("name", "twitter:card", "summary_large_image" if has_image else "summary"),
        ("name", "twitter:title", title),
        ("name", "twitter:description", desc),
    ]
    if has_image:
        tags += [
            ("property", "og:image", image),
            ("property", "og:image:width", "1280"),
            ("property", "og:image:height", "720"),
            ("name", "twitter:image", image),
        ]
    meta = "\n".join(f'<meta {k}="{n}" content="{v}">' for k, n, v in tags)
    body = (
        f'<!doctype html><html lang="en"><head><meta charset="utf-8"><title>{title}</title>'
        f'<link rel="canonical" href="{url}">\n{meta}</head>'
        f'<body><h1>{title}</h1><p>{desc}</p><p><a href="{url}">Watch the story</a></p></body></html>'
    )
    return HTMLResponse(body)


async def _owned(session: AsyncSession, project_id: str, p: Principal) -> Project:
    project = await session.get(Project, project_id)
    if project is None or project.workspace_id != p.workspace.id:
        raise HTTPException(404, "Project not found")
    return project


def _out(project: Project, live: bool) -> PublicationOut:
    return PublicationOut(
        published=live,
        slug=project.story_slug,
        path=f"{stories.PATH_PREFIX}{project.story_slug}" if project.story_slug else None,
        published_at=project.published_at,
    )


@router.get("/v1/projects/{project_id}/publication", response_model=PublicationOut)
async def publication(
    project_id: str, p: Principal = Depends(current_principal), session: AsyncSession = Depends(get_session)
) -> PublicationOut:
    """Where this video's story is published. A finished video that was never published (made before Latest Stories) is
    published the first time its owner looks."""
    project = await _owned(session, project_id, p)
    if project.state == "final_ready" and project.story_slug is None:
        await stories.publish(session, project)
        await session.commit()
    ws = await session.get(Workspace, project.workspace_id)
    return _out(project, stories.listed(project, ws))
