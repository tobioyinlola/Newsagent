"""Public measurement intake, scoped reports and operator-entered publisher measurements."""

import csv
import io
import re
from datetime import date, timedelta
from typing import Literal
from uuid import UUID

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from fastapi.responses import Response
from pydantic import BaseModel, Field, model_validator
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import Principal, auth_ctx_any, current_principal, require
from app.db import get_session
from app.models import DistributionPlacement, DistributionRequest, Project, PublisherSnapshot, ShareLink, Workspace
from app.models.base import new_id, utcnow
from app.routes.stories import _listed
from app.services import analytics as service
from app.services import rbac
from app.services.audit import audit
from app.services.ratelimit import limit
from app.services.sessions import hash_token

router = APIRouter(tags=["analytics"])


class EventIn(BaseModel):
    kind: Literal["impression", "story_visit", "share_visit", "video_view", "video_complete"]
    session_id: UUID


class SnapshotIn(BaseModel):
    as_of: date
    views: int | None = Field(default=None, ge=0, le=1000000000000, strict=True)
    impressions: int | None = Field(default=None, ge=0, le=1000000000000, strict=True)
    source_note: str = Field(default="", max_length=2000)

    @model_validator(mode="after")
    def valid(self):
        if self.as_of > service.today() or self.as_of < date(2000, 1, 1):
            raise ValueError("Use a past or current reporting date, from year 2000 onward.")
        if self.views is None and self.impressions is None:
            raise ValueError("Enter views or impressions. Leave unknown metrics blank, not zero.")
        return self


async def measurement(db, project, body, request):
    if (
        request.headers.get("dnt") == "1"
        or request.headers.get("sec-gpc") == "1"
        or re.search(r"bot\b|crawler|spider|facebookexternalhit", request.headers.get("user-agent", ""), re.I)
    ):
        return {"recorded": False}
    authorization = request.headers.get("authorization")
    if authorization:
        try:
            ctx = await auth_ctx_any(authorization, db)
        except HTTPException:
            ctx = None
        if (
            ctx
            and ctx.otp_ok
            and (ctx.user.workspace_id == project.workspace_id or await rbac.permissions_for(db, ctx.user.email))
        ):
            return {"recorded": False}
    return {"recorded": await service.record(db, project.id, body.kind, body.session_id)}


@router.post("/v1/public/stories/{slug}/events", dependencies=[Depends(limit("audience-events", 600, 600))])
async def story_event(slug: str, body: EventIn, request: Request, db: AsyncSession = Depends(get_session)):
    project, _, _, assets = await _listed(db, slug)
    if body.kind == "share_visit":
        raise HTTPException(422, "Use a public story metric for this page")
    if body.kind in {"video_view", "video_complete"} and not any(a.type in {"render", "render_light"} for a in assets):
        raise HTTPException(404, "Video unavailable")
    return await measurement(db, project, body, request)


@router.post("/v1/share/{token}/events", dependencies=[Depends(limit("audience-events", 600, 600))])
async def share_event(token: str, body: EventIn, request: Request, db: AsyncSession = Depends(get_session)):
    link = (await db.execute(select(ShareLink).where(ShareLink.token_hash == hash_token(token)))).scalar_one_or_none()
    project = await db.get(Project, link.project_id) if link else None
    ws = await db.get(Workspace, project.workspace_id) if project else None
    if (
        not link
        or link.revoked_at
        or not project
        or not ws
        or ws.deleted_at
        or ws.suspended
        or ws.share_disabled
        or project.state != "final_ready"
    ):
        raise HTTPException(404, "Shared video unavailable")
    if body.kind not in {"share_visit", "video_view", "video_complete"}:
        raise HTTPException(422, "Use a shared-video metric for this page")
    return await measurement(db, project, body, request)


def dates(start, end):
    end = end or service.today()
    start = start or end - timedelta(days=29)
    if end > service.today() or start > end or (end - start).days > 365 or start < date(2000, 1, 1):
        raise HTTPException(422, "Choose a valid UTC date range of up to 366 days, ending no later than today.")
    return start, end


async def scoped_report(db, p, start, end, project_id, workspace_id=None, admin=False):
    start, end = dates(start, end)
    scope = workspace_id if admin else p.workspace.id
    if project_id:
        project = await db.get(Project, project_id)
        if not project or (scope and project.workspace_id != scope):
            raise HTTPException(404, "Story not found")
    return await service.report(db, start, end, workspace_id=scope, project_id=project_id, admin=admin)


@router.get("/v1/analytics")
async def customer_report(
    start: date | None = None,
    end: date | None = None,
    project_id: str | None = None,
    p: Principal = Depends(current_principal),
    db: AsyncSession = Depends(get_session),
):
    return await scoped_report(db, p, start, end, project_id)


@router.get("/v1/admin/analytics")
async def admin_report(
    start: date | None = None,
    end: date | None = None,
    project_id: str | None = None,
    workspace_id: str | None = None,
    p: Principal = Depends(require("operations.view")),
    db: AsyncSession = Depends(get_session),
):
    return await scoped_report(db, p, start, end, project_id, workspace_id, admin=True)


def csv_cell(value):
    value = str(value)
    return "'" + value if value.lstrip().startswith(("=", "+", "-", "@")) else value


def export_csv(data):
    out = io.StringIO()
    writer = csv.writer(out)
    writer.writerow(["Source", "Date", "Story / outlet", "Metric", "Value", "Basis"])
    for row in data["series"]:
        for name in service.METRICS:
            writer.writerow(
                ["Cover Founder", row["date"], "All selected stories", name, row[name], "daily recorded sessions"]
            )
    for channel in data["channels"]:
        for row in channel["history"]:
            for metric in ("views", "impressions"):
                if row[metric] is not None:
                    writer.writerow(
                        [
                            "Publisher report",
                            row["as_of"],
                            csv_cell(channel["outlet"] + " — " + channel["headline"]),
                            metric,
                            row[metric],
                            "cumulative as reported",
                        ]
                    )
    return Response(
        out.getvalue(),
        media_type="text/csv",
        headers={"Content-Disposition": 'attachment; filename="audience-report.csv"', "Cache-Control": "no-store"},
    )


@router.get("/v1/analytics/export.csv")
async def customer_csv(
    start: date | None = None,
    end: date | None = None,
    project_id: str | None = None,
    p: Principal = Depends(current_principal),
    db: AsyncSession = Depends(get_session),
):
    return export_csv(await scoped_report(db, p, start, end, project_id))


@router.get("/v1/admin/analytics/export.csv")
async def admin_csv(
    start: date | None = None,
    end: date | None = None,
    project_id: str | None = None,
    workspace_id: str | None = None,
    p: Principal = Depends(require("operations.view")),
    db: AsyncSession = Depends(get_session),
):
    return export_csv(await scoped_report(db, p, start, end, project_id, workspace_id, admin=True))


@router.put("/v1/admin/analytics/placements/{placement_id}/snapshots")
async def save_snapshot(
    placement_id: str,
    body: SnapshotIn,
    p: Principal = Depends(require("operations.manage")),
    db: AsyncSession = Depends(get_session),
):
    placement = (
        await db.execute(
            update(DistributionPlacement)
            .where(DistributionPlacement.id == placement_id)
            .values(updated_at=utcnow())
            .returning(DistributionPlacement)
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()
    request = await db.get(DistributionRequest, placement.request_id) if placement else None
    if not placement or not request or not request.paid_at:
        raise HTTPException(404, "Paid outlet placement not found")
    if not placement.published_url or placement.status != "published":
        raise HTTPException(409, "Record the published post URL before entering publisher performance.")
    row = (
        await db.execute(
            select(PublisherSnapshot).where(
                PublisherSnapshot.placement_id == placement_id, PublisherSnapshot.as_of == body.as_of
            )
        )
    ).scalar_one_or_none()
    before = service.snapshot_output(row, admin=True) if row else None
    if row is None:
        project = await db.get(Project, request.data.get("project_id", ""))
        row = PublisherSnapshot(
            id=new_id(),
            workspace_id=request.workspace_id,
            request_id=request.id,
            placement_id=placement_id,
            project_id=project.id if project else None,
            as_of=body.as_of,
        )
        db.add(row)
    row.views, row.impressions, row.source_note = body.views, body.impressions, body.source_note.strip()
    row.updated_by, row.updated_at = p.user.email, utcnow()
    await db.flush()
    audit(
        db,
        p.user.email,
        "analytics.publisher_snapshot_saved",
        target_type="distribution",
        target_id=request.id,
        detail={"placement_id": placement_id, "before": before, "after": service.snapshot_output(row, admin=True)},
    )
    await db.commit()
    return service.snapshot_output(row, admin=True)


@router.delete("/v1/admin/analytics/snapshots/{id}")
async def remove_snapshot(
    id: str, p: Principal = Depends(require("operations.manage")), db: AsyncSession = Depends(get_session)
):
    row = await db.get(PublisherSnapshot, id)
    if not row:
        raise HTTPException(404, "Publisher snapshot not found")
    audit(
        db,
        p.user.email,
        "analytics.publisher_snapshot_removed",
        target_type="distribution",
        target_id=row.request_id,
        detail={"before": service.snapshot_output(row, admin=True)},
    )
    await db.delete(row)
    await db.commit()
    return {"removed": True}


@router.get("/v1/admin/analytics/placements/{placement_id}/snapshots")
async def snapshot_history(
    placement_id: str, p: Principal = Depends(require("operations.view")), db: AsyncSession = Depends(get_session)
):
    placement = await db.get(DistributionPlacement, placement_id)
    if not placement:
        raise HTTPException(404, "Placement not found")
    rows = (
        (
            await db.execute(
                select(PublisherSnapshot)
                .where(PublisherSnapshot.placement_id == placement_id)
                .order_by(PublisherSnapshot.as_of.desc())
            )
        )
        .scalars()
        .all()
    )
    return [service.snapshot_output(row, admin=True) for row in rows]


class MetricsRequestIn(BaseModel):
    idempotency_key: str = Field(min_length=16, max_length=64, pattern=r"^[A-Za-z0-9_-]+$")


@router.post("/v1/admin/analytics/placements/{placement_id}/request-metrics")
async def request_metrics(
    placement_id: str,
    body: MetricsRequestIn,
    tasks: BackgroundTasks,
    p: Principal = Depends(require("operations.manage")),
    db: AsyncSession = Depends(get_session),
):
    from app.services import distribution as delivery

    placement = (
        await db.execute(
            update(DistributionPlacement)
            .where(DistributionPlacement.id == placement_id)
            .values(updated_at=utcnow())
            .returning(DistributionPlacement)
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()
    row = await db.get(DistributionRequest, placement.request_id) if placement else None
    if not placement or not row or not row.paid_at:
        raise HTTPException(404, "Paid placement not found")
    if placement.status != "published" or not placement.published_url or not placement.contact_email:
        raise HTTPException(
            409, "Save a published link and publisher contact in Distribution before requesting metrics."
        )
    text = (
        f"Hello,\n\nI'm following up from Cover Founder about our client's announcement on {placement.data['name']}.\n\n"
        f"Headline: {row.data['headline']}\nPublished post: {placement.published_url}\n\n"
        f"Please share the latest cumulative views and impressions as of {service.today().isoformat()}, including the reporting date, timezone and how each metric is defined. "
        "A dated breakdown, report or screenshot is helpful. If a metric is unavailable, please say so rather than reporting it as zero.\n\n"
        "Please reply directly to this email. Our team will review your figures and update the client's performance report.\n\nKind regards,\nThe Cover Founder team"
    )
    await delivery.queue_mail(
        db,
        row,
        "metrics_request",
        placement.contact_email,
        "Performance report request: " + row.data["headline"],
        text,
        key=placement.id + ":" + body.idempotency_key,
        placement=placement,
    )
    audit(
        db,
        p.user.email,
        "analytics.metrics_requested",
        target_type="distribution",
        target_id=row.id,
        detail={"placement_id": placement.id, "recipient": placement.contact_email},
    )
    await db.commit()
    tasks.add_task(delivery.deliver_request, row.id)
    return {"status": "queued"}
