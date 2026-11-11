"""Back office: marketing switches and status. Public: the unsubscribe page every marketing email links to."""

from html import escape

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import HTMLResponse
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import Principal, require
from app.db import get_session
from app.models import MarketingPref, MarketingSend, MarketingSuppression
from app.models.base import utcnow
from app.services import marketing
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
