"""Cookie-free website visitor counts: the beacon the public site sends, and the back-office report."""

from datetime import date, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import Principal, require
from app.db import get_session
from app.services import site_visits as svc
from app.services.ratelimit import client_ip, limit

router = APIRouter(tags=["site-visits"])


class VisitIn(BaseModel):
    path: str = Field(max_length=300)
    referrer_host: str = Field("", max_length=253)  # the other website they came from (host only), if any
    utm_source: str = Field("", max_length=100)
    utm_medium: str = Field("", max_length=100)
    utm_campaign: str = Field("", max_length=100)


@router.post("/v1/public/visit", status_code=204, dependencies=[Depends(limit("site-visit", 300, 600))])
async def visit(body: VisitIn, request: Request, db: AsyncSession = Depends(get_session)) -> Response:
    """One page opened on the public site. Counts nothing (and says nothing) if it must not be counted."""
    ua = request.headers.get("user-agent", "")
    if (
        request.headers.get("dnt") == "1"
        or request.headers.get("sec-gpc") == "1"
        or not ua.strip()
        or svc.BOT.search(ua)
    ):
        return Response(status_code=204)
    path = svc.normalize_path(body.path)
    if path is None:
        return Response(status_code=204)
    source, detail = svc.classify(body.referrer_host, body.utm_source, body.utm_medium, body.utm_campaign)
    day = svc.today()
    await svc.record(
        db, day=day, vhash=svc.visitor_hash(day, client_ip(request), ua), path=path, source=source, detail=detail
    )
    return Response(status_code=204)


@router.get("/v1/admin/site-visits")
async def site_visits(
    start: date | None = None,
    end: date | None = None,
    p: Principal = Depends(require("operations.view")),
    db: AsyncSession = Depends(get_session),
) -> dict:
    end = end or svc.today()
    start = start or end - timedelta(days=29)
    if start > end:
        raise HTTPException(422, "The start date must not be after the end date.")
    if (end - start).days > 365:
        raise HTTPException(422, "Choose a range of up to 366 days.")
    return await svc.report(db, start, end)
