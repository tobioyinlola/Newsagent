"""Back office: marketing switches and status. Public: the unsubscribe page every marketing email links to."""

from html import escape

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import Principal, require
from app.db import get_session
from app.models import MarketingPref, MarketingSegment, MarketingSend, MarketingSuppression
from app.models.base import utcnow
from app.services import marketing
from app.services import marketing_segments as segs
from app.services.audit import audit

router = APIRouter(tags=["marketing"])


@router.get("/v1/admin/marketing/status")
async def status(p: Principal = Depends(require("marketing.view")), db: AsyncSession = Depends(get_session)) -> dict:
    cfg = await marketing.get_config(db)
    start = utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    sent_today = (
        await db.execute(
            select(func.count())
            .select_from(MarketingSend)
            .where(MarketingSend.status.in_(("sent", "dry_run")), MarketingSend.created_at >= start)
        )
    ).scalar_one()
    opted_out = (
        await db.execute(select(func.count()).select_from(MarketingPref).where(MarketingPref.opted_out_at.is_not(None)))
    ).scalar_one()
    suppressed = (await db.execute(select(func.count()).select_from(MarketingSuppression))).scalar_one()
    return {
        "engine": marketing.engine_mode(),  # off | on | dry_run (set MARKETING_EMAIL on the backend)
        "config": cfg.model_dump(),
        "sent_today": sent_today,
        "opted_out": opted_out,
        "suppressed": suppressed,
    }


@router.put("/v1/admin/marketing/config")
async def put_config(
    body: marketing.MarketingConfig,
    request: Request,
    p: Principal = Depends(require("marketing.manage")),
    db: AsyncSession = Depends(get_session),
) -> dict:
    before = await marketing.get_config(db)
    await marketing.save_config(db, p.user.email, body)
    audit(
        db,
        p.user.email,
        "marketing.config_changed",
        target_type="setting",
        target_id=marketing.KEY,
        detail={"before": before.model_dump(), "after": body.model_dump()},
        request=request,
    )
    await db.commit()
    return {"config": body.model_dump()}


# ---------- segments ----------
class SegmentBody(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    description: str = Field("", max_length=1000)
    rules: dict


class PreviewBody(BaseModel):
    rules: dict


def _seg(s: MarketingSegment) -> dict:
    return {
        "id": s.id,
        "name": s.name,
        "description": s.description,
        "rules": s.rules,
        "created_by": s.created_by,
        "created_at": s.created_at.isoformat(),
    }


async def _live(db: AsyncSession, segment_id: str) -> MarketingSegment:
    s = await db.get(MarketingSegment, segment_id)
    if s is None or s.archived_at is not None:
        raise HTTPException(404, "That segment doesn't exist.")
    return s


def _rules(raw: dict) -> segs.Rules:
    try:
        return segs.validate(raw)
    except segs.Invalid as e:
        raise HTTPException(422, str(e)) from None


@router.get("/v1/admin/marketing/segment-fields")
async def segment_fields(p: Principal = Depends(require("marketing.view"))) -> dict:
    return {"fields": segs.catalog()}


@router.get("/v1/admin/marketing/segments")
async def list_segments(
    p: Principal = Depends(require("marketing.view")), db: AsyncSession = Depends(get_session)
) -> dict:
    rows = (
        await db.execute(
            select(MarketingSegment)
            .where(MarketingSegment.archived_at.is_(None))
            .order_by(MarketingSegment.created_at.desc())
        )
    ).scalars()
    return {"items": [_seg(s) for s in rows]}


@router.post("/v1/admin/marketing/segments/preview")
async def preview_rules(
    body: PreviewBody, p: Principal = Depends(require("marketing.view")), db: AsyncSession = Depends(get_session)
) -> dict:
    return await segs.preview(db, _rules(body.rules))


@router.post("/v1/admin/marketing/segments", status_code=201)
async def create_segment(
    body: SegmentBody,
    request: Request,
    p: Principal = Depends(require("marketing.manage")),
    db: AsyncSession = Depends(get_session),
) -> dict:
    rules = _rules(body.rules)
    s = MarketingSegment(
        name=body.name.strip(), description=body.description.strip(), rules=rules.model_dump(), created_by=p.user.email
    )
    db.add(s)
    await db.flush()
    audit(db, p.user.email, "marketing.segment_created", target_type="segment", target_id=s.id, request=request)
    await db.commit()
    return _seg(s)


@router.get("/v1/admin/marketing/segments/{segment_id}")
async def get_segment(
    segment_id: str, p: Principal = Depends(require("marketing.view")), db: AsyncSession = Depends(get_session)
) -> dict:
    s = await _live(db, segment_id)
    return {**_seg(s), "preview": await segs.preview(db, segs.Rules.model_validate(s.rules))}


@router.put("/v1/admin/marketing/segments/{segment_id}")
async def update_segment(
    segment_id: str,
    body: SegmentBody,
    request: Request,
    p: Principal = Depends(require("marketing.manage")),
    db: AsyncSession = Depends(get_session),
) -> dict:
    s = await _live(db, segment_id)
    s.name, s.description, s.rules = body.name.strip(), body.description.strip(), _rules(body.rules).model_dump()
    audit(db, p.user.email, "marketing.segment_changed", target_type="segment", target_id=s.id, request=request)
    await db.commit()
    return _seg(s)


@router.delete("/v1/admin/marketing/segments/{segment_id}", status_code=204)
async def archive_segment(
    segment_id: str,
    request: Request,
    p: Principal = Depends(require("marketing.manage")),
    db: AsyncSession = Depends(get_session),
) -> None:
    s = await _live(db, segment_id)
    s.archived_at = utcnow()
    audit(db, p.user.email, "marketing.segment_archived", target_type="segment", target_id=s.id, request=request)
    await db.commit()


# ---------- unsubscribe (public; the token is the proof) ----------
def _page(title: str, message: str, button: str | None = None) -> HTMLResponse:
    form = f'<form method="post"><button type="submit">{escape(button)}</button></form>' if button else ""
    return HTMLResponse(
        "<!doctype html><html lang=en><meta charset=utf-8><meta name=viewport content='width=device-width,initial-scale=1'>"
        f'<title>{escape(title)}</title><body style="font:16px/1.5 Inter,Helvetica,Arial,sans-serif;color:#191A30;max-width:480px;'
        f'margin:12vh auto;padding:0 20px"><h1 style="font-size:24px">{escape(title)}</h1><p>{escape(message)}</p>{form}'
        "<style>button{font:700 16px inherit;padding:12px 22px;background:#C0FE73;border:2px solid #222;border-radius:2px;"
        "cursor:pointer}</style></body></html>",
        headers={"Cache-Control": "no-store", "Referrer-Policy": "no-referrer"},
    )


@router.get("/v1/unsubscribe/{token}", include_in_schema=False)
async def unsubscribe_page(token: str, db: AsyncSession = Depends(get_session)) -> HTMLResponse:
    pref = (await db.execute(select(MarketingPref).where(MarketingPref.token == token))).scalar_one_or_none()
    if pref is None:
        raise HTTPException(404, "This link isn't valid.")
    if pref.opted_out_at is not None:
        return _page(
            "You're unsubscribed",
            "You won't get marketing emails from Cover Founder. Account emails (sign-in codes, receipts) still arrive.",
        )
    return _page(
        "Stop marketing emails?",
        "You'll stop getting product tips and offers. Account emails such as sign-in codes and receipts will still arrive.",
        "Unsubscribe",
    )


@router.post("/v1/unsubscribe/{token}", include_in_schema=False)
async def unsubscribe(token: str, request: Request, db: AsyncSession = Depends(get_session)) -> HTMLResponse:
    """The button on the page, and the mail app's one-click unsubscribe (RFC 8058) which posts here directly."""
    one_click = "one-click" in (await request.body()).decode("utf-8", "ignore").lower()
    pref = await marketing.set_opt_out(db, token, True, "one_click" if one_click else "link")
    if pref is None:
        raise HTTPException(404, "This link isn't valid.")
    await db.commit()
    return _page(
        "You're unsubscribed",
        "You won't get marketing emails from Cover Founder. Account emails (sign-in codes, receipts) still arrive.",
    )
