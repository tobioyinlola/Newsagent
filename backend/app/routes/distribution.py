"""Human-fulfilled distribution requests. Payment and submission are one atomic operation."""

import re
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, EmailStr, Field, TypeAdapter, ValidationError
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import Principal, current_principal, require
from app.db import get_session
from app.integrations import registry
from app.models import Asset, BrandAsset, Brief, DistributionRequest, Project, ScriptVersion, Workspace
from app.models.base import utcnow
from app.services import ledger
from app.services.audit import audit
from app.services.distribution import send_confirmation
from app.services.ratelimit import limit

router = APIRouter(tags=["distribution"])
NAMES = [
    "Empire Magazine Africa",
    "Techpoint Africa",
    "Nairametrics",
    "Tech Next",
    "Tech Cabal",
    "Techeconomy",
    "Condia",
    "88 Lately",
    "Crest Africa",
    "Talented Women Network",
    "Iconic Africa",
    "Iconic Global",
    "CoinSpeaks",
    "The Cryptofy",
    "The Crypto Reporters",
    "The Coins Report",
    "The Coins Insider",
    "Business Insider",
    "Street Insider",
    "Bar Chart",
    "The Globe and Mail",
    "Benzinga",
    "Tribune",
    "Sun",
    "New Telegraph",
    "Independent",
    "Vanguard",
    "ThisDay",
    "The Guardian",
    "Punch",
    "Daily Trust",
    "Daily Post",
    "Business Day",
    "P.M. News",
    "Premium Times",
    "The Nation",
    "Celeb Spotlight",
    "News Nine",
    "Naijaloaded",
    "Tooxclusive",
    "NotJustOk",
    "9jaflaver",
    "Mp3bullet",
    "Naijamusic",
    "MP3Naija",
    "AlbumTalks",
    "P mp Kulture",
]
OUTLETS = {
    str(i + 1): {"id": str(i + 1), "name": name, "region": "Africa", "credits": "0"} for i, name in enumerate(NAMES)
}


class DraftIn(BaseModel):
    stage: Literal["outlets", "content", "contact", "review"] = "outlets"
    outlet_ids: list[str] = Field(default_factory=list, max_length=100)
    project_id: str | None = None
    story_project_id: str | None = None
    announcement_source: Literal["platform", "custom"] = "custom"
    headline: str = Field(default="", max_length=300)
    announcement: str = Field(default="", max_length=50000)
    contact_name: str = Field(default="", max_length=200)
    contact_email: str = Field(default="", max_length=320)
    phone: str = Field(default="", max_length=40)
    whatsapp: str = Field(default="", max_length=40)
    logo_key: str = Field(default="", max_length=500)
    picture_keys: list[str] = Field(default_factory=list, max_length=10)


class StatusIn(BaseModel):
    status: Literal["submitted", "in_progress", "completed"]


def out(row: DistributionRequest) -> dict:
    return {
        "id": row.id,
        "workspace_id": row.workspace_id,
        "created_by": row.created_by,
        "status": row.status,
        "stage": row.stage,
        "data": {
            **row.data,
            "outlets": row.data.get("outlets", [OUTLETS[i] for i in row.data.get("outlet_ids", []) if i in OUTLETS]),
        },
        "total_credits": str(row.total_credits),
        "paid": row.paid_at is not None,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
        "submitted_at": row.submitted_at,
        "email_sent": row.email_sent_at is not None,
    }


async def owned(db: AsyncSession, id: str, p: Principal) -> DistributionRequest:
    row = await db.get(DistributionRequest, id)
    if row is None or row.workspace_id != p.workspace.id:
        raise HTTPException(404, "Distribution request not found")
    return row


async def validate(db: AsyncSession, body: DraftIn, workspace_id: str):
    if len(set(body.outlet_ids)) != len(body.outlet_ids) or any(i not in OUTLETS for i in body.outlet_ids):
        raise HTTPException(422, "Choose valid, distinct outlets")
    if body.project_id:
        project = await db.get(Project, body.project_id)
        if project is None or project.workspace_id != workspace_id or project.state != "final_ready":
            raise HTTPException(422, "Select one of your completed videos")
    if body.story_project_id:
        story = (
            await db.execute(
                select(ScriptVersion.id)
                .join(Project, Project.id == ScriptVersion.project_id)
                .where(
                    Project.workspace_id == workspace_id,
                    Project.id == body.story_project_id,
                    ScriptVersion.story.is_not(None),
                )
            )
        ).first()
        if story is None:
            raise HTTPException(422, "Choose a story written in your workspace")
    for key, kinds in [
        (body.logo_key, {"logo_light", "logo_dark", "product_image"}),
        *[(k, {"product_image"}) for k in body.picture_keys],
    ]:
        if not key:
            continue
        asset = (
            await db.execute(
                select(BrandAsset).where(
                    BrandAsset.key == key, BrandAsset.workspace_id == workspace_id, BrandAsset.status == "clean"
                )
            )
        ).scalar_one_or_none()
        if asset is None or asset.kind not in kinds:
            raise HTTPException(422, "Images must be your own checked uploads")


@router.get("/v1/distribution/outlets")
async def outlets(p: Principal = Depends(current_principal)) -> dict:
    return {"outlets": list(OUTLETS.values()), "coming_soon": ["United States", "Canada", "United Kingdom"]}


@router.get("/v1/distribution/stories")
async def stories(p: Principal = Depends(current_principal), db: AsyncSession = Depends(get_session)) -> list[dict]:
    scripts = (
        (
            await db.execute(
                select(ScriptVersion)
                .join(Project, Project.id == ScriptVersion.project_id)
                .where(Project.workspace_id == p.workspace.id, ScriptVersion.story.is_not(None))
                .order_by(ScriptVersion.created_at.desc(), ScriptVersion.version.desc())
            )
        )
        .scalars()
        .all()
    )
    result, seen = [], set()
    for script in scripts:
        if script.project_id in seen or not script.story:
            continue
        seen.add(script.project_id)
        story = script.story
        parts = [story.get("dek", "")]
        for section in story.get("sections", []):
            if section.get("heading"):
                parts.append(section["heading"])
            parts.extend(section.get("paragraphs", []))
        if story.get("about"):
            parts.append(story["about"])
        result.append(
            {
                "project_id": script.project_id,
                "headline": story.get("headline", ""),
                "announcement": "\n\n".join(x for x in parts if x.strip()),
            }
        )
    return result


@router.get("/v1/distribution/videos")
async def videos(p: Principal = Depends(current_principal), db: AsyncSession = Depends(get_session)) -> list[dict]:
    projects = (
        (
            await db.execute(
                select(Project)
                .where(Project.workspace_id == p.workspace.id, Project.state == "final_ready")
                .order_by(Project.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    result = []
    for project in projects:
        script = (
            (
                await db.execute(
                    select(ScriptVersion)
                    .where(ScriptVersion.project_id == project.id)
                    .order_by(ScriptVersion.version.desc())
                )
            )
            .scalars()
            .first()
        )
        story = script.story if script and script.story else {}
        text = "\n\n".join(
            [story.get("dek", ""), *[p for s in story.get("sections", []) for p in s.get("paragraphs", [])]]
        )
        brief = (await db.execute(select(Brief).where(Brief.project_id == project.id))).scalar_one_or_none()
        video = (
            (await db.execute(select(Asset).where(Asset.project_id == project.id, Asset.type == "render")))
            .scalars()
            .first()
        )
        result.append(
            {
                "id": project.id,
                "headline": story.get("headline") or (brief.raw_text[:120] if brief else ""),
                "announcement": text
                or "\n\n".join(segment.get("text", "") for segment in (script.segments if script else [])),
                "video_url": registry.get_storage().presign_get(video.storage_key, 600) if video else None,
            }
        )
    return result


@router.get("/v1/distribution")
async def listing(p: Principal = Depends(current_principal), db: AsyncSession = Depends(get_session)) -> list[dict]:
    rows = (
        await db.execute(
            select(DistributionRequest)
            .where(DistributionRequest.workspace_id == p.workspace.id)
            .order_by(DistributionRequest.updated_at.desc())
        )
    ).scalars()
    return [out(r) for r in rows]


@router.post("/v1/distribution", dependencies=[Depends(limit("distribution-create", 30, 3600))])
async def create(p: Principal = Depends(current_principal), db: AsyncSession = Depends(get_session)) -> dict:
    row = DistributionRequest(workspace_id=p.workspace.id, created_by=p.user.email, data=DraftIn().model_dump())
    db.add(row)
    await db.commit()
    return out(row)


@router.get("/v1/distribution/{id}")
async def detail(id: str, p: Principal = Depends(current_principal), db: AsyncSession = Depends(get_session)) -> dict:
    return out(await owned(db, id, p))


@router.put("/v1/distribution/{id}")
async def save(
    id: str, body: DraftIn, p: Principal = Depends(current_principal), db: AsyncSession = Depends(get_session)
) -> dict:
    await owned(db, id, p)
    await validate(db, body, p.workspace.id)
    total = sum((Decimal(OUTLETS[i]["credits"]) for i in body.outlet_ids), Decimal("0"))
    row = (
        await db.execute(
            update(DistributionRequest)
            .where(DistributionRequest.id == id, DistributionRequest.status == "draft")
            .values(data=body.model_dump(), stage=body.stage, total_credits=total, updated_at=utcnow())
            .returning(DistributionRequest)
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(409, "Submitted requests cannot be edited")
    await db.commit()
    return out(row)


@router.post("/v1/distribution/{id}/submit")
async def submit(id: str, p: Principal = Depends(current_principal), db: AsyncSession = Depends(get_session)) -> dict:
    # A conditional update claims the request on both SQLite and Postgres; concurrent submits cannot debit twice.
    await owned(db, id, p)
    now = utcnow()
    row = (
        await db.execute(
            update(DistributionRequest)
            .where(DistributionRequest.id == id, DistributionRequest.status == "draft")
            .values(status="submitted", updated_at=now)
            .returning(DistributionRequest)
        )
    ).scalar_one_or_none()
    if row is None:
        row = await owned(db, id, p)
        await send_confirmation(db, row)
        return out(row)
    body = DraftIn.model_validate(row.data)
    if body.announcement_source == "platform" and not body.story_project_id:
        raise HTTPException(422, "Select the platform story you want to use")
    await validate(db, body, p.workspace.id)
    if (
        not body.outlet_ids
        or not body.project_id
        or not all(
            x.strip()
            for x in [
                body.headline,
                body.announcement,
                body.contact_name,
                body.contact_email,
                body.phone,
                body.whatsapp,
                body.logo_key,
            ]
        )
    ):
        raise HTTPException(
            422, "Choose outlets and a completed video, add your release, company logo and all contact details"
        )
    try:
        TypeAdapter(EmailStr).validate_python(body.contact_email)
    except ValidationError as e:
        raise HTTPException(422, "Enter a valid contact email") from e
    if any(
        not re.fullmatch(r"[+()0-9 .-]{7,40}", value) or len(re.sub(r"\D", "", value)) < 7
        for value in [body.phone, body.whatsapp]
    ):
        raise HTTPException(422, "Enter valid phone and WhatsApp numbers, including the country code")
    total = sum((Decimal(OUTLETS[i]["credits"]) for i in body.outlet_ids), Decimal("0"))
    if total != row.total_credits:
        row.status, row.total_credits, row.stage = "draft", total, "review"
        await db.commit()
        raise HTTPException(409, "Outlet pricing changed. Review the updated total before submitting.")
    ws = (
        await db.execute(
            select(Workspace)
            .where(Workspace.id == p.workspace.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).scalar_one()
    if ws.suspended:
        raise HTTPException(403, "This workspace is suspended")
    if ws.credit_balance < total:
        # Persist the draft's checkout stage even though payment failed.
        row.status, row.stage, row.total_credits = "draft", "review", total
        await db.commit()
        raise HTTPException(
            402,
            {
                "error": "insufficient_credits",
                "message": "Top up your wallet to submit. Your draft is saved.",
                "required": str(total),
            },
        )
    if total:
        await ledger.apply(
            db,
            ws,
            -total,
            "usage",
            ref=f"distribution:{id}",
            stage="distribution",
            description=f"Distribution to {len(body.outlet_ids)} outlets",
        )
    row.data = {**body.model_dump(), "outlets": [dict(OUTLETS[i]) for i in body.outlet_ids]}
    row.total_credits, row.paid_at, row.submitted_at, row.stage = total, now, now, "submitted"
    audit(
        db,
        p.user.email,
        "distribution.submitted",
        target_type="distribution",
        target_id=id,
        detail={"credits": str(total), "outlets": len(body.outlet_ids)},
    )
    await db.commit()
    await send_confirmation(db, row)
    return out(row)


@router.get("/v1/admin/distribution")
async def admin_list(
    p: Principal = Depends(require("operations.view")), db: AsyncSession = Depends(get_session)
) -> list[dict]:
    rows = (await db.execute(select(DistributionRequest).order_by(DistributionRequest.updated_at.desc()))).scalars()
    return [out(r) for r in rows]


@router.get("/v1/admin/distribution/{id}/assets")
async def admin_assets(
    id: str, p: Principal = Depends(require("operations.view")), db: AsyncSession = Depends(get_session)
) -> dict:
    row = await db.get(DistributionRequest, id)
    if row is None:
        raise HTTPException(404, "Request not found")
    data = row.data
    video = (
        (await db.execute(select(Asset).where(Asset.project_id == data.get("project_id"), Asset.type == "render")))
        .scalars()
        .first()
    )
    keys = [data.get("logo_key"), *data.get("picture_keys", [])]
    return {
        "video_url": registry.get_storage().presign_get(video.storage_key, 600) if video else None,
        "images": [{"key": k, "url": registry.get_storage().presign_get(k, 600)} for k in keys if k],
    }


@router.patch("/v1/admin/distribution/{id}")
async def admin_status(
    id: str,
    body: StatusIn,
    p: Principal = Depends(require("operations.manage")),
    db: AsyncSession = Depends(get_session),
) -> dict:
    row = await db.get(DistributionRequest, id)
    if row is None:
        raise HTTPException(404, "Request not found")
    if not row.paid_at:
        raise HTTPException(409, "An unpaid draft cannot be marked as submitted")
    row.status, row.updated_at = body.status, utcnow()
    audit(
        db,
        p.user.email,
        "distribution.status_changed",
        target_type="distribution",
        target_id=id,
        detail={"status": body.status},
    )
    await db.commit()
    return out(row)


@router.post("/v1/admin/distribution/{id}/confirmation")
async def retry_email(
    id: str, p: Principal = Depends(require("operations.manage")), db: AsyncSession = Depends(get_session)
) -> dict:
    row = await db.get(DistributionRequest, id)
    if row is None or row.paid_at is None:
        raise HTTPException(404, "Submitted request not found")
    await send_confirmation(db, row)
    return out(row)
