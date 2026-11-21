"""Announcements: written in the back office (Marketing), shown to customers as a pop-up after they sign in, and optionally emailed to all."""

from datetime import UTC, datetime, timedelta
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, Field
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import Principal, current_principal, require
from app.db import get_session
from app.models import Announcement, MarketingCampaign, User
from app.models.base import utcnow
from app.services import announcements as svc
from app.services import marketing, paging
from app.services import marketing_campaigns as campaigns
from app.services import marketing_copy as copies
from app.services import marketing_segments as segs
from app.services.audit import audit

router = APIRouter(tags=["announcements"])


class AnnouncementBody(BaseModel):
    title: str = Field(min_length=1, max_length=120)
    message: str = Field(min_length=1, max_length=2000)
    button_label: str = Field("", max_length=60)
    button_url: str = Field("", max_length=500)
    show_for: int = Field(3, ge=1, le=24 * 90, description="How long the pop-up keeps appearing.")
    unit: Literal["hours", "days"] = "days"
    starts_at: datetime | None = None  # default: now
    send_email: bool = True
    confirm_count: int | None = None  # how many people the email would reach, as the team saw it


def _clean(body: AnnouncementBody) -> AnnouncementBody:
    try:
        copies.validate(
            copies.CopyIn(
                name="x",
                subject=body.title,
                body=body.message,
                button_label=body.button_label,
                button_url=body.button_url,
            )
        )
    except copies.Invalid as e:
        raise HTTPException(422, str(e)) from None
    if bool(body.button_label.strip()) != bool(body.button_url.strip()):
        raise HTTPException(422, "A button needs both its words and where it goes. Fill in both or neither.")
    if body.unit == "days" and body.show_for > 90:
        raise HTTPException(422, "Show it for up to 90 days.")
    return body


async def _out(db: AsyncSession, a: Announcement) -> dict:
    out = {
        "id": a.id,
        "title": a.title,
        "message": a.message,
        "button_label": a.button_label,
        "button_url": a.button_url,
        "shows_from": a.shows_from,
        "shows_until": a.shows_until,
        "ended_at": a.ended_at,
        "status": svc.status(a),
        "created_by": a.created_by,
        "created_at": a.created_at,
        "email": None,
    }
    if a.email_campaign_id:
        c = await db.get(MarketingCampaign, a.email_campaign_id)
        if c is not None:
            out["email"] = {"campaign_id": c.id, "status": c.status, "send_at": c.send_at, "audience": c.audience, **await campaigns.counts(db, c.id)}
    return out


@router.get("/v1/admin/marketing/announcements")
async def list_announcements(
    pg: paging.Page = Depends(paging.page(10, 50)),
    p: Principal = Depends(require("marketing.view")),
    db: AsyncSession = Depends(get_session),
) -> dict:
    base = select(Announcement)
    total = await paging.count(db, base)
    rows = (await db.execute(paging.window(base.order_by(Announcement.created_at.desc(), Announcement.id), pg))).scalars().all()
    return {"items": [await _out(db, a) for a in rows], **paging.meta(pg, total)}


@router.get("/v1/admin/marketing/announcements/audience")
async def audience(p: Principal = Depends(require("marketing.view")), db: AsyncSession = Depends(get_session)) -> dict:
    """How many people an announcement email would reach right now (everyone except those who opted out, bounced or complained)."""
    seg = segs.Rules.model_validate(svc.EVERYONE_RULES)
    return {"reachable": (await segs.preview(db, seg, sample=0))["reachable"], "email_engine": marketing.engine_mode()}


@router.post("/v1/admin/marketing/announcements", status_code=201)
async def create_announcement(
    body: AnnouncementBody,
    request: Request,
    p: Principal = Depends(require("marketing.manage")),
    db: AsyncSession = Depends(get_session),
) -> dict:
    body = _clean(body)
    now = utcnow()
    begin = body.starts_at if body.starts_at is None or body.starts_at.tzinfo else body.starts_at.replace(tzinfo=UTC)
    if begin is not None and begin < now - timedelta(minutes=1):
        raise HTTPException(422, "Choose a start time that is not in the past.")
    reachable = 0
    if body.send_email:
        if marketing.engine_mode() == "off":
            raise HTTPException(409, "Marketing email is switched off on the server (MARKETING_EMAIL), so the email would not be sent. Untick the email, or switch it on first.")
        reachable = (await segs.preview(db, segs.Rules.model_validate(svc.EVERYONE_RULES), sample=0))["reachable"]
        if reachable == 0:
            raise HTTPException(422, "Nobody can be emailed right now.")
        if body.confirm_count != reachable:
            raise HTTPException(409, f"The audience changed: {reachable} people can be emailed now, not {body.confirm_count}. Please look again.")
    starts, ends = svc.window(begin, body.show_for, body.unit)
    a = Announcement(
        title=body.title.strip(),
        message=body.message.strip(),
        button_label=body.button_label.strip(),
        button_url=body.button_url.strip(),
        shows_from=starts,
        shows_until=ends,
        created_by=p.user.email,
    )
    db.add(a)
    await db.flush()
    if body.send_email:
        c = await svc.make_email(db, a, p.user.email)
        c.status, c.send_at, c.scheduled_by, c.audience = "scheduled", begin or now, p.user.email, reachable
        a.email_campaign_id = c.id
    audit(
        db, p.user.email, "marketing.announcement_created", target_type="announcement", target_id=a.id,
        detail={"emailed": body.send_email, "audience": reachable, "until": ends.isoformat()}, request=request,
    )
    await db.commit()
    return await _out(db, a)


@router.post("/v1/admin/marketing/announcements/{announcement_id}/end")
async def end_announcement(
    announcement_id: str,
    request: Request,
    p: Principal = Depends(require("marketing.manage")),
    db: AsyncSession = Depends(get_session),
) -> dict:
    """Stop the pop-up now. An email that has already gone out cannot be taken back."""
    a = await db.get(Announcement, announcement_id)
    if a is None:
        raise HTTPException(404, "Announcement not found")
    if svc.status(a) != "ended":
        a.ended_at = utcnow()
        audit(db, p.user.email, "marketing.announcement_ended", target_type="announcement", target_id=a.id, request=request)
        await db.commit()
    return await _out(db, a)


# ---------- what a signed-in customer sees ----------
def _public(a: Announcement) -> dict:
    return {
        "id": a.id,
        "title": a.title,
        "message": a.message,
        "button_label": a.button_label,
        "button_url": a.button_url,
        "shows_until": a.shows_until,
    }


@router.get("/v1/me/announcements")
async def my_announcements(p: Principal = Depends(current_principal), db: AsyncSession = Depends(get_session)) -> list[dict]:
    user = await db.get(User, p.user.id)
    assert user is not None
    return [_public(a) for a in await svc.active_for(db, user)]


@router.post("/v1/me/announcements/{announcement_id}/dismiss")
async def dismiss_announcement(announcement_id: str, p: Principal = Depends(current_principal), db: AsyncSession = Depends(get_session)) -> dict:
    """Close it for good: it will not appear again for this person."""
    user = await db.get(User, p.user.id)
    assert user is not None
    svc.mark_seen(user, announcement_id)
    await db.commit()
    return {"ok": True}
