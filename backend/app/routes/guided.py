"""Guided flow endpoints: start the interview from the intake form, and read the written story."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import Principal, current_principal
from app.db import get_session
from app.models import Project, ScriptVersion
from app.schemas.api import ProjectOut
from app.services import guided
from app.services.ratelimit import limit

router = APIRouter(prefix="/v1/projects/{project_id}", tags=["guided"])


async def _owned(session: AsyncSession, project_id: str, p: Principal) -> Project:
    project = await session.get(Project, project_id)
    if project is None or project.workspace_id != p.workspace.id:
        raise HTTPException(404, "Project not found")
    return project


@router.post("/guided/start", response_model=ProjectOut, dependencies=[Depends(limit("guided-start", 20, 3600))])
async def start(
    project_id: str, p: Principal = Depends(current_principal), session: AsyncSession = Depends(get_session)
) -> ProjectOut:
    """Details are in: work out the story and open the AI interview (free; nothing is rendered)."""
    from app.routes.projects import _out

    project = await _owned(session, project_id, p)
    await guided.start(session, project)
    await session.refresh(project)
    return await _out(session, project)


@router.get("/story")
async def story(
    project_id: str, p: Principal = Depends(current_principal), session: AsyncSession = Depends(get_session)
) -> dict:
    """The news story and the social post written after the interview."""
    await _owned(session, project_id, p)
    sv = (
        (
            await session.execute(
                select(ScriptVersion)
                .where(ScriptVersion.project_id == project_id, ScriptVersion.story.is_not(None))
                .order_by(ScriptVersion.version.desc())
            )
        )
        .scalars()
        .first()
    )
    if sv is None:
        raise HTTPException(404, "The story isn't written yet.")
    return sv.story or {}
