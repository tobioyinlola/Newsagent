"""Operational endpoints: readiness, what is real vs stand-in, pipeline metrics and the HeyGen callback."""

import hashlib
import hmac
import json
import logging
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException, Request, Response
from sqlalchemy import func, select, text
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import Principal, current_principal, operator
from app.config import get_settings
from app.db import get_session
from app.integrations import registry
from app.models import Job, Project, ProviderRequest, WebhookEvent
from app.pipeline.advance import advance
from app.schemas.api import PresenterOut
from app.services import presenters, realtime
from app.services import state_machine as sm
from app.services.ratelimit import limit

router = APIRouter(tags=["system"])
log = logging.getLogger("system")


@router.get("/health/ready")
async def ready(response: Response, session: AsyncSession = Depends(get_session)) -> dict:
    """Is this instance fit to serve? The database is required; the others are reported so an operator can see them."""
    checks: dict[str, str] = {}
    try:
        await session.execute(text("select 1"))
        checks["database"] = "ok"
    except Exception:  # noqa: BLE001
        checks["database"] = "down"
    try:
        await registry.get_storage().size("healthcheck/none")
        checks["storage"] = "ok"
    except Exception:  # noqa: BLE001
        checks["storage"] = "down"
    s = get_settings()
    if s.renderer_backend == "http":
        import httpx

        try:
            async with httpx.AsyncClient(timeout=3) as c:
                checks["renderer"] = "ok" if (await c.get(f"{s.renderer_url}/health")).status_code == 200 else "down"
        except Exception:  # noqa: BLE001
            checks["renderer"] = "down"
    depth: dict[str, int] = {}
    if s.queue_backend == "celery":
        from app.pipeline.queue import lane_depths

        try:  # messages waiting in each lane: a number that keeps growing means the workers cannot keep up
            depth = await lane_depths()
            checks["queue"] = "ok"
        except Exception:  # noqa: BLE001
            checks["queue"] = "down"
    ok = checks["database"] == "ok"
    if not ok:
        response.status_code = 503
    return {
        "status": "ready" if ok and "down" not in checks.values() else ("degraded" if ok else "down"),
        "checks": checks,
        "queue_depth": depth,
    }


@router.get("/v1/capabilities")
async def capabilities(_: Principal = Depends(current_principal)) -> dict:
    """What is real in this environment. With USE_MOCKS the presenter, voices and transcripts are stand-ins and the
    app says so, rather than presenting them as genuine results."""
    s = get_settings()
    demo = s.use_mocks
    return {
        "demo_mode": demo,
        "presenter": "demo" if demo else ("heygen" if s.heygen_api_key else "unavailable"),
        "interviewer_voice": "browser" if (demo or not s.tts_api_key) else "synthetic",
        "interview_room": "livekit" if realtime.enabled() else "browser",
        "payments": "manual" if s.billing_provider == "manual" else "checkout",
        "transcription": "demo" if demo else ("available" if s.transcription_api_key else "unavailable"),
        "message": "Demo mode: the presenter, voices and transcripts are stand-ins, not real AI output."
        if demo
        else None,
    }


@router.get("/v1/presenters", response_model=list[PresenterOut])
async def list_presenters(q: str = "", gender: str = "", limit: int = 48, _: Principal = Depends(current_principal)):
    """The AI presenter looks a customer can choose from (search by name, filter by gender)."""
    try:
        return [PresenterOut(**p.__dict__) for p in await presenters.search(q, gender, max(1, min(limit, 100)))]
    except Exception:  # noqa: BLE001
        raise HTTPException(503, "The presenter list isn't available right now. Please try again shortly.") from None


@router.get("/v1/admin/pipeline-metrics")
async def pipeline_metrics(_: Principal = Depends(operator), session: AsyncSession = Depends(get_session)) -> dict:
    since = datetime.now(UTC) - timedelta(hours=24)

    async def grouped(col, *where) -> dict[str, int]:
        rows = (await session.execute(select(col, func.count()).where(*where).group_by(col))).all()
        return {str(k): int(n) for k, n in rows if k is not None}

    stuck_cutoff = datetime.now(UTC) - timedelta(minutes=20)
    active = (await session.execute(select(Project).where(Project.state.in_(sm.ACTIVE)))).scalars().all()
    stuck = [p.id for p in active if ((p.state_changed_at or p.created_at).replace(tzinfo=UTC) < stuck_cutoff)]
    durations = (
        await session.execute(
            select(Job.stage, func.avg(Job.duration_s), func.count())
            .where(Job.status == "succeeded", Job.created_at >= since)
            .group_by(Job.stage)
        )
    ).all()
    return {
        "projects_by_state": await grouped(Project.state),
        "jobs_24h_by_status": await grouped(Job.status, Job.created_at >= since),
        "job_failures_24h_by_category": await grouped(
            Job.failure_category, Job.status == "failed", Job.created_at >= since
        ),
        "avg_job_seconds_24h": {stage: round(float(avg or 0), 1) for stage, avg, _n in durations},
        "vendor_jobs_in_flight": (
            await session.execute(
                select(func.count()).select_from(ProviderRequest).where(ProviderRequest.status == "submitted")
            )
        ).scalar_one(),
        "possibly_stuck_projects": stuck,
    }


def _find(d: object, key: str) -> str | None:
    """The first value stored under `key` anywhere in a (small) JSON document."""
    if isinstance(d, dict):
        if isinstance(d.get(key), (str, int)):
            return str(d[key])
        for v in d.values():
            r = _find(v, key)
            if r:
                return r
    elif isinstance(d, list):
        for v in d:
            r = _find(v, key)
            if r:
                return r
    return None


@router.post("/v1/webhooks/heygen", dependencies=[Depends(limit("webhook", 600, 60))])
async def heygen_webhook(request: Request, session: AsyncSession = Depends(get_session)) -> dict:
    """HeyGen tells us a video changed. It only wakes the pipeline: results are always read back from HeyGen's own API
    by the step that owns the job, so nothing in this payload can put media into a video.

    UNVERIFIED against HeyGen's live contract (the developer docs could not be read here): the HMAC-SHA256 signature
    scheme, the header name (HEYGEN_WEBHOOK_SIGNATURE_HEADER) and the payload keys are assumptions. Until
    HEYGEN_WEBHOOK_SECRET is set the endpoint is disabled; polling remains the source of truth either way."""
    s = get_settings()
    if not s.heygen_webhook_secret:
        raise HTTPException(404, "Not found")
    body = await request.body()  # the signature is over the raw body
    given = (request.headers.get(s.heygen_webhook_signature_header) or "").removeprefix("sha256=")
    expected = hmac.new(s.heygen_webhook_secret.encode(), body, hashlib.sha256).hexdigest()
    if not hmac.compare_digest(given, expected):
        raise HTTPException(401, "Invalid signature")
    try:
        doc = json.loads(body)
    except ValueError:
        raise HTTPException(400, "Malformed event") from None
    event_id = _find(doc, "event_id") or hashlib.sha256(body).hexdigest()
    session.add(WebhookEvent(provider="heygen", event_id=event_id))
    try:
        await session.commit()
    except IntegrityError:
        await session.rollback()
        return {"result": "duplicate"}
    video_id = _find(doc, "video_id")
    pr = (
        (await session.execute(select(ProviderRequest).where(ProviderRequest.vendor_video_id == video_id)))
        .scalars()
        .first()
        if video_id
        else None
    )
    if pr is None:
        return {"result": "ignored"}  # not one of ours (or not recorded yet): nothing to wake
    pr.last_webhook_at = datetime.now(UTC)
    await session.commit()
    log.info("provider callback", extra={"provider": "heygen", "project_id": pr.project_id, "vendor_id": video_id})
    await advance(session, pr.project_id)  # idempotent: re-polls the recorded job right away
    return {"result": "accepted"}
