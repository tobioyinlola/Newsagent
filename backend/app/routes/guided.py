"""Guided flow endpoints: start the interview from the intake form, and read the written story."""

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
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


async def _latest_story_version(session: AsyncSession, project_id: str) -> ScriptVersion | None:
    return (
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


@router.get("/story")
async def story(
    project_id: str, p: Principal = Depends(current_principal), session: AsyncSession = Depends(get_session)
) -> dict:
    """The news story and the social post written after the interview."""
    await _owned(session, project_id, p)
    sv = await _latest_story_version(session, project_id)
    if sv is None:
        raise HTTPException(404, "The story isn't written yet.")
    return sv.story or {}


class StoryEdit(BaseModel):
    """The owner's own wording of the press release: its subject (headline), summary line and body paragraphs."""

    headline: str = Field(min_length=1, max_length=200)
    dek: str = Field(default="", max_length=500)
    paragraphs: list[str] = Field(min_length=1, max_length=30)

    @field_validator("headline", "dek")
    @classmethod
    def _tidy(cls, v: str, info) -> str:
        v = " ".join(v.split())
        if info.field_name == "headline" and not v:
            raise ValueError("The subject can't be empty.")
        return v

    @field_validator("paragraphs")
    @classmethod
    def _paragraphs(cls, v: list[str]) -> list[str]:
        cleaned = [" ".join(x.split()) for x in v]
        cleaned = [x for x in cleaned if x]
        if not cleaned:
            raise ValueError("The press release needs some text.")
        if any(len(x) > 3000 for x in cleaned) or sum(len(x) for x in cleaned) > 12000:
            raise ValueError("The press release is too long.")
        return cleaned


@router.put("/story", dependencies=[Depends(limit("story-edit", 60, 3600))])
async def edit_story(
    project_id: str,
    body: StoryEdit,
    p: Principal = Depends(current_principal),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Let the owner change the press release before they approve it. Only while the story is being reviewed;
    the social post and the presenter's words are not touched. Moderation screens it when the owner approves."""
    project = await _owned(session, project_id, p)
    if project.state != "script_ready":
        raise HTTPException(
            409, "The press release can be edited while you are reviewing your story, before you approve it."
        )
    sv = await _latest_story_version(session, project_id)
    if sv is None or sv.approved:
        raise HTTPException(
            409, "The press release can be edited while you are reviewing your story, before you approve it."
        )
    story = dict(sv.story or {})
    heading = next((str(x.get("heading") or "") for x in story.get("sections") or [] if isinstance(x, dict)), "")
    story.update(headline=body.headline, dek=body.dek, sections=[{"heading": heading, "paragraphs": body.paragraphs}])
    sv.story = story  # a new dict, so the change is saved
    await session.commit()
    return story
