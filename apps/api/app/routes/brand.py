import uuid

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import Principal, current_principal
from app.db import get_session
from app.integrations import registry
from app.models import BrandKit
from app.schemas.api import (
    FONTS,
    TONES,
    BrandDraft,
    BrandImportIn,
    BrandKitIn,
    BrandKitOut,
    ContrastCheck,
    LogoUploadIn,
    LogoUploadOut,
    VoiceOut,
)
from app.services import brand as brand_svc
from app.services.ratelimit import limit

router = APIRouter(prefix="/v1", tags=["brand"])

MAX_LOGO_BYTES = 2 * 1024 * 1024
LOGO_TYPES = {"image/svg+xml": "svg", "image/png": "png"}


async def _current(session: AsyncSession, workspace_id: str) -> BrandKit | None:
    return (
        (
            await session.execute(
                select(BrandKit).where(BrandKit.workspace_id == workspace_id).order_by(BrandKit.version.desc())
            )
        )
        .scalars()
        .first()
    )


def _out(kit: BrandKit) -> BrandKitOut:
    out = BrandKitOut.model_validate(kit)
    out.contrast = [ContrastCheck(**c) for c in brand_svc.brand_contrast_report(kit.primary_color, kit.accent_color)]
    out.accent_alternatives = brand_svc.accent_alternatives(kit.accent_color)
    return out


@router.get("/brand-kit", response_model=BrandKitOut)
async def get_brand_kit(
    p: Principal = Depends(current_principal), session: AsyncSession = Depends(get_session)
) -> BrandKitOut:
    kit = await _current(session, p.workspace.id)
    if kit is None:
        raise HTTPException(404, "No brand kit")
    return _out(kit)


@router.put("/brand-kit", response_model=BrandKitOut)
async def save_brand_kit(
    body: BrandKitIn, p: Principal = Depends(current_principal), session: AsyncSession = Depends(get_session)
) -> BrandKitOut:
    """Each save creates a new version (BR-5). There is no field for the channel identity (BR-8)."""
    bad_fonts = [f for f in body.fonts.values() if f not in FONTS]
    if bad_fonts or body.tone not in TONES:
        raise HTTPException(422, {"error": "invalid_choice", "fonts": FONTS, "tones": TONES})
    if any(not c.startswith("#") or len(c) != 7 for c in body.secondary_colors):
        raise HTTPException(422, "secondary_colors must be #RRGGBB")
    prefix = f"brand/{p.workspace.id}/"
    for key in (body.logo_light_key, body.logo_dark_key):
        if key and not key.startswith(prefix):
            raise HTTPException(422, "Logo must be uploaded through /v1/brand-kit/logo-upload")
    prev = await _current(session, p.workspace.id)
    kit = BrandKit(
        workspace_id=p.workspace.id,
        version=(prev.version + 1) if prev else 1,
        **body.model_dump(),
    )
    session.add(kit)
    await session.flush()
    p.workspace.brand_kit_id = kit.id
    await session.commit()
    return _out(kit)


@router.post("/brand-kit/import", response_model=BrandDraft, dependencies=[Depends(limit("import", 10, 3600))])
async def import_brand(body: BrandImportIn, _: Principal = Depends(current_principal)) -> BrandDraft:
    try:
        draft = await brand_svc.import_from_website(body.url)
    except brand_svc.UnsafeUrl as e:
        raise HTTPException(422, str(e)) from None
    except httpx.HTTPError:
        raise HTTPException(502, "Could not read that website. Enter your brand details manually.") from None
    return BrandDraft(**draft)


@router.post("/brand-kit/logo-upload", response_model=LogoUploadOut, dependencies=[Depends(limit("upload", 30, 3600))])
async def logo_upload(body: LogoUploadIn, p: Principal = Depends(current_principal)) -> LogoUploadOut:
    ext = LOGO_TYPES.get(body.content_type)
    if ext is None:
        raise HTTPException(422, "Logo must be an SVG or a transparent PNG")
    if body.size_bytes > MAX_LOGO_BYTES:
        raise HTTPException(422, "Logo must be 2 MB or smaller")
    key = f"brand/{p.workspace.id}/logo-{body.variant}-{uuid.uuid4().hex[:8]}.{ext}"
    return LogoUploadOut(upload_url=registry.get_storage().presign_put(key, 600), key=key)


@router.get("/voices", response_model=list[VoiceOut])
async def voices(_: Principal = Depends(current_principal)) -> list[VoiceOut]:
    """BR-6: availability depends on the avatar vendor, so read it from the provider at runtime."""
    allowed = set(brand_svc.ALLOWED_VOICE_ACCENTS)
    return [VoiceOut(**v.__dict__) for v in await registry.get_avatar().list_voices() if v.accent in allowed]
