import json
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import delete, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import Principal, current_principal
from app.db import get_session
from app.integrations import registry
from app.models import Asset, Brief, InterviewSession, Job, Project, ScriptVersion, ShareLink, Take
from app.pipeline.advance import advance
from app.pipeline.takes import chunk_key
from app.schemas.api import ApproveIn, ProjectCreate, ProjectOut, ScriptOut, ScriptUpdate
from app.services import interview as iv
from app.services import state_machine as sm
from app.services.brand import ALLOWED_VOICE_ACCENTS
from app.services.claims import detect_claims
from app.services.ratelimit import limit
from app.services.safety import find_banned, text_overflow

router = APIRouter(prefix="/v1/projects", tags=["projects"])

WORDS_PER_SECOND = 2.5


async def _owned(session: AsyncSession, project_id: str, p: Principal) -> Project:
    project = await session.get(Project, project_id)
    if project is None or project.workspace_id != p.workspace.id:
        raise HTTPException(404, "Project not found")
    return project


async def _out(session: AsyncSession, project: Project) -> ProjectOut:
    assets = (await session.execute(select(Asset).where(Asset.project_id == project.id))).scalars().all()
    out = ProjectOut.model_validate(project)
    out.assets = [a for a in assets]  # type: ignore[misc]
    return out


async def _latest_script(session: AsyncSession, project_id: str) -> ScriptVersion | None:
    return (
        (
            await session.execute(
                select(ScriptVersion)
                .where(ScriptVersion.project_id == project_id)
                .order_by(ScriptVersion.version.desc())
            )
        )
        .scalars()
        .first()
    )


@router.post("", response_model=ProjectOut, dependencies=[Depends(limit("brief", 20, 3600))])
async def create_project(
    body: ProjectCreate, p: Principal = Depends(current_principal), session: AsyncSession = Depends(get_session)
) -> ProjectOut:
    if p.workspace.suspended:
        raise HTTPException(403, "Workspace suspended")
    if body.voice_accent not in ALLOWED_VOICE_ACCENTS:
        raise HTTPException(422, {"error": "invalid_voice_accent", "allowed": ALLOWED_VOICE_ACCENTS})
    project = Project(
        workspace_id=p.workspace.id,
        region=body.region,
        voice_accent=body.voice_accent,
        accent_override=body.accent_override,
    )
    session.add(project)
    await session.flush()
    session.add(Brief(project_id=project.id, raw_text=body.brief_text, website_url=body.website_url))
    await session.commit()
    return await _out(session, project)


@router.get("/{project_id}", response_model=ProjectOut)
async def get_project(
    project_id: str, p: Principal = Depends(current_principal), session: AsyncSession = Depends(get_session)
) -> ProjectOut:
    return await _out(session, await _owned(session, project_id, p))


@router.post(
    "/{project_id}/script/generate", response_model=ScriptOut, dependencies=[Depends(limit("script", 15, 3600))]
)
async def generate_script(
    project_id: str, p: Principal = Depends(current_principal), session: AsyncSession = Depends(get_session)
) -> ScriptVersion:
    project = await _owned(session, project_id, p)
    if project.state not in {"draft", "script_ready"}:
        raise HTTPException(409, "Script can no longer be regenerated")
    llm = registry.get_llm()
    brief = project.brief
    if brief is None:
        raise HTTPException(409, "Project has no brief")
    # Stages 1 and 2 are cheap; they are not charged against render budgets (spec section 8).
    brief.structured_facts = await llm.parse_brief(brief.raw_text, brief.website_url)
    draft = await llm.write_script(brief.structured_facts, "confident")
    prev = await _latest_script(session, project_id)
    sv = ScriptVersion(
        project_id=project_id,
        version=(prev.version + 1) if prev else 1,
        segments=[s.model_dump() for s in draft.segments],
        ticker_lines=draft.ticker_lines,
        lower_thirds=draft.lower_thirds,
        interview_questions=draft.interview_questions,
        claim_flags=[c.model_dump() for c in draft.claim_flags],
    )
    session.add(sv)
    if project.state == "draft":
        sm.transition(project, "script_ready")
    await session.commit()
    return sv


@router.get("/{project_id}/script", response_model=ScriptOut)
async def get_script(
    project_id: str, p: Principal = Depends(current_principal), session: AsyncSession = Depends(get_session)
) -> ScriptVersion:
    await _owned(session, project_id, p)
    sv = await _latest_script(session, project_id)
    if sv is None:
        raise HTTPException(404, "No script yet")
    return sv


@router.put("/{project_id}/script", response_model=ScriptOut)
async def update_script(
    project_id: str,
    body: ScriptUpdate,
    p: Principal = Depends(current_principal),
    session: AsyncSession = Depends(get_session),
) -> ScriptVersion:
    project = await _owned(session, project_id, p)
    if project.state != "script_ready":
        raise HTTPException(409, "Script is locked")
    prev = await _latest_script(session, project_id)
    text = " ".join(s.get("text", "") for s in body.segments)
    flags = [c.model_dump() for c in detect_claims(text)]
    for f in flags:  # confirmation carries over only for claim text the owner explicitly confirms
        f["confirmed"] = f["text"] in body.confirmed_claims
    sv = ScriptVersion(
        project_id=project_id,
        version=(prev.version + 1) if prev else 1,
        segments=body.segments,
        ticker_lines=body.ticker_lines,
        lower_thirds=body.lower_thirds,
        interview_questions=body.interview_questions,
        claim_flags=flags,
    )
    session.add(sv)
    await session.commit()
    return sv


@router.post("/{project_id}/script/approve", response_model=ProjectOut)
async def approve_script(
    project_id: str,
    body: ApproveIn | None = None,
    p: Principal = Depends(current_principal),
    session: AsyncSession = Depends(get_session),
) -> ProjectOut:
    project = await _owned(session, project_id, p)
    sv = await _latest_script(session, project_id)
    if project.state != "script_ready" or sv is None:
        raise HTTPException(409, "No script ready for approval")
    unconfirmed = [f for f in sv.claim_flags if not f.get("confirmed")]
    if unconfirmed:  # hard rule 3
        raise HTTPException(
            422,
            {
                "error": "claims_unconfirmed",
                "message": "Please confirm each flagged claim before approving.",
                "claims": unconfirmed,
            },
        )
    banned = find_banned(json.dumps([sv.segments, sv.ticker_lines, sv.lower_thirds, sv.interview_questions]))
    if banned:  # hard rule 1: checked before any paid step runs
        raise HTTPException(
            422,
            {
                "error": "banned_network_name",
                "message": "Please remove real news network names: " + ", ".join(banned),
                "terms": banned,
            },
        )
    too_long = text_overflow(sv.lower_thirds, sv.ticker_lines)
    if too_long:  # keeps text inside the broadcast layout (the renderer never wraps or shrinks it)
        raise HTTPException(422, {"error": "text_too_long", "message": too_long})
    ws = p.workspace
    words = sum(len(s["text"].split()) for s in sv.segments)
    if words / WORDS_PER_SECOND > ws.max_video_seconds:
        raise HTTPException(422, "Script is longer than your plan allows")
    since = datetime.now(UTC) - timedelta(days=1)
    today = (
        await session.execute(
            select(func.count())
            .select_from(ScriptVersion)
            .join(Project, Project.id == ScriptVersion.project_id)
            .where(Project.workspace_id == ws.id, ScriptVersion.approved_at >= since)
        )
    ).scalar_one()
    if today >= ws.max_videos_per_day:
        raise HTTPException(429, "Daily video limit reached")
    with_interview = bool(body and body.with_interview)
    if with_interview and not (1 <= len(sv.interview_questions) <= iv.MAX_QUESTIONS):
        raise HTTPException(
            422,
            {"error": "interview_questions", "message": f"An interview needs 1 to {iv.MAX_QUESTIONS} questions."},
        )
    if with_interview and any(not q.strip() or len(q) > 200 for q in sv.interview_questions):
        raise HTTPException(422, {"error": "interview_questions", "message": "Each question must be 1-200 characters."})
    banned_q = find_banned(" ".join(sv.interview_questions))
    if banned_q:
        raise HTTPException(
            422,
            {
                "error": "banned_network_name",
                "message": "Please remove real news network names: " + ", ".join(banned_q),
            },
        )
    project.interview_enabled = with_interview
    sv.approved, sv.approved_by, sv.approved_at = True, p.user.email, datetime.now(UTC)
    sm.transition(project, "script_approved")
    await session.commit()
    await advance(session, project_id)  # paid pipeline starts; every paid step passes the spend guard
    await session.refresh(project)
    return await _out(session, project)


@router.post("/{project_id}/retry", response_model=ProjectOut)
async def retry(
    project_id: str, p: Principal = Depends(current_principal), session: AsyncSession = Depends(get_session)
) -> ProjectOut:
    project = await _owned(session, project_id, p)
    try:
        sm.resume(project)
    except sm.IllegalTransition:
        raise HTTPException(409, "Project is not retryable") from None
    await session.commit()
    await advance(session, project_id)
    await session.refresh(project)
    return await _out(session, project)


IN_FLIGHT = {"script_approved", "rendering_anchor", "anchor_ready", "merging"}


@router.delete("/{project_id}")
async def delete_project(
    project_id: str, p: Principal = Depends(current_principal), session: AsyncSession = Depends(get_session)
) -> dict:
    """Owner can delete a project at any time it isn't mid-render. Removes files and all records."""
    project = await _owned(session, project_id, p)
    if project.state in IN_FLIGHT:
        raise HTTPException(409, "This video is being made. Delete it once it finishes or fails.")
    storage = registry.get_storage()
    assets = (await session.execute(select(Asset).where(Asset.project_id == project_id))).scalars().all()
    for a in assets:
        await storage.delete(a.storage_key)
    for t in (await session.execute(select(Take).where(Take.project_id == project_id))).scalars():
        for idx in list(t.chunks or {}):
            await storage.delete(chunk_key(project_id, t.id, int(idx)))
        for k in (t.processed_video_key, t.processed_audio_key):
            if k:
                await storage.delete(k)
    for s in (
        await session.execute(select(InterviewSession).where(InterviewSession.project_id == project_id))
    ).scalars():
        if s.photo_key:
            await storage.delete(s.photo_key)
    for model in (Take, Asset, Job, ScriptVersion, ShareLink, InterviewSession):
        await session.execute(delete(model).where(model.project_id == project_id))
    await session.execute(delete(Brief).where(Brief.project_id == project_id))
    await session.delete(project)
    await session.commit()
    return {"ok": True}
