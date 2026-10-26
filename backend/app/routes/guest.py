"""Founder-facing endpoints. No account: the magic link token is the credential, scoped to ONE project.

Everything here is rate limited per token and per IP, and reveals nothing beyond what the founder needs.
"""

import uuid
from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import get_session
from app.integrations import registry
from app.integrations.storage.base import ObjectTooLarge
from app.models import Asset, InterviewSession, Project, Take, Workspace
from app.pipeline.queue import enqueue
from app.pipeline.steps import approved_script, latest_takes
from app.pipeline.takes import chunk_key
from app.schemas.api import (
    ChunkUrlsIn,
    ChunkUrlsOut,
    CompleteIn,
    GuestQuestion,
    GuestTake,
    GuestTakeIn,
    GuestView,
    LinesOut,
    PhotoConfirmIn,
    PhotoIn,
    RealtimeOut,
    UploadSlot,
    VoiceLine,
    VoicePrepareOut,
)
from app.services import interview as iv
from app.services import privacy, ratelimit, uploads
from app.services import state_machine as sm
from app.services.notifications import notify_owners

router = APIRouter(prefix="/v1/interview/{token}", tags=["founder"])
URL_TTL = 3600
GONE = HTTPException(404, "This link is no longer valid. Ask the person who invited you for a new one.")


async def guest_limit(token: str, request: Request) -> None:
    for key, n in ((f"guest:t:{iv.hash_token(token)[:16]}", 1500), (f"guest:ip:{ratelimit.client_ip(request)}", 3000)):
        if not await ratelimit.hit(key, n, 600):
            raise HTTPException(429, "Too many requests. Please wait a moment and try again.")


async def load(
    token: str, session: AsyncSession, *, states: set[str] | None = None
) -> tuple[InterviewSession, Project]:
    s = (
        await session.execute(select(InterviewSession).where(InterviewSession.token_hash == iv.hash_token(token)))
    ).scalar_one_or_none()
    if s is None or s.revoked_at is not None or iv.is_expired(s.expiry):
        raise GONE
    project = await session.get(Project, s.project_id)
    allowed = states or {"awaiting_founder", "processing_founder"}
    if s.mode == "live" and "awaiting_founder" in allowed:
        allowed = allowed | {"interviewing"}  # the AI interview happens before the anchor exists
    if project is None or project.state not in allowed:
        raise GONE
    return s, project


def _take(t: Take) -> GuestTake:
    flags = list(t.flags or [])
    return GuestTake(
        id=t.id,
        status=t.status,
        kind=t.kind,
        flags=flags,
        messages=iv.flag_messages(flags),
        chunks_received=sorted(int(i) for i in (t.chunks or {})),
        duration_s=t.duration_s,
    )


async def _owned_take(session: AsyncSession, s: InterviewSession, take_id: str) -> Take:
    t = await session.get(Take, take_id)
    if t is None or t.session_id != s.id:
        raise HTTPException(404, "Recording not found")
    return t


async def _company(session: AsyncSession, project: Project) -> str:
    script = await approved_script(session, project.id)
    ws = await session.get(Workspace, project.workspace_id)
    return (script.lower_thirds[0].get("title") if script.lower_thirds else "") or (ws.name if ws else "this startup")


@router.get("", response_model=GuestView, dependencies=[Depends(guest_limit)])
async def view(token: str, session: AsyncSession = Depends(get_session)) -> GuestView:
    s, project = await load(token, session)
    script = await approved_script(session, project.id)
    takes = await latest_takes(session, project.id)
    attempts = dict(
        (
            await session.execute(
                select(Take.question_index, func.count())
                .where(Take.project_id == project.id)
                .group_by(Take.question_index)
            )
        ).all()
    )
    clips = {
        a.format: a
        for a in (
            await session.execute(select(Asset).where(Asset.project_id == project.id, Asset.type == "question_clip"))
        ).scalars()
    }
    storage = registry.get_storage()
    company = await _company(session, project)
    return GuestView(
        mode=s.mode,
        company=company,
        founder_name=s.founder_name,
        expires_at=s.expiry,
        consent_text=iv.consent_text(company),
        consented=s.consent_at is not None,
        can_record=project.state in {"awaiting_founder", "interviewing"} and s.submitted_at is None,
        submitted=s.submitted_at is not None,
        has_photo=bool(s.photo_key),
        max_chunks=iv.LIVE_MAX_CHUNKS if s.mode == "live" else iv.MAX_CHUNKS,
        max_chunk_bytes=iv.MAX_CHUNK_BYTES,
        questions=[
            GuestQuestion(
                index=i,
                text=q,
                clip_url=storage.presign_get(clips[f"q{i}"].storage_key, URL_TTL) if f"q{i}" in clips else None,
                take=_take(takes[i]) if i in takes else None,
                attempts_left=max(0, iv.MAX_ATTEMPTS_PER_QUESTION - attempts.get(i, 0)),
            )
            for i, q in enumerate(script.interview_questions)
        ],
    )


@router.post("/consent", dependencies=[Depends(guest_limit)])
async def consent(token: str, session: AsyncSession = Depends(get_session)) -> dict:
    s, _ = await load(token, session)
    s.consent_at, s.consent_version = datetime.now(UTC), iv.CONSENT_VERSION
    await session.commit()
    return {"ok": True}


@router.post("/takes", response_model=GuestTake, dependencies=[Depends(guest_limit)])
async def start_take(token: str, body: GuestTakeIn, session: AsyncSession = Depends(get_session)) -> GuestTake:
    s, project = await load(token, session, states={"awaiting_founder"})
    if s.consent_at is None:
        raise HTTPException(409, "Please read and accept how your recording will be used first.")
    script = await approved_script(session, project.id)
    if body.question_index >= len(script.interview_questions):
        raise HTTPException(422, "No such question")
    if s.mode == "live" and body.kind != "video":
        raise HTTPException(422, "Your camera needs to be on for this interview.")
    mime = body.mime.split(";")[0].strip().lower()
    table = iv.ALLOWED_VIDEO_MIME if body.kind == "video" else iv.ALLOWED_AUDIO_MIME
    if mime not in table:
        raise HTTPException(415, "This browser's recording format isn't supported. Try audio only.")
    used = (
        await session.execute(
            select(func.count())
            .select_from(Take)
            .where(Take.session_id == s.id, Take.question_index == body.question_index)
        )
    ).scalar_one()
    if used >= iv.MAX_ATTEMPTS_PER_QUESTION:
        raise HTTPException(429, "That's the maximum number of takes for this question. Please keep your best one.")
    t = Take(
        session_id=s.id, project_id=project.id, question_index=body.question_index, kind=body.kind, ext=table[mime]
    )
    session.add(t)
    await session.commit()
    return _take(t)


@router.post("/takes/{take_id}/chunk-urls", response_model=ChunkUrlsOut, dependencies=[Depends(guest_limit)])
async def chunk_urls(
    token: str, take_id: str, body: ChunkUrlsIn, session: AsyncSession = Depends(get_session)
) -> ChunkUrlsOut:
    s, project = await load(token, session, states={"awaiting_founder"})
    t = await _owned_take(session, s, take_id)
    if t.status != "recording":
        raise HTTPException(409, "This recording is already finished.")
    if any(i < 0 or i >= (iv.LIVE_MAX_CHUNKS if s.mode == "live" else iv.MAX_CHUNKS) for i in body.indexes):
        raise HTTPException(422, "Recording is too long")
    storage = registry.get_storage()
    return ChunkUrlsOut(
        urls={str(i): storage.presign_put(chunk_key(project.id, t.id, i), URL_TTL) for i in body.indexes}
    )


@router.post("/takes/{take_id}/chunks/{idx}/confirm", response_model=GuestTake, dependencies=[Depends(guest_limit)])
async def confirm_chunk(token: str, take_id: str, idx: int, session: AsyncSession = Depends(get_session)) -> GuestTake:
    s, project = await load(token, session, states={"awaiting_founder"})
    t = await _owned_take(session, s, take_id)
    if t.status != "recording" or not (0 <= idx < (iv.LIVE_MAX_CHUNKS if s.mode == "live" else iv.MAX_CHUNKS)):
        raise HTTPException(409, "This recording is already finished.")
    storage = registry.get_storage()
    key = chunk_key(project.id, t.id, idx)
    size = await storage.size(key)
    if size is None:
        raise HTTPException(409, "That part hasn't arrived yet.")
    if size > iv.MAX_CHUNK_BYTES or size == 0:
        await storage.delete(key)
        raise HTTPException(422, "That part of the recording was not accepted.")
    chunks = dict(t.chunks or {})
    chunks[str(idx)] = size
    if sum(chunks.values()) > iv.MAX_TAKE_BYTES:
        raise HTTPException(413, "This recording is too large.")
    t.chunks = chunks  # reassign so the JSON column change is detected
    await session.commit()
    return _take(t)


@router.delete("/takes/{take_id}", dependencies=[Depends(guest_limit)])
async def abandon_take(token: str, take_id: str, session: AsyncSession = Depends(get_session)) -> dict:
    """Drop a recording that will never be finished (the camera went off, or the person left), so it can't block
    submitting. A finished take is never touched: re-recording replaces it instead."""
    s, project = await load(token, session, states={"awaiting_founder"})
    t = await _owned_take(session, s, take_id)
    if t.status == "recording":
        storage = registry.get_storage()
        for idx in list(t.chunks or {}):
            await storage.delete(chunk_key(project.id, t.id, int(idx)))
        t.status, t.chunks = "superseded", {}
        await session.commit()
    return {"ok": True}


@router.get("/takes/{take_id}", response_model=GuestTake, dependencies=[Depends(guest_limit)])
async def take_status(token: str, take_id: str, session: AsyncSession = Depends(get_session)) -> GuestTake:
    s, _ = await load(token, session)
    return _take(await _owned_take(session, s, take_id))


@router.post("/takes/{take_id}/complete", response_model=GuestTake, dependencies=[Depends(guest_limit)])
async def complete_take(
    token: str, take_id: str, body: CompleteIn, session: AsyncSession = Depends(get_session)
) -> GuestTake:
    s, project = await load(token, session, states={"awaiting_founder"})
    t = await _owned_take(session, s, take_id)
    if t.status in {"uploaded", "processing", "ready", "needs_retake"}:
        return _take(t)  # idempotent: a retried request after a dropped response is fine
    if t.status != "recording":
        raise HTTPException(409, "This recording can't be completed.")
    if s.mode == "live" and body.chunk_count > iv.LIVE_MAX_CHUNKS:
        raise HTTPException(422, "That answer was longer than the interview allows.")
    have = {int(i) for i in (t.chunks or {})}
    missing = [i for i in range(body.chunk_count) if i not in have]
    if missing:
        raise HTTPException(
            409, {"error": "missing_chunks", "message": "Some parts haven't arrived yet.", "missing": missing[:80]}
        )
    if any(i >= body.chunk_count for i in have):  # stray chunks beyond the declared count are dropped
        t.chunks = {str(i): sz for i, sz in t.chunks.items() if int(i) < body.chunk_count}
    for old in (
        await session.execute(
            select(Take).where(
                Take.session_id == s.id,
                Take.question_index == t.question_index,
                Take.id != t.id,
                Take.status != "superseded",
            )
        )
    ).scalars():
        old.status = "superseded"
    t.status = "uploaded"
    await session.commit()
    enqueue("process_take", {"take_id": t.id})  # processed now so a bad take is caught while they're still here
    return _take(t)


@router.post("/takes/{take_id}/reprocess", response_model=GuestTake, dependencies=[Depends(guest_limit)])
async def reprocess(token: str, take_id: str, session: AsyncSession = Depends(get_session)) -> GuestTake:
    s, _ = await load(token, session, states={"awaiting_founder"})
    t = await _owned_take(session, s, take_id)
    if t.status != "failed":
        raise HTTPException(409, "Nothing to retry.")
    t.status = "uploaded"
    await session.commit()
    enqueue("process_take", {"take_id": t.id})
    return _take(t)


@router.post("/photo", response_model=UploadSlot, dependencies=[Depends(guest_limit)])
async def photo_slot(token: str, body: PhotoIn, session: AsyncSession = Depends(get_session)) -> UploadSlot:
    s, project = await load(token, session, states={"awaiting_founder"})
    ext = {"image/png": "png", "image/jpeg": "jpg"}.get(body.content_type)
    if ext is None:
        raise HTTPException(422, "Please use a PNG or JPEG photo.")
    key = f"projects/{project.id}/takes/photo-{uuid.uuid4().hex[:10]}.{ext}"
    return UploadSlot(key=key, upload_url=registry.get_storage().presign_put(key, 900))


@router.post("/photo/confirm", dependencies=[Depends(guest_limit)])
async def photo_confirm(token: str, body: PhotoConfirmIn, session: AsyncSession = Depends(get_session)) -> dict:
    s, project = await load(token, session, states={"awaiting_founder"})
    if not body.key.startswith(f"projects/{project.id}/takes/photo-"):
        raise HTTPException(422, "Invalid photo")
    storage = registry.get_storage()
    ctype = "image/png" if body.key.endswith(".png") else "image/jpeg"

    async def reject(msg: str) -> HTTPException:
        await storage.delete(body.key)
        return HTTPException(422, msg)

    try:
        data = await storage.get(body.key, uploads.RULES["product_image"].max_bytes)
    except ObjectTooLarge:
        raise await reject("That photo is too large.") from None
    except Exception:
        raise HTTPException(422, "We didn't receive that photo. Please try again.") from None
    try:
        uploads.validate_content(ctype, data)
    except uploads.InvalidUpload as e:
        raise await reject(str(e)) from None
    try:
        result = await registry.get_scanner().scan(data)
    except Exception:
        raise HTTPException(503, "We couldn't check that photo right now. Please try again shortly.") from None
    if not result.clean:
        raise await reject("That file was blocked by our security scan.")
    if body.take_id:  # a still taken while answering: kept with that answer
        t = await _owned_take(session, s, body.take_id)
        if t.snapshot_key:
            await storage.delete(t.snapshot_key)
        t.snapshot_key = body.key
    else:
        s.photo_key = body.key
    await session.commit()
    return {"ok": True}


@router.post("/submit", dependencies=[Depends(guest_limit)])
async def submit(token: str, session: AsyncSession = Depends(get_session)) -> dict:
    s, project = await load(token, session, states={"awaiting_founder"})
    if s.submitted_at is not None:
        return {"ok": True}
    script = await approved_script(session, project.id)
    takes = await latest_takes(session, project.id)
    problems = []
    for i in range(len(script.interview_questions)):
        t = takes.get(i)
        if t is None:
            problems.append(f"Question {i + 1} hasn't been answered.")
        elif t.status in {"recording", "uploaded", "processing"}:
            problems.append(f"Answer {i + 1} is still being processed.")
        elif t.status == "failed":
            problems.append(f"Answer {i + 1} couldn't be processed. Please try uploading it again.")
        elif t.kind == "audio" and s.mode != "live" and not s.photo_key:
            problems.append("Please add a photo of yourself for audio-only answers.")
    if problems:
        raise HTTPException(
            422, {"error": "incomplete", "message": " ".join(dict.fromkeys(problems)), "problems": problems}
        )
    if s.mode == "live":
        # The owner is right here: the interview is complete, and they review it and press "make my video".
        s.submitted_at = datetime.now(UTC)
        await session.commit()
        return {"ok": True}
    s.submitted_at, s.token_enc = datetime.now(UTC), None
    sm.transition(project, "processing_founder")
    await session.commit()
    await notify_owners(project.id, "founder_submitted")
    return {"ok": True}


@router.post("/speedtest", response_model=UploadSlot, dependencies=[Depends(guest_limit)])
async def speedtest_slot(token: str, session: AsyncSession = Depends(get_session)) -> UploadSlot:
    """Presigned slot for the device check's upload-speed test (a few hundred KB, deleted straight after)."""
    s, project = await load(token, session, states={"awaiting_founder"})
    key = f"projects/{project.id}/takes/speedtest-{uuid.uuid4().hex[:10]}"
    return UploadSlot(key=key, upload_url=registry.get_storage().presign_put(key, 300))


@router.post("/speedtest/done", dependencies=[Depends(guest_limit)])
async def speedtest_done(token: str, body: PhotoConfirmIn, session: AsyncSession = Depends(get_session)) -> dict:
    _, project = await load(token, session, states={"awaiting_founder"})
    if body.key.startswith(f"projects/{project.id}/takes/speedtest-"):
        await registry.get_storage().delete(body.key)
    return {"ok": True}


async def _speak(session: AsyncSession, project: Project, text: str) -> str | None:
    """Audio URL for one interviewer line (cached by text), or None so the browser speaks it itself.
    Never blocks the interview: a missing budget, a vendor error or a mock provider all just mean "no audio"."""
    import hashlib

    from app.config import get_settings
    from app.services.spend_guard import LimitReached, SpendGuard

    storage, tts = registry.get_storage(), registry.get_tts()
    st = get_settings()
    h = hashlib.sha256(f"{st.tts_model}|{st.tts_voice}|{text}".encode()).hexdigest()[:24]
    key = f"projects/{project.id}/interview/voice/{h}.mp3"
    if await storage.size(key):
        return storage.presign_get(key, URL_TTL)
    guard = SpendGuard(session)
    try:
        res = await guard.reserve(
            project.workspace_id, "tts", tts.estimate_cost(text), project_id=project.id, stage="interview_voice"
        )
    except LimitReached:
        return None
    try:
        audio = await tts.synthesize(text)
    except Exception:  # noqa: BLE001
        await guard.release(res)
        await session.commit()
        return None
    if not audio:
        await guard.release(res)
        await session.commit()
        return None
    await storage.put(key, audio, "audio/mpeg")
    await guard.settle(res, tts.estimate_cost(text))
    await session.commit()
    return storage.presign_get(key, URL_TTL)


async def _line_items(token: str, session: AsyncSession) -> tuple[Project, list[tuple[str, str]]]:
    s, project = await load(token, session)
    script = await approved_script(session, project.id)
    lines = iv.interviewer_lines(s.founder_name, await _company(session, project), list(script.interview_questions))
    items = [("greeting", lines["greeting"])]
    items += [(f"q{i}", q) for i, q in enumerate(lines["questions"])]
    items += [("thanks", lines["thanks"]), ("closing", lines["closing"])]
    return project, items


@router.get("/lines", response_model=LinesOut, dependencies=[Depends(guest_limit)])
async def interviewer_lines_text(token: str, session: AsyncSession = Depends(get_session)) -> LinesOut:
    """The interviewer's lines as plain text, no audio and no spend. The LiveKit interviewer agent reads these so it can only
    ever say what the interview's script says."""
    _, items = await _line_items(token, session)
    return LinesOut(lines=dict(items))


@router.post("/realtime", response_model=RealtimeOut, dependencies=[Depends(guest_limit)])
async def join_realtime(token: str, session: AsyncSession = Depends(get_session)) -> RealtimeOut:
    """Permission to join this interview's LiveKit room. 404 when LiveKit isn't set up: the browser then runs the interview on
    its own, which always works."""
    from app.config import get_settings
    from app.services import realtime

    if not realtime.enabled():
        raise HTTPException(404, "Live rooms are not set up.")
    s, project = await load(token, session)
    return RealtimeOut(
        url=get_settings().livekit_url,
        room=realtime.room_name(project.id),
        token=realtime.mint_token(
            project_id=project.id,
            identity=f"founder-{s.id}",
            name=s.founder_name or "Founder",
            interview_token=token,
            api_url=get_settings().api_public_url,
        ),
    )


@router.post("/voice", response_model=VoicePrepareOut, dependencies=[Depends(guest_limit)])
async def prepare_voice(token: str, session: AsyncSession = Depends(get_session)) -> VoicePrepareOut:
    """What the AI interviewer says, with audio for each line when a voice provider is configured. The greeting
    uses the founder's name. Called while the device check runs, so the interview itself never waits."""
    project, items = await _line_items(token, session)
    return VoicePrepareOut(
        lines=[VoiceLine(key=k, text=t, audio_url=await _speak(session, project, t)) for k, t in items]
    )


@router.delete("/data", dependencies=[Depends(guest_limit)])
async def erase_my_recordings(token: str, session: AsyncSession = Depends(get_session)) -> dict:
    """The founder's own right to erasure: delete every recording, transcript and photo, and close the link."""
    s, project = await load(token, session)
    await privacy.purge_takes(session, project.id)
    s.revoked_at, s.token_enc, s.submitted_at = datetime.now(UTC), None, None
    if project.state == "processing_founder":
        sm.transition(project, "awaiting_founder")  # nothing left to review; the owner can invite again or skip
    project.merge_plan = None
    await session.commit()
    await notify_owners(project.id, "founder_erased")
    return {"ok": True}
