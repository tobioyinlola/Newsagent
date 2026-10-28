import asyncio
import hashlib
import json
import secrets

from fastapi import APIRouter, Depends, HTTPException
from fastapi.responses import StreamingResponse
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import Principal, current_principal
from app.config import get_settings
from app.db import get_session, session_maker
from app.integrations import registry
from app.models import Asset, Job, Project, ScriptVersion, ShareLink, Workspace
from app.models.base import utcnow
from app.schemas.api import (
    CaptionsOut,
    CostLine,
    CostsOut,
    DownloadItem,
    DownloadsOut,
    ProjectOut,
    ShareCreated,
    SharePublic,
)
from app.services.captions import DISCLOSURE, suggested_captions
from app.services.ratelimit import limit

router = APIRouter(tags=["delivery"])
SIGNED_URL_TTL_S = 900
TERMINAL = {"final_ready", "failed", "limit_reached", "cancelled"}
SSE_POLL_S = 1.0  # tests shorten this
SSE_MAX_S = 600


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


async def _owned(session: AsyncSession, project_id: str, p: Principal) -> Project:
    project = await session.get(Project, project_id)
    if project is None or project.workspace_id != p.workspace.id:
        raise HTTPException(404, "Project not found")
    return project


async def _assets(session: AsyncSession, project_id: str) -> list[Asset]:
    return list((await session.execute(select(Asset).where(Asset.project_id == project_id))).scalars().all())


def _filename(a: Asset) -> str:
    return {
        "render": f"video-{a.format}.mp4",
        "preview": "preview.mp4",
        "thumbnail": "thumbnail.png",
        "caption": "captions.srt",
    }.get(a.type, a.storage_key.rsplit("/", 1)[-1])


async def _hook(session: AsyncSession, project_id: str) -> tuple[str, str]:
    script = (
        (
            await session.execute(
                select(ScriptVersion)
                .where(ScriptVersion.project_id == project_id, ScriptVersion.approved.is_(True))
                .order_by(ScriptVersion.version.desc())
            )
        )
        .scalars()
        .first()
    )
    if script is None:
        return "", ""
    first = script.segments[0]["text"] if script.segments else ""
    company = (script.lower_thirds[0].get("title") if script.lower_thirds else "") or ""
    return company, first


@router.get("/v1/projects", response_model=list[ProjectOut])
async def list_projects(
    p: Principal = Depends(current_principal), session: AsyncSession = Depends(get_session)
) -> list[Project]:
    rows = await session.execute(
        select(Project).where(Project.workspace_id == p.workspace.id).order_by(Project.created_at.desc()).limit(100)
    )
    return list(rows.scalars().all())


@router.get("/v1/projects/{project_id}/downloads", response_model=DownloadsOut)
async def downloads(
    project_id: str, p: Principal = Depends(current_principal), session: AsyncSession = Depends(get_session)
) -> DownloadsOut:
    project = await _owned(session, project_id, p)
    storage = registry.get_storage()
    items = [
        DownloadItem(
            type=a.type,
            format=a.format,
            filename=_filename(a),
            url=storage.presign_get(a.storage_key, SIGNED_URL_TTL_S),
            expires_in_s=SIGNED_URL_TTL_S,
        )
        for a in await _assets(session, project_id)
        if a.type in {"render", "preview", "thumbnail", "caption"}
        and (project.state == "final_ready" or a.type == "preview")
    ]
    return DownloadsOut(items=items, disclosure=DISCLOSURE)


@router.get("/v1/projects/{project_id}/captions", response_model=CaptionsOut)
async def captions(
    project_id: str, p: Principal = Depends(current_principal), session: AsyncSession = Depends(get_session)
) -> CaptionsOut:
    await _owned(session, project_id, p)
    company, hook = await _hook(session, project_id)
    link = (
        (
            await session.execute(
                select(ShareLink).where(ShareLink.project_id == project_id, ShareLink.revoked_at.is_(None))
            )
        )
        .scalars()
        .first()
    )
    caps = suggested_captions(company, hook)
    caps.pop("company", None)
    return CaptionsOut(captions=caps, disclosure=DISCLOSURE, has_active_share=link is not None)


@router.post(
    "/v1/projects/{project_id}/share", response_model=ShareCreated, dependencies=[Depends(limit("share", 20, 3600))]
)
async def create_share(
    project_id: str, p: Principal = Depends(current_principal), session: AsyncSession = Depends(get_session)
) -> ShareCreated:
    project = await _owned(session, project_id, p)
    if project.state != "final_ready":
        raise HTTPException(409, "Video is not ready to share yet")
    if p.workspace.share_disabled:
        raise HTTPException(403, "Sharing is disabled for this workspace")
    token = secrets.token_urlsafe(32)
    session.add(ShareLink(project_id=project_id, token_hash=_hash(token)))
    await session.commit()
    # The raw token is returned once and never stored or logged.
    return ShareCreated(url=f"{get_settings().app_base_url}/s/{token}")


@router.delete("/v1/projects/{project_id}/share")
async def revoke_share(
    project_id: str, p: Principal = Depends(current_principal), session: AsyncSession = Depends(get_session)
) -> dict:
    await _owned(session, project_id, p)
    await session.execute(
        update(ShareLink)
        .where(ShareLink.project_id == project_id, ShareLink.revoked_at.is_(None))
        .values(revoked_at=utcnow())
    )
    await session.commit()
    return {"ok": True}


@router.get("/v1/share/{token}", response_model=SharePublic, dependencies=[Depends(limit("share-view", 60, 600))])
async def view_share(token: str, session: AsyncSession = Depends(get_session)) -> SharePublic:
    link = (await session.execute(select(ShareLink).where(ShareLink.token_hash == _hash(token)))).scalar_one_or_none()
    gone = HTTPException(404, "This link is no longer available")
    if link is None or link.revoked_at is not None:
        raise gone
    project = await session.get(Project, link.project_id)
    ws = await session.get(Workspace, project.workspace_id) if project else None
    if project is None or ws is None or ws.suspended or ws.share_disabled or project.state != "final_ready":
        raise gone
    storage = registry.get_storage()
    assets = await _assets(session, project.id)
    video = next((a for a in assets if a.type == "render" and a.format == "16x9"), None)
    thumb = next((a for a in assets if a.type == "thumbnail"), None)
    if video is None:
        raise gone
    company, hook = await _hook(session, project.id)
    link.views = (link.views or 0) + 1  # an impression: someone opened the shared video
    await session.commit()
    return SharePublic(
        title=company or "Featured startup",
        video_url=storage.presign_get(video.storage_key, SIGNED_URL_TTL_S),
        thumbnail_url=storage.presign_get(thumb.storage_key, SIGNED_URL_TTL_S) if thumb else None,
        disclosure=DISCLOSURE,
        tag="Featured",
    )


@router.get("/v1/projects/{project_id}/costs", response_model=CostsOut)
async def costs(
    project_id: str, p: Principal = Depends(current_principal), session: AsyncSession = Depends(get_session)
) -> CostsOut:
    project = await _owned(session, project_id, p)
    jobs = (
        (await session.execute(select(Job).where(Job.project_id == project_id).order_by(Job.created_at)))
        .scalars()
        .all()
    )
    return CostsOut(
        total=project.cost_total,
        lines=[
            CostLine(
                stage=j.stage,
                vendor=j.vendor,
                status=j.status,
                attempts=j.attempts,
                cost=j.cost,
                duration_s=j.duration_s,
            )
            for j in jobs
        ],
    )


@router.get("/v1/projects/{project_id}/events")
async def events(
    project_id: str, p: Principal = Depends(current_principal), session: AsyncSession = Depends(get_session)
) -> StreamingResponse:
    """Server-sent events. Clients use fetch streaming (EventSource cannot send the Authorization header)."""
    await _owned(session, project_id, p)

    async def stream():
        last, waited, quiet = None, 0.0, 0.0
        while waited < SSE_MAX_S:
            async with session_maker()() as s:
                proj = await s.get(Project, project_id)
            if proj is None:
                return
            snap = {"state": proj.state, "failure_reason": proj.failure_reason, "cost_total": str(proj.cost_total)}
            if snap != last:
                last, quiet = snap, 0.0
                yield f"event: state\ndata: {json.dumps(snap)}\n\n"
                if proj.state in TERMINAL:
                    return
            elif quiet >= 15:
                quiet = 0.0
                yield ": keep-alive\n\n"
            await asyncio.sleep(SSE_POLL_S)
            waited += SSE_POLL_S
            quiet += SSE_POLL_S

    return StreamingResponse(stream(), media_type="text/event-stream", headers={"Cache-Control": "no-cache"})
