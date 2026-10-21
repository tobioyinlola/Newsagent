import uuid

import httpx
from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import Principal, current_principal
from app.db import get_session
from app.integrations import registry
from app.integrations.storage.base import ObjectTooLarge
from app.models import BrandAsset, BrandKit
from app.schemas.api import (
    FONTS,
    TONES,
    BrandAssetOut,
    BrandDraft,
    BrandImportIn,
    BrandKitIn,
    BrandKitOut,
    ContrastCheck,
    UploadConfirmIn,
    UploadIn,
    UploadOut,
    VoiceOut,
)
from app.services import brand as brand_svc
from app.services import uploads
from app.services.ratelimit import limit

router = APIRouter(prefix="/v1", tags=["brand"])


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
    for key, kind in ((body.logo_light_key, "logo_light"), (body.logo_dark_key, "logo_dark")):
        if not key:
            continue
        ok = (
            await session.execute(
                select(BrandAsset.id).where(
                    BrandAsset.key == key,
                    BrandAsset.workspace_id == p.workspace.id,
                    BrandAsset.status == "clean",
                    BrandAsset.kind == kind,
                )
            )
        ).first()
        if not ok:
            raise HTTPException(422, "Logo must be an uploaded file that passed our security check")
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


@router.post("/brand-kit/uploads", response_model=UploadOut, dependencies=[Depends(limit("upload", 30, 3600))])
async def start_upload(
    body: UploadIn, p: Principal = Depends(current_principal), session: AsyncSession = Depends(get_session)
) -> UploadOut:
    rule = uploads.RULES[body.kind]
    ext = rule.types.get(body.content_type)
    if ext is None:
        raise HTTPException(422, "That file type isn't allowed here")
    if body.size_bytes > rule.max_bytes:
        raise HTTPException(422, f"File must be {rule.max_bytes // (1024 * 1024)} MB or smaller")
    key = f"brand/{p.workspace.id}/{body.kind}-{uuid.uuid4().hex[:10]}.{ext}"
    session.add(
        BrandAsset(
            workspace_id=p.workspace.id,
            key=key,
            kind=body.kind,
            content_type=body.content_type,
            size_bytes=body.size_bytes,
        )
    )
    await session.commit()
    return UploadOut(upload_url=registry.get_storage().presign_put(key, 600), key=key, max_bytes=rule.max_bytes)


@router.post(
    "/brand-kit/uploads/confirm", response_model=BrandAssetOut, dependencies=[Depends(limit("upload", 30, 3600))]
)
async def confirm_upload(
    body: UploadConfirmIn, p: Principal = Depends(current_principal), session: AsyncSession = Depends(get_session)
) -> BrandAssetOut:
    """Download what was actually uploaded, verify type and size, scan for malware. Only then is it usable."""
    asset = (
        await session.execute(
            select(BrandAsset).where(BrandAsset.key == body.key, BrandAsset.workspace_id == p.workspace.id)
        )
    ).scalar_one_or_none()
    if asset is None or asset.status != "pending":
        raise HTTPException(404, "Upload not found")
    storage = registry.get_storage()
    rule = uploads.RULES[asset.kind]

    async def reject(reason: str) -> HTTPException:
        asset.status = "rejected"
        await storage.delete(asset.key)
        await session.commit()
        return HTTPException(422, reason)

    try:
        data = await storage.get(asset.key, rule.max_bytes)
    except ObjectTooLarge:
        raise await reject("File is too large") from None
    except Exception:
        raise HTTPException(422, "We didn't receive that file. Please upload it again.") from None
    try:
        uploads.validate_content(asset.content_type, data)
    except uploads.InvalidUpload as e:
        raise await reject(str(e)) from None
    try:
        result = await registry.get_scanner().scan(data)
    except Exception:
        # Fail closed: an unscanned file is never marked clean. The upload stays pending and can be retried.
        raise HTTPException(503, "We couldn't check that file right now. Please try again shortly.") from None
    if not result.clean:
        raise await reject("That file was blocked by our security scan.")
    asset.status, asset.size_bytes = "clean", len(data)
    await session.commit()
    return BrandAssetOut(key=asset.key, kind=asset.kind, content_type=asset.content_type, size_bytes=asset.size_bytes)


@router.get("/brand-kit/assets", response_model=list[BrandAssetOut])
async def list_assets(
    p: Principal = Depends(current_principal), session: AsyncSession = Depends(get_session)
) -> list[BrandAssetOut]:
    rows = (
        (
            await session.execute(
                select(BrandAsset)
                .where(BrandAsset.workspace_id == p.workspace.id, BrandAsset.status == "clean")
                .order_by(BrandAsset.created_at)
            )
        )
        .scalars()
        .all()
    )
    storage = registry.get_storage()
    return [
        BrandAssetOut(
            key=a.key,
            kind=a.kind,
            content_type=a.content_type,
            size_bytes=a.size_bytes,
            url=storage.presign_get(a.key, 900),
        )
        for a in rows
    ]


@router.get("/voices", response_model=list[VoiceOut])
async def voices(_: Principal = Depends(current_principal)) -> list[VoiceOut]:
    """BR-6: availability depends on the avatar vendor, so read it from the provider at runtime."""
    allowed = set(brand_svc.ALLOWED_VOICE_ACCENTS)
    return [VoiceOut(**v.__dict__) for v in await registry.get_avatar().list_voices() if v.accent in allowed]
