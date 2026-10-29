"""Back office: the library of presenter clips. Operator-only; customers never see or change it."""

import uuid

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import Principal, require
from app.db import get_session
from app.integrations import registry
from app.integrations.storage.base import ObjectTooLarge
from app.models import PresenterClip
from app.schemas.backoffice import (
    PresenterClipOut,
    PresenterClipPatch,
    PresenterClipUploadIn,
    PresenterClipUploadOut,
)
from app.services import presenter as lib
from app.services import uploads
from app.services.audit import audit
from app.services.ratelimit import limit

router = APIRouter(prefix="/v1/admin/presenter-clips", tags=["backoffice"])


def _out(c: PresenterClip, preview: bool = True) -> PresenterClipOut:
    return PresenterClipOut(
        id=c.id,
        title=c.title,
        role=c.role,
        active=c.active,
        status=c.status,
        duration_s=c.duration_s,
        width=c.width,
        height=c.height,
        has_audio=c.has_audio,
        size_bytes=c.size_bytes,
        rights_confirmed_by=c.rights_confirmed_by,
        created_at=c.created_at,
        url=registry.get_storage().presign_get(c.key, 900) if preview and c.status == "clean" else None,
    )


@router.get("", response_model=list[PresenterClipOut])
async def list_clips(p: Principal = Depends(require("presenter.manage")), session: AsyncSession = Depends(get_session)):
    rows = (
        (
            await session.execute(
                select(PresenterClip)
                .where(PresenterClip.status == "clean")
                .order_by(PresenterClip.role, PresenterClip.created_at)
            )
        )
        .scalars()
        .all()
    )
    return [_out(c) for c in rows]


@router.post("", response_model=PresenterClipUploadOut, dependencies=[Depends(limit("upload", 60, 3600))])
async def start_upload(
    body: PresenterClipUploadIn,
    request: Request,
    p: Principal = Depends(require("presenter.manage")),
    session: AsyncSession = Depends(get_session),
):
    if not body.rights_confirmed:
        raise HTTPException(422, "Confirm that you have the rights to this footage and that its presenter agreed.")
    rule = uploads.RULES["presenter_clip"]
    ext = rule.types.get(body.content_type)
    if ext is None:
        raise HTTPException(422, "Use an MP4, MOV or WebM video.")
    if body.size_bytes > rule.max_bytes:
        raise HTTPException(422, f"A clip must be {rule.max_bytes // (1024 * 1024)} MB or smaller.")
    clip = PresenterClip(
        title=body.title.strip(),
        role=body.role,
        key=f"presenter/{uuid.uuid4().hex}.{ext}",
        content_type=body.content_type,
        size_bytes=body.size_bytes,
        rights_confirmed_by=p.user.email,
    )
    session.add(clip)
    audit(
        session,
        p.user.email,
        "presenter_clip.upload_started",
        target_type="presenter_clip",
        target_id=clip.id,
        detail={"role": body.role, "title": clip.title, "rights_confirmed": True},
        request=request,
    )
    await session.commit()
    return PresenterClipUploadOut(
        id=clip.id, upload_url=registry.get_storage().presign_put(clip.key, 1800), max_bytes=rule.max_bytes
    )


@router.post("/{clip_id}/confirm", response_model=PresenterClipOut, dependencies=[Depends(limit("upload", 60, 3600))])
async def confirm_upload(
    clip_id: str,
    request: Request,
    p: Principal = Depends(require("presenter.manage")),
    session: AsyncSession = Depends(get_session),
):
    """Read what was really uploaded: right file type, malware-free, real video of a usable length and size."""
    clip = await session.get(PresenterClip, clip_id)
    if clip is None or clip.status != "pending":
        raise HTTPException(404, "Upload not found")
    storage = registry.get_storage()
    rule = uploads.RULES["presenter_clip"]

    async def reject(reason: str) -> HTTPException:
        clip.status = "rejected"
        await storage.delete(clip.key)
        await session.commit()
        return HTTPException(422, reason)

    try:
        data = await storage.get(clip.key, rule.max_bytes)
    except ObjectTooLarge:
        raise await reject("That file is too large.") from None
    except Exception:
        raise HTTPException(422, "We didn't receive that file. Please upload it again.") from None
    try:
        uploads.validate_content(clip.content_type, data)
    except uploads.InvalidUpload:
        raise await reject("That isn't a valid video file.") from None
    try:
        scan = await registry.get_scanner().scan(data)
    except Exception:
        raise HTTPException(
            503, "We couldn't scan that file right now. Please try again shortly."
        ) from None  # fail closed
    if not scan.clean:
        raise await reject("That file was blocked by the security scan.")
    try:
        a = await registry.get_renderer().analyze(storage.presign_get(clip.key, 600))
    except Exception:
        raise HTTPException(503, "We couldn't read that video right now. Please try again shortly.") from None
    problem = lib.check_media(clip.role, a.video_duration_s or a.duration_s, a.width, a.height)
    if problem:
        raise await reject(problem)
    clip.status, clip.size_bytes = "clean", len(data)
    clip.duration_s, clip.width, clip.height, clip.has_audio = (
        a.video_duration_s or a.duration_s,
        a.width,
        a.height,
        a.has_audio,
    )
    audit(
        session,
        p.user.email,
        "presenter_clip.added",
        target_type="presenter_clip",
        target_id=clip.id,
        detail={"role": clip.role, "title": clip.title, "duration_s": clip.duration_s},
        request=request,
    )
    await session.commit()
    return _out(clip)


@router.patch("/{clip_id}", response_model=PresenterClipOut)
async def update_clip(
    clip_id: str,
    body: PresenterClipPatch,
    request: Request,
    p: Principal = Depends(require("presenter.manage")),
    session: AsyncSession = Depends(get_session),
):
    clip = await session.get(PresenterClip, clip_id)
    if clip is None or clip.status != "clean":
        raise HTTPException(404, "Clip not found")
    changes = body.model_dump(exclude_none=True)
    if "role" in changes:
        problem = lib.check_media(changes["role"], clip.duration_s or 0, clip.width, clip.height)
        if problem:
            raise HTTPException(422, problem)
    for k, v in changes.items():
        setattr(clip, k, v.strip() if isinstance(v, str) else v)
    audit(
        session,
        p.user.email,
        "presenter_clip.updated",
        target_type="presenter_clip",
        target_id=clip.id,
        detail=changes,
        request=request,
    )
    await session.commit()
    return _out(clip)


@router.delete("/{clip_id}", status_code=204)
async def delete_clip(
    clip_id: str,
    request: Request,
    p: Principal = Depends(require("presenter.manage")),
    session: AsyncSession = Depends(get_session),
) -> None:
    clip = await session.get(PresenterClip, clip_id)
    if clip is None:
        raise HTTPException(404, "Clip not found")
    audit(
        session,
        p.user.email,
        "presenter_clip.deleted",
        target_type="presenter_clip",
        target_id=clip.id,
        detail={"role": clip.role, "title": clip.title},
        request=request,
    )
    await registry.get_storage().delete(clip.key)
    await session.delete(clip)
    await session.commit()
