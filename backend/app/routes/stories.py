"""Latest Stories: the public lists and pages, and the owner's control over their own story's page."""

import asyncio
import logging
import time
from html import escape

import httpx
from fastapi import APIRouter, Depends, HTTPException, Query
from fastapi.responses import HTMLResponse, RedirectResponse, Response
from sqlalchemy import exists, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import Principal, current_principal
from app.config import get_settings
from app.db import get_session
from app.integrations import registry
from app.models import Asset, NewsStory, Project, Workspace
from app.schemas.api import PublicationOut, StoryCardOut, StoryPageOut, StoryPictureOut
from app.services import news_desk_public, stories
from app.services.ratelimit import limit

router = APIRouter(tags=["stories"])
log = logging.getLogger("stories")

# Link previews: WhatsApp drops pictures over about 300 KB, so the picture shared with a link is a 1200x630 JPEG kept well under that.
SOCIAL_W, SOCIAL_H, SOCIAL_MAX_BYTES = 1200, 630, 280_000
_social_cache: dict[str, tuple[float, bytes]] = {}


async def _social_jpeg(source_url: str) -> bytes | None:
    """The cover picture as a small 1200x630 JPEG for link previews, or None if it can't be made (the caller then redirects)."""
    try:
        async with httpx.AsyncClient(timeout=15, follow_redirects=True) as c:
            r = await c.get(source_url)
            r.raise_for_status()
        if len(r.content) > 20 * 1024 * 1024:
            return None
        for quality in (5, 9, 14, 20):
            proc = await asyncio.create_subprocess_exec(
                "ffmpeg", "-v", "error", "-i", "pipe:0",
                "-vf", f"scale={SOCIAL_W}:{SOCIAL_H}:force_original_aspect_ratio=increase,crop={SOCIAL_W}:{SOCIAL_H}",
                "-frames:v", "1", "-q:v", str(quality), "-f", "image2pipe", "-vcodec", "mjpeg", "pipe:1",
                stdin=asyncio.subprocess.PIPE, stdout=asyncio.subprocess.PIPE, stderr=asyncio.subprocess.DEVNULL,
            )  # fmt: skip
            out, _ = await asyncio.wait_for(proc.communicate(r.content), timeout=25)
            if proc.returncode == 0 and out and len(out) <= SOCIAL_MAX_BYTES:
                return out
    except Exception as e:  # a preview picture must never break the link; the plain redirect still works
        log.warning("preview picture not made: %s", e)
    return None


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
                # CF Featured Stories is reserved for customer-produced videos.
                # Require the completed widescreen render here so unpublished or
                # text-only projects cannot enter the feed.
                exists(
                    select(Asset.id).where(
                        Asset.project_id == Project.id,
                        Asset.type == "render",
                        Asset.format == "16x9",
                    )
                ),
            )
            .order_by(Project.published_at.desc())
            .limit(limit_ + offset)
        )
    ).all()
    out = []
    for project, ws in rows:
        story = await stories.story_of(session, project.id)
        if not story:
            continue
        out.append(await stories.card(session, project, ws, story, await _assets(session, project.id)))
    out.sort(key=lambda item: item["published_at"].isoformat(), reverse=True)
    return out[offset : offset + limit_]


@router.get(
    "/v1/public/cf-news",
    response_model=list[StoryCardOut],
    dependencies=[Depends(limit("public-stories", 120, 600))],
)
async def cf_news(
    limit_: int = Query(24, alias="limit", ge=1, le=60),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
):
    rows = (
        await session.execute(
            select(NewsStory)
            .where(NewsStory.status == "published", NewsStory.published_data.is_not(None))
            .order_by(NewsStory.published_at.desc())
            .offset(offset)
            .limit(limit_)
        )
    ).scalars()
    return [await news_desk_public.card(session, row) for row in rows]


@router.get(
    "/v1/public/technology-news",
    response_model=list[StoryCardOut],
    include_in_schema=False,
    dependencies=[Depends(limit("public-stories", 120, 600))],
)
async def technology_news_legacy(
    limit_: int = Query(24, alias="limit", ge=1, le=60),
    offset: int = Query(0, ge=0),
    session: AsyncSession = Depends(get_session),
):
    return await cf_news(limit_, offset, session)


@router.get(
    "/v1/public/stories/{slug}", response_model=StoryPageOut, dependencies=[Depends(limit("public-story", 120, 600))]
)
async def public_story(slug: str, session: AsyncSession = Depends(get_session)) -> dict:
    editorial = await news_desk_public.find(session, slug)
    if editorial:
        return await news_desk_public.page(session, editorial)
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
async def story_image(slug: str, session: AsyncSession = Depends(get_session)) -> Response:
    """A steady address for a story's cover picture (the stored file's own link expires), for link previews.
    Served as a small 1200x630 JPEG so WhatsApp and the others will show it."""
    editorial = await news_desk_public.find(session, slug)
    if editorial:
        pictures = await news_desk_public.images(session, editorial)
        if not pictures:
            raise HTTPException(404, "No picture")
        source = pictures[0]["url"]
    else:
        _, _, _, assets = await _listed(session, slug)
        thumb = next((a for a in assets if a.type == "thumbnail"), None)
        if thumb is None:
            raise HTTPException(404, "No picture")
        source = registry.get_storage().presign_get(thumb.storage_key, stories.PUBLIC_URL_TTL_S)
    cached = _social_cache.get(slug)
    if cached and cached[0] > time.monotonic():
        jpeg: bytes | None = cached[1]
    else:
        jpeg = await _social_jpeg(source)
        if jpeg:
            if len(_social_cache) >= 64:
                _social_cache.clear()
            _social_cache[slug] = (time.monotonic() + 3600, jpeg)
    if jpeg is None:
        return RedirectResponse(source, 302)
    return Response(jpeg, media_type="image/jpeg", headers={"Cache-Control": "public, max-age=3600"})


def _preview_html(
    *, title: str, desc: str, url: str, image: str | None, alt: str, published: str | None
) -> HTMLResponse:
    """The small page link-preview bots read. Title and description come first; every value is escaped."""
    t, d, u = escape(title, quote=True), escape(desc, quote=True), escape(url, quote=True)
    tags = [
        ("property", "og:type", "article"),
        ("property", "og:site_name", "Cover Founder News"),
        ("property", "og:locale", "en_US"),
        ("property", "og:title", t),
        ("property", "og:description", d),
        ("property", "og:url", u),
        ("name", "description", d),
        ("name", "twitter:card", "summary_large_image" if image else "summary"),
        ("name", "twitter:title", t),
        ("name", "twitter:description", d),
    ]
    if published:
        tags.append(("property", "article:published_time", published))
    if image:
        i = escape(image, quote=True)
        tags += [
            ("property", "og:image", i),
            ("property", "og:image:secure_url", i),
            ("property", "og:image:type", "image/jpeg"),
            ("property", "og:image:width", str(SOCIAL_W)),
            ("property", "og:image:height", str(SOCIAL_H)),
            ("property", "og:image:alt", escape(alt, quote=True)),
            ("name", "twitter:image", i),
            ("name", "twitter:image:alt", escape(alt, quote=True)),
        ]
    meta = "\n".join(f'<meta {k}="{n}" content="{v}">' for k, n, v in tags)
    body = (
        f'<!doctype html><html lang="en"><head><meta charset="utf-8"><title>{t}</title>'
        f'<link rel="canonical" href="{u}">\n{meta}</head>'
        f'<body><h1>{t}</h1><p>{d}</p><p><a href="{u}">Watch the story</a></p></body></html>'
    )
    return HTMLResponse(body)


@router.api_route(
    "/v1/public/stories/{slug}/preview",
    methods=["GET", "HEAD"],  # some crawlers ask with HEAD first
    response_class=HTMLResponse,
    dependencies=[Depends(limit("public-story", 120, 600))],
)
async def story_preview(slug: str, session: AsyncSession = Depends(get_session)) -> HTMLResponse:
    """What WhatsApp, LinkedIn, X, Facebook and Slack read to draw a link preview. The site serves this page, instead of the app,
    to those crawlers only (see vercel.json); people always get the app."""
    base = get_settings().app_base_url.rstrip("/")
    url = f"{base}{stories.PATH_PREFIX}{slug}"
    image = f"{base}/v1/public/stories/{slug}/image"
    editorial = await news_desk_public.find(session, slug)
    if editorial:
        data = editorial.published_data or {}
        has_image = bool(await news_desk_public.images(session, editorial))
        published = getattr(editorial, "published_at", None)
        return _preview_html(
            title=str(data.get("headline") or "Cover Founder News"),
            desc=str(data.get("summary") or ""),
            url=f"{base}{stories.PATH_PREFIX}{editorial.slug}",
            image=image if has_image else None,
            alt=str(data.get("headline") or "Cover Founder News"),
            published=published.isoformat() if published else None,
        )
    project, ws, story, assets = await _listed(session, slug)
    headline = str(story.get("headline") or "Cover Founder News")
    published = project.published_at
    return _preview_html(
        title=headline,
        desc=str(story.get("dek") or ""),
        url=url,
        image=image if any(a.type == "thumbnail" for a in assets) else None,
        alt=headline,
        published=published.isoformat() if published else None,
    )


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
