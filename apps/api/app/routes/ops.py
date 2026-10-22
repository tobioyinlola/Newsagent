"""Operator console: queue, jobs, cost report, moderation queue, system switches, audit log."""

import csv
import io
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Request
from fastapi.responses import Response
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import Principal, current_principal, operator
from app.config import VENDOR_POLICIES, get_settings
from app.db import get_session
from app.models import AuditLog, CreditTransaction, Job, ModerationCase, Project, SystemSetting, Take, Workspace
from app.pipeline.advance import advance
from app.schemas.api import (
    AuditOut,
    CostReport,
    CostRow,
    CostSummary,
    JobOut,
    ModerationCaseOut,
    ModerationDecisionIn,
    ProjectModerationOut,
    QueueOut,
    SettingsOut,
    SettingsPatch,
)
from app.services import moderation_flow
from app.services import state_machine as sm
from app.services.audit import audit
from app.services.spend_guard import is_paused

router = APIRouter(tags=["ops"])
STUCK_AFTER = timedelta(minutes=30)


# ---------- owner-visible moderation status ----------
@router.get("/v1/projects/{project_id}/moderation", response_model=list[ProjectModerationOut])
async def project_moderation(
    project_id: str, p: Principal = Depends(current_principal), session: AsyncSession = Depends(get_session)
) -> list[ModerationCase]:
    project = await session.get(Project, project_id)
    if project is None or project.workspace_id != p.workspace.id:
        raise HTTPException(404, "Project not found")
    rows = await session.execute(
        select(ModerationCase).where(ModerationCase.project_id == project_id).order_by(ModerationCase.created_at.desc())
    )
    return list(rows.scalars().all())


# ---------- review queue ----------
@router.get("/v1/admin/moderation", response_model=list[ModerationCaseOut])
async def moderation_queue(
    status: str = "pending", _: Principal = Depends(operator), session: AsyncSession = Depends(get_session)
) -> list[ModerationCaseOut]:
    q = select(ModerationCase, Workspace.name).join(
        Workspace, Workspace.id == ModerationCase.workspace_id, isouter=True
    )
    if status != "all":
        q = q.where(ModerationCase.status == status)
    rows = (await session.execute(q.order_by(ModerationCase.created_at).limit(200))).all()
    return [
        ModerationCaseOut(**{**{c.name: getattr(case, c.name) for c in case.__table__.columns}, "workspace_name": name})
        for case, name in rows
    ]


@router.post("/v1/admin/moderation/{case_id}/decision")
async def moderation_decision(
    case_id: str,
    body: ModerationDecisionIn,
    request: Request,
    op: Principal = Depends(operator),
    session: AsyncSession = Depends(get_session),
) -> dict:
    case = await session.get(ModerationCase, case_id)
    if case is None:
        raise HTTPException(404, "Case not found")
    if case.status != "pending":
        raise HTTPException(409, f"This case is already {case.status}.")
    await moderation_flow.decide(session, case, body.decision, body.note, op.user.email)
    audit(
        session,
        op.user.email,
        f"moderation.{body.decision}",
        target_type="case",
        target_id=case.id,
        detail={"project": case.project_id, "stage": case.stage, "reasons": case.reasons},
        request=request,
    )
    await session.commit()
    return {"ok": True, "status": case.status}


# ---------- queue and jobs ----------
@router.get("/v1/admin/queue", response_model=QueueOut)
async def queue(_: Principal = Depends(operator), session: AsyncSession = Depends(get_session)) -> QueueOut:
    async def counts(col) -> dict[str, int]:
        return {k: n for k, n in (await session.execute(select(col, func.count()).group_by(col))).all()}

    pending = (
        await session.execute(
            select(func.count()).select_from(ModerationCase).where(ModerationCase.status == "pending")
        )
    ).scalar_one()
    return QueueOut(
        jobs=await counts(Job.status),
        takes=await counts(Take.status),
        projects=await counts(Project.state),
        moderation_pending=pending,
        paused=await is_paused(session),
    )


@router.get("/v1/admin/jobs", response_model=list[JobOut])
async def jobs(
    status: str | None = None,
    stage: str | None = None,
    limit: int = 100,
    _: Principal = Depends(operator),
    session: AsyncSession = Depends(get_session),
) -> list[JobOut]:
    q = (
        select(Job, Workspace.name)
        .join(Project, Project.id == Job.project_id)
        .join(Workspace, Workspace.id == Project.workspace_id)
    )
    if status:
        q = q.where(Job.status == status)
    if stage:
        q = q.where(Job.stage == stage)
    rows = (await session.execute(q.order_by(Job.created_at.desc()).limit(min(max(limit, 1), 500)))).all()
    now = datetime.now(UTC)
    out = []
    for j, ws_name in rows:
        started = j.started_at.replace(tzinfo=UTC) if j.started_at and j.started_at.tzinfo is None else j.started_at
        stuck = (
            j.status == "running"
            and started is not None
            and now - started > max(STUCK_AFTER, timedelta(seconds=VENDOR_POLICIES["avatar"].timeout_s * 1.5))
        )
        out.append(
            JobOut(
                id=j.id,
                project_id=j.project_id,
                workspace_name=ws_name,
                stage=j.stage,
                vendor=j.vendor,
                status=j.status,
                attempts=j.attempts,
                cost=j.cost,
                duration_s=j.duration_s,
                error=j.error,
                created_at=j.created_at,
                stuck=stuck,
            )
        )
    return out


@router.post("/v1/admin/projects/{project_id}/retry")
async def operator_retry(
    project_id: str, request: Request, op: Principal = Depends(operator), session: AsyncSession = Depends(get_session)
) -> dict:
    """Restart a failed or paused project on the owner's behalf (e.g. after fixing a vendor outage)."""
    project = await session.get(Project, project_id)
    if project is None:
        raise HTTPException(404, "Project not found")
    try:
        sm.resume(project)
    except sm.IllegalTransition:
        raise HTTPException(409, "Project is not failed or paused") from None
    audit(session, op.user.email, "project.retry", target_type="project", target_id=project_id, request=request)
    await session.commit()
    await advance(session, project_id)
    return {"ok": True}


# ---------- cost report ----------
async def _cost_rows(session: AsyncSession, since: datetime) -> tuple[list[CostRow], Decimal]:
    usd_per_credit = Decimal(get_settings().usd_per_credit)
    projects = (
        await session.execute(
            select(Project, Workspace.name)
            .join(Workspace, Workspace.id == Project.workspace_id)
            .where(Project.created_at >= since)
            .order_by(Project.created_at.desc())
            .limit(1000)
        )
    ).all()
    ids = [p.id for p, _ in projects]
    by_project: dict[str, dict] = {i: {"cost": Decimal("0"), "credits": Decimal("0"), "vendors": {}} for i in ids}
    if ids:
        rows = (
            await session.execute(
                select(
                    CreditTransaction.project_id,
                    CreditTransaction.vendor,
                    func.sum(CreditTransaction.vendor_cost),
                    func.sum(CreditTransaction.amount),
                )
                .where(
                    CreditTransaction.project_id.in_(ids),
                    CreditTransaction.kind.in_(["usage", "usage_adjust", "usage_release"]),
                )
                .group_by(CreditTransaction.project_id, CreditTransaction.vendor)
            )
        ).all()
        for pid, vendor, cost, amount in rows:
            if pid not in by_project:
                continue
            d = by_project[pid]
            d["cost"] += Decimal(cost or 0)
            d["credits"] += -Decimal(amount or 0)
            d["vendors"][vendor or "unknown"] = Decimal(cost or 0)
    out = [
        CostRow(
            project_id=p.id,
            workspace_name=name,
            state=p.state,
            interview=p.interview_enabled,
            vendor_cost=by_project[p.id]["cost"],
            credits_charged=by_project[p.id]["credits"],
            margin=by_project[p.id]["credits"] * usd_per_credit - by_project[p.id]["cost"],
            by_vendor=by_project[p.id]["vendors"],
        )
        for p, name in projects
    ]
    return out, usd_per_credit


@router.get("/v1/admin/cost-report", response_model=CostReport)
async def cost_report(
    days: int = 90, _: Principal = Depends(operator), session: AsyncSession = Depends(get_session)
) -> CostReport:
    rows, usd = await _cost_rows(session, datetime.now(UTC) - timedelta(days=min(max(days, 1), 3650)))
    done = [r for r in rows if r.state == "final_ready"]
    n = len(done)
    avg = lambda f: (sum((f(r) for r in done), Decimal("0")) / n) if n else Decimal("0")  # noqa: E731
    return CostReport(
        summary=CostSummary(
            videos=n,
            avg_vendor_cost=avg(lambda r: r.vendor_cost),
            avg_credits_charged=avg(lambda r: r.credits_charged),
            avg_margin=avg(lambda r: r.margin),
            usd_per_credit=usd,
            markup=Decimal(get_settings().credit_markup),
        ),
        rows=rows,
    )


@router.get("/v1/admin/cost-report.csv")
async def cost_report_csv(
    days: int = 90, _: Principal = Depends(operator), session: AsyncSession = Depends(get_session)
) -> Response:
    rows, _usd = await _cost_rows(session, datetime.now(UTC) - timedelta(days=min(max(days, 1), 3650)))
    out = io.StringIO()
    w = csv.writer(out)
    w.writerow(["project_id", "workspace", "state", "interview", "vendor_cost", "credits_charged", "margin"])
    for r in rows:
        w.writerow(
            [
                r.project_id,
                r.workspace_name,
                r.state,
                r.interview,
                f"{r.vendor_cost:.4f}",
                f"{r.credits_charged:.4f}",
                f"{r.margin:.4f}",
            ]
        )
    return Response(
        out.getvalue(), media_type="text/csv", headers={"Content-Disposition": 'attachment; filename="cost-report.csv"'}
    )


# ---------- system switches ----------
async def _read_settings(session: AsyncSession) -> SettingsOut:
    async def val(key: str) -> dict:
        row = await session.get(SystemSetting, key)
        return row.value if row else {}

    pause, mod, avatar = await val("paid_steps_paused"), await val("moderation"), await val("avatar")
    return SettingsOut(
        paused=bool(pause.get("paused")),
        pause_reason=pause.get("reason", ""),
        moderation_mode=mod.get("mode", "enforce"),
        moderation_llm=bool(mod.get("llm", False)),
        avatar_primary=avatar.get("primary", "heygen"),
        avatar_secondary=avatar.get("secondary"),
        avatar_failover=bool(avatar.get("failover", False)),
    )


@router.get("/v1/admin/settings", response_model=SettingsOut)
async def get_system_settings(
    _: Principal = Depends(operator), session: AsyncSession = Depends(get_session)
) -> SettingsOut:
    return await _read_settings(session)


@router.patch("/v1/admin/settings", response_model=SettingsOut)
async def patch_system_settings(
    body: SettingsPatch,
    request: Request,
    op: Principal = Depends(operator),
    session: AsyncSession = Depends(get_session),
) -> SettingsOut:
    async def put(key: str, patch: dict) -> None:
        row = await session.get(SystemSetting, key)
        if row is None:
            row = SystemSetting(key=key, value={})
            session.add(row)
        row.value = {**row.value, **patch}  # reassign: JSON columns don't detect in-place edits
        row.updated_by, row.updated_at = op.user.email, datetime.now(UTC)

    if body.paused is not None or body.pause_reason is not None:
        cur = await _read_settings(session)
        await put(
            "paid_steps_paused",
            {
                "paused": cur.paused if body.paused is None else body.paused,
                "reason": cur.pause_reason if body.pause_reason is None else body.pause_reason,
            },
        )
    mod: dict = {k: v for k, v in {"mode": body.moderation_mode, "llm": body.moderation_llm}.items() if v is not None}
    if mod:
        await put("moderation", mod)
    av: dict = {}
    if body.avatar_primary is not None:
        av["primary"] = body.avatar_primary
    if body.avatar_secondary is not None:
        av["secondary"] = None if body.avatar_secondary == "none" else body.avatar_secondary
    if body.avatar_failover is not None:
        av["failover"] = body.avatar_failover
    if av:
        if av.get("primary") and av.get("primary") == av.get(
            "secondary", (await _read_settings(session)).avatar_secondary
        ):
            raise HTTPException(422, "The primary and secondary avatar providers must differ.")
        await put("avatar", av)
    audit(
        session,
        op.user.email,
        "settings.update",
        target_type="settings",
        detail=body.model_dump(exclude_none=True),
        request=request,
    )
    await session.commit()
    return await _read_settings(session)


@router.get("/v1/admin/audit", response_model=list[AuditOut])
async def audit_log(
    limit: int = 100,
    action: str | None = None,
    _: Principal = Depends(operator),
    session: AsyncSession = Depends(get_session),
) -> list[AuditLog]:
    q = select(AuditLog)
    if action:
        q = q.where(AuditLog.action.startswith(action))
    return list(
        (await session.execute(q.order_by(AuditLog.created_at.desc()).limit(min(max(limit, 1), 500)))).scalars().all()
    )
