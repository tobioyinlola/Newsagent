"""Owner-side founder interview endpoints (authenticated). Guest endpoints live in routes/guest.py."""

from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import Principal, current_principal
from app.config import get_settings
from app.db import get_session
from app.integrations import registry
from app.models import InterviewSession, Project, Take
from app.pipeline.advance import advance
from app.pipeline.steps import approved_script, default_plan, latest_takes
from app.schemas.api import (
    InterviewInviteIn,
    InterviewInviteOut,
    InterviewStatusOut,
    KeepRawIn,
    MergePlanIn,
    ProjectOut,
    RetakeIn,
    TakeOut,
)
from app.services import crypto, moderation_flow
from app.services import interview as iv
from app.services import state_machine as sm
from app.services.moderation import fingerprint
from app.services.notifications import email_founder_invite, email_founder_retake
from app.services.ratelimit import limit

router = APIRouter(prefix="/v1/projects/{project_id}", tags=["interview"])
URL_TTL = 3600


async def _owned(session: AsyncSession, project_id: str, p: Principal) -> Project:
    project = await session.get(Project, project_id)
    if project is None or project.workspace_id != p.workspace.id:
        raise HTTPException(404, "Project not found")
    return project


async def active_session(session: AsyncSession, project_id: str) -> InterviewSession | None:
    return (
        (
            await session.execute(
                select(InterviewSession)
                .where(InterviewSession.project_id == project_id, InterviewSession.revoked_at.is_(None))
                .order_by(InterviewSession.created_at.desc())
            )
        )
        .scalars()
        .first()
    )


def take_out(t: Take, attempts: int, include_urls: bool) -> TakeOut:
    storage = registry.get_storage()
    return TakeOut(
        id=t.id,
        question_index=t.question_index,
        kind=t.kind,
        status=t.status,
        flags=list(t.flags or []),
        messages=iv.flag_messages(list(t.flags or [])),
        duration_s=t.duration_s,
        transcript=t.transcript,
        attempts=attempts,
        video_url=storage.presign_get(t.processed_video_key, URL_TTL)
        if include_urls and t.processed_video_key
        else None,
        audio_url=storage.presign_get(t.processed_audio_key, URL_TTL)
        if include_urls and t.processed_audio_key
        else None,
    )


async def attempts_by_question(session: AsyncSession, project_id: str) -> dict[int, int]:
    rows = await session.execute(
        select(Take.question_index, func.count()).where(Take.project_id == project_id).group_by(Take.question_index)
    )
    return {q: n for q, n in rows.all()}


@router.post("/interview", response_model=InterviewInviteOut, dependencies=[Depends(limit("magic-link", 20, 3600))])
async def create_invite(
    project_id: str,
    body: InterviewInviteIn,
    p: Principal = Depends(current_principal),
    session: AsyncSession = Depends(get_session),
) -> InterviewInviteOut:
    project = await _owned(session, project_id, p)
    if project.state != "awaiting_founder":
        raise HTTPException(409, "The interview questions aren't ready yet.")
    now = datetime.now(UTC)
    for old in (
        await session.execute(
            select(InterviewSession).where(
                InterviewSession.project_id == project_id, InterviewSession.revoked_at.is_(None)
            )
        )
    ).scalars():  # one live link per project: a new link replaces the old one
        old.revoked_at, old.token_enc = now, None
    token = iv.new_token()
    days = get_settings().interview_expiry_days
    s = InterviewSession(
        project_id=project_id,
        token_hash=iv.hash_token(token),
        founder_name=body.founder_name.strip(),
        founder_title=body.founder_title.strip(),
        founder_email=body.founder_email,
        invited_at=now,
        expiry=now + timedelta(days=days),
        token_enc=crypto.encrypt(token),
    )
    session.add(s)
    await session.commit()
    emailed = False
    if body.founder_email:
        script = await approved_script(session, project_id)
        company = (script.lower_thirds[0].get("title") if script.lower_thirds else "") or p.workspace.name
        emailed = await email_founder_invite(body.founder_email, s.founder_name, company, token, days)
    return InterviewInviteOut(url=f"{get_settings().app_base_url}/i/{token}", expires_at=s.expiry, emailed=emailed)


@router.delete("/interview")
async def revoke_invite(
    project_id: str, p: Principal = Depends(current_principal), session: AsyncSession = Depends(get_session)
) -> dict:
    await _owned(session, project_id, p)
    s = await active_session(session, project_id)
    if s:
        s.revoked_at, s.token_enc = datetime.now(UTC), None
        await session.commit()
    return {"ok": True}


@router.get("/interview", response_model=InterviewStatusOut)
async def interview_status(
    project_id: str, p: Principal = Depends(current_principal), session: AsyncSession = Depends(get_session)
) -> InterviewStatusOut:
    project = await _owned(session, project_id, p)
    if not project.interview_enabled:
        return InterviewStatusOut(active=False)
    script = await approved_script(session, project_id)
    s = await active_session(session, project_id)
    takes = await latest_takes(session, project_id)
    attempts = await attempts_by_question(session, project_id)
    storage = registry.get_storage()
    return InterviewStatusOut(
        active=s is not None,
        founder_name=s.founder_name if s else None,
        founder_title=s.founder_title if s else None,
        founder_email=s.founder_email if s else None,
        expires_at=s.expiry if s else None,
        submitted=bool(s and s.submitted_at),
        consented=bool(s and s.consent_at),
        reminders_sent=s.reminders_sent if s else 0,
        questions=list(script.interview_questions),
        takes=[take_out(t, attempts.get(q, 1), True) for q, t in sorted(takes.items()) if t.status != "recording"],
        plan=project.merge_plan or default_plan(len(script.interview_questions)),
        photo_url=storage.presign_get(s.photo_key, URL_TTL) if s and s.photo_key else None,
    )


@router.put("/interview/plan")
async def save_plan(
    project_id: str,
    body: MergePlanIn,
    p: Principal = Depends(current_principal),
    session: AsyncSession = Depends(get_session),
) -> dict:
    project = await _owned(session, project_id, p)
    if project.state not in {"awaiting_founder", "processing_founder"}:
        raise HTTPException(409, "The layout can only be changed before the final video is made.")
    script = await approved_script(session, project_id)
    takes = await latest_takes(session, project_id)
    try:
        plan = iv.validate_plan(
            body.model_dump(), len(script.interview_questions), {q: float(t.duration_s or 0) for q, t in takes.items()}
        )
    except iv.InvalidPlan as e:
        raise HTTPException(422, {"error": "invalid_plan", "message": str(e)}) from None
    project.merge_plan, project.layout = plan, plan["layout"]
    await session.commit()
    return plan


@router.post("/interview/merge", response_model=ProjectOut)
async def make_final(
    project_id: str, p: Principal = Depends(current_principal), session: AsyncSession = Depends(get_session)
) -> ProjectOut:
    """Start the merge. From awaiting_founder this is the anchor-only fallback (skip the interview)."""
    from app.routes.projects import _out

    project = await _owned(session, project_id, p)
    if project.state not in {"awaiting_founder", "processing_founder"}:
        raise HTTPException(409, "Nothing to merge yet.")
    if project.state == "processing_founder":
        takes = await latest_takes(session, project_id)
        if any(t.status in {"recording", "uploaded", "processing"} for t in takes.values()):
            raise HTTPException(409, "Some answers are still being processed.")
    takes_now = await latest_takes(session, project_id)
    plan_now = project.merge_plan or default_plan(len(takes_now))
    included = {a["question_index"] for a in plan_now["answers"] if a.get("include", True)}
    s = await active_session(session, project_id)
    spoken = " ".join(t.transcript or "" for q, t in sorted(takes_now.items()) if q in included)
    who = f"{s.founder_name} {s.founder_title}" if s else ""
    await moderation_flow.enforce(  # what the founder SAID is published too, so it is screened before the final render
        session,
        project_id=project_id,
        workspace_id=project.workspace_id,
        stage="interview",
        subject_id=fingerprint(*(f"{t.id}:{t.transcript}" for _, t in sorted(takes_now.items()))),
        text=f"{who}\n{spoken}",
    )
    if s:
        s.revoked_at, s.token_enc = datetime.now(UTC), None  # the founder link stops working once we merge
    sm.transition(project, "merging")
    await session.commit()
    await advance(session, project_id)
    await session.refresh(project)
    return await _out(session, project)


@router.post("/interview/retake", dependencies=[Depends(limit("retake", 30, 3600))])
async def request_retake(
    project_id: str,
    body: RetakeIn,
    p: Principal = Depends(current_principal),
    session: AsyncSession = Depends(get_session),
) -> dict:
    project = await _owned(session, project_id, p)
    if project.state not in {"awaiting_founder", "processing_founder"}:
        raise HTTPException(409, "Answers can't be re-recorded now.")
    takes = await latest_takes(session, project_id)
    t = takes.get(body.question_index)
    if t is None:
        raise HTTPException(404, "No answer for that question yet.")
    t.status = "needs_retake"
    t.flags = sorted(set(t.flags or []) | {"owner_requested"})
    s = await active_session(session, project_id)
    emailed = False
    if s is None:
        raise HTTPException(409, "Create a new link first: the founder's link was revoked.")
    s.submitted_at = None  # reopen so the founder can resubmit
    if project.state == "processing_founder":
        sm.transition(project, "awaiting_founder")
    token = crypto.decrypt(s.token_enc) if s.token_enc else None
    if token is None:  # link was submitted earlier and its token dropped: issue a fresh one
        token = iv.new_token()
        s.token_hash, s.token_enc = iv.hash_token(token), crypto.encrypt(token)
    await session.commit()
    if s.founder_email:
        script = await approved_script(session, project_id)
        company = (script.lower_thirds[0].get("title") if script.lower_thirds else "") or p.workspace.name
        emailed = await email_founder_retake(s.founder_email, s.founder_name, company, token, body.note)
    return {"ok": True, "emailed": emailed, "url": f"{get_settings().app_base_url}/i/{token}"}


@router.put("/keep-raw-takes")
async def keep_raw(
    project_id: str,
    body: KeepRawIn,
    p: Principal = Depends(current_principal),
    session: AsyncSession = Depends(get_session),
) -> dict:
    project = await _owned(session, project_id, p)
    project.keep_raw_takes = body.keep
    await session.commit()
    return {"keep": project.keep_raw_takes}
