"""Product footage for a project: choose what to show, and optionally generate synthetic shots."""

import uuid
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import Principal, current_principal
from app.db import get_session
from app.integrations import registry
from app.integrations.errors import classify
from app.models import Asset, Project
from app.schemas.api import BrollCandidate, BrollGenerateIn, BrollItemOut, BrollOut, BrollPutIn
from app.services import broll as svc
from app.services import moderation
from app.services.ratelimit import limit
from app.services.spend_guard import LimitReached, SpendGuard

router = APIRouter(prefix="/v1/projects/{project_id}/broll", tags=["broll"])
NOT_NOW = {"merging", "failed", "limit_reached", "cancelled", "final_ready", "draft"}


async def _owned(session: AsyncSession, project_id: str, p: Principal) -> Project:
    project = await session.get(Project, project_id)
    if project is None or project.workspace_id != p.workspace.id:
        raise HTTPException(404, "Project not found")
    return project


async def _out(session: AsyncSession, project: Project) -> BrollOut:
    ai = registry.get_broll()
    return BrollOut(
        items=[BrollItemOut(**i) for i in (project.broll or [])],
        candidates=[BrollCandidate(**c) for c in await svc.candidates(session, project)],
        ai_available=ai is not None,
        note=None
        if ai is not None
        else "AI-generated shots aren't set up for this product yet. Upload your own footage.",
    )


@router.get("", response_model=BrollOut)
async def get_broll(
    project_id: str, p: Principal = Depends(current_principal), session: AsyncSession = Depends(get_session)
) -> BrollOut:
    return await _out(session, await _owned(session, project_id, p))


def _editable(project: Project) -> None:
    if not project.interview_enabled:
        raise HTTPException(409, "Product footage is used in interview videos.")
    if project.state in NOT_NOW:
        raise HTTPException(409, "Product footage can't be changed in this state.")


@router.put("", response_model=BrollOut)
async def put_broll(
    project_id: str,
    body: BrollPutIn,
    p: Principal = Depends(current_principal),
    session: AsyncSession = Depends(get_session),
) -> BrollOut:
    project = await _owned(session, project_id, p)
    _editable(project)
    try:
        project.broll = svc.normalise(
            [i.model_dump() for i in body.items], await svc.candidates(session, project, with_urls=False)
        )
    except ValueError as e:
        raise HTTPException(422, str(e)) from None
    await session.commit()
    return await _out(session, project)


@router.post("/generate", response_model=BrollOut, dependencies=[Depends(limit("broll", 10, 3600))])
async def generate_broll(
    project_id: str,
    body: BrollGenerateIn,
    p: Principal = Depends(current_principal),
    session: AsyncSession = Depends(get_session),
) -> BrollOut:
    """Make one SYNTHETIC shot. It is stored as a candidate, labelled as AI-generated wherever it is used, and only
    appears in the video if the owner picks it. UNAVAILABLE until a real provider is configured: no fake result."""
    project = await _owned(session, project_id, p)
    _editable(project)
    ai = registry.get_broll()
    if ai is None:
        raise HTTPException(503, "AI-generated shots aren't set up for this product yet. Upload your own footage.")
    if moderation.screen_text(body.prompt).level == "block":
        raise HTTPException(422, "That description can't be used.")
    guard = SpendGuard(session)
    try:
        res = await guard.reserve(
            project.workspace_id,
            ai.name,
            ai.estimate_cost(body.prompt, body.seconds),
            project_id=project.id,
            stage="broll",
        )
    except LimitReached as e:
        raise HTTPException(402, e.reason) from None
    try:
        out = await ai.generate(body.prompt, body.seconds)
    except Exception as e:  # noqa: BLE001
        await guard.release(res)
        await session.commit()
        c = classify(e)
        raise HTTPException(502 if c.retryable else 422, "We couldn't make that shot. " + c.message) from None
    key = f"projects/{project.id}/broll-{uuid.uuid4().hex[:8]}.mp4"
    await registry.get_storage().put(key, out.data, out.content_type)
    session.add(Asset(project_id=project.id, type=svc.GENERATED_TYPE, storage_key=key, duration=out.duration_s))
    await guard.settle(res, out.cost)
    project.cost_total += Decimal(str(out.cost))
    await session.commit()
    return await _out(session, project)
