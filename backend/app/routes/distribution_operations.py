"""Operator configuration, private per-outlet workflow and communication history."""

from typing import Literal
from urllib.parse import urlsplit

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import AnyHttpUrl, BaseModel, EmailStr, Field, TypeAdapter, field_validator
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import Principal, require
from app.db import get_session
from app.models import DistributionMail, DistributionPlacement, DistributionRequest, SystemSetting
from app.models.base import utcnow
from app.routes.distribution import OUTLETS, result
from app.services import distribution as service
from app.services import distribution_catalog as config
from app.services.audit import audit

router = APIRouter(tags=["distribution"])


class PlacementUpdate(BaseModel):
    status: Literal["pending", "in_progress", "published"] | None = None
    internal_status: Literal["not_started", "follow_up", "payment_made"] | None = None
    internal_notes: str | None = Field(default=None, max_length=5000)
    published_url: str | None = Field(default=None, max_length=2000)
    contact_email: EmailStr | Literal[""] | None = None
    outreach_subject: str | None = Field(default=None, min_length=1, max_length=300)
    outreach_body: str | None = Field(default=None, min_length=1, max_length=100000)

    @field_validator("published_url")
    @classmethod
    def url(cls, value):
        if value:
            value = str(TypeAdapter(AnyHttpUrl).validate_python(value))
            if len(value) > 2000:
                raise ValueError("Publication URL must be no longer than 2000 characters.")
            parsed = urlsplit(value)
            if parsed.username or parsed.password:
                raise ValueError("Publication links must not contain credentials.")
        return value

    @field_validator("outreach_subject")
    @classmethod
    def subject(cls, value):
        if value and ("\r" in value or "\n" in value):
            raise ValueError("Subject must be a single line.")
        return value


class OutreachSend(BaseModel):
    idempotency_key: str = Field(min_length=16, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")


async def save_setting(db, p, change):
    row = await config.settings(db, lock=True)
    if row is None:
        row = SystemSetting(key=config.KEY, value={})
        db.add(row)
        await db.flush()
    row.value = change(row.value)
    row.updated_by, row.updated_at = p.user.email, utcnow()
    audit(db, p.user.email, "distribution.configuration_changed", target_type="setting", target_id=config.KEY)
    await db.commit()


@router.get("/v1/admin/distribution/config")
async def get_config(p: Principal = Depends(require("operations.view")), db: AsyncSession = Depends(get_session)):
    row = await config.settings(db)
    return {
        "team_emails": (row.value if row else {}).get("team_emails", []),
        "outlets": await config.catalog(db, admin=True),
        "template_variables": sorted(config.VARIABLES),
    }


@router.put("/v1/admin/distribution/config")
async def set_config(
    body: config.TeamConfig,
    p: Principal = Depends(require("operations.manage")),
    db: AsyncSession = Depends(get_session),
):
    emails = sorted({str(e).strip().lower() for e in body.team_emails})
    await save_setting(db, p, lambda old: {**old, "team_emails": emails})
    return {"team_emails": emails}


@router.put("/v1/admin/distribution/outlets/{outlet_id}")
async def set_outlet(
    outlet_id: str,
    body: config.OutletConfig,
    p: Principal = Depends(require("operations.manage")),
    db: AsyncSession = Depends(get_session),
):
    if outlet_id not in OUTLETS:
        raise HTTPException(404, "Outlet not found")
    value = body.model_dump(mode="json")
    await save_setting(db, p, lambda old: {**old, "outlets": {**old.get("outlets", {}), outlet_id: value}})
    return {**OUTLETS[outlet_id], **value}


@router.get("/v1/admin/distribution/{id}")
async def request_detail(
    id: str, p: Principal = Depends(require("operations.view")), db: AsyncSession = Depends(get_session)
):
    row = await db.get(DistributionRequest, id)
    if row is None:
        raise HTTPException(404, "Request not found")
    return await result(db, row, admin=True)


@router.patch("/v1/admin/distribution/{id}/placements/{placement_id}")
async def update_placement(
    id: str,
    placement_id: str,
    body: PlacementUpdate,
    tasks: BackgroundTasks,
    p: Principal = Depends(require("operations.manage")),
    db: AsyncSession = Depends(get_session),
):
    row = (
        await db.execute(
            update(DistributionRequest)
            .where(DistributionRequest.id == id, DistributionRequest.paid_at.is_not(None))
            .values(updated_at=utcnow())
            .returning(DistributionRequest)
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(404, "Paid request not found")
    # A write claim serializes read/modify/write on SQLite as well as Postgres.
    placement = (
        await db.execute(
            update(DistributionPlacement)
            .where(DistributionPlacement.id == placement_id, DistributionPlacement.request_id == id)
            .values(updated_at=utcnow())
            .returning(DistributionPlacement)
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()
    if placement is None:
        raise HTTPException(404, "Outlet placement not found")
    old_url = placement.published_url
    values = body.model_dump(exclude_none=True)
    for name, value in values.items():
        setattr(placement, name, str(value))
    if body.published_url:
        placement.status = "published"
    if placement.status == "published" and not placement.published_url:
        raise HTTPException(422, "Add the published post URL before marking this outlet published")
    if placement.status == "published":
        placement.published_at = placement.published_at or utcnow()
    else:
        placement.published_at = None
    if placement.published_url and placement.published_url != old_url:
        await service.queue_publication(db, row, placement)
    service.activity(
        db,
        row,
        "placement_updated",
        {
            "changed_fields": list(values),
            "status": placement.status,
            "published_url": placement.published_url,
            "internal_status": placement.internal_status,
        },
        actor=p.user.email,
        placement=placement,
    )
    await db.flush()
    placements = (
        (await db.execute(select(DistributionPlacement).where(DistributionPlacement.request_id == id))).scalars().all()
    )
    row.status = (
        "completed"
        if all(x.status == "published" for x in placements)
        else "in_progress"
        if any(x.status != "pending" for x in placements)
        else "submitted"
    )
    row.updated_at = utcnow()
    audit(
        db,
        p.user.email,
        "distribution.placement_updated",
        target_type="distribution",
        target_id=id,
        detail={"placement_id": placement_id, "status": placement.status, "internal_status": placement.internal_status},
    )
    await db.commit()
    tasks.add_task(service.deliver_request, row.id)
    return await result(db, row, admin=True)


@router.post("/v1/admin/distribution/{id}/placements/{placement_id}/outreach")
async def send_outreach(
    id: str,
    placement_id: str,
    body: OutreachSend,
    tasks: BackgroundTasks,
    p: Principal = Depends(require("operations.manage")),
    db: AsyncSession = Depends(get_session),
):
    row = await db.get(DistributionRequest, id)
    if row is None or not row.paid_at:
        raise HTTPException(404, "Paid request not found")
    placement = (
        await db.execute(
            update(DistributionPlacement)
            .where(DistributionPlacement.id == placement_id, DistributionPlacement.request_id == id)
            .values(updated_at=utcnow())
            .returning(DistributionPlacement)
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()
    if placement is None:
        raise HTTPException(404, "Placement not found")
    if not placement.contact_email or not placement.outreach_body.strip() or not placement.outreach_subject.strip():
        raise HTTPException(422, "Save a recipient, subject and email body first")
    await service.queue_mail(
        db,
        row,
        "outreach",
        placement.contact_email,
        placement.outreach_subject,
        placement.outreach_body,
        key=placement.id + ":" + body.idempotency_key,
        placement=placement,
    )
    audit(
        db,
        p.user.email,
        "distribution.outreach_requested",
        target_type="distribution",
        target_id=id,
        detail={"placement_id": placement.id, "recipient": placement.contact_email},
    )
    await db.commit()
    tasks.add_task(service.deliver_request, id)
    return {"status": "queued"}


@router.post("/v1/admin/distribution/{id}/emails/{mail_id}/retry")
async def retry_mail(
    id: str,
    mail_id: str,
    tasks: BackgroundTasks,
    p: Principal = Depends(require("operations.manage")),
    db: AsyncSession = Depends(get_session),
):
    mail = await db.get(DistributionMail, mail_id)
    if mail is None or mail.request_id != id:
        raise HTTPException(404, "Email not found")
    if mail.status == "sent":
        return {"status": "already_sent"}
    if mail.status == "sending":
        raise HTTPException(409, "Delivery is in progress; wait before retrying")
    mail.status = "retry_requested"
    audit(
        db,
        p.user.email,
        "distribution.email_retry",
        target_type="distribution",
        target_id=id,
        detail={"mail_id": mail_id},
    )
    await db.commit()
    tasks.add_task(service.deliver_request, id)
    return {"status": "queued"}
