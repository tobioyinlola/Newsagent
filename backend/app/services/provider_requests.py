"""Paid vendor generations that survive crashes: submit once, record the vendor's id at once, then only ever poll it."""

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select, text
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import VendorPolicy, get_settings
from app.db import session_maker
from app.integrations.avatar.base import AvatarProvider, AvatarRequest, AvatarResult
from app.integrations.errors import Deferred, ProviderError, ProviderPending
from app.models import Project, ProviderRequest
from app.services.spend_guard import Reservation, SpendGuard

log = logging.getLogger("provider_requests")
POLL_INTERVAL_S = 5.0  # tests set to 0


class Cancelled(Exception):
    """The owner cancelled the project while a vendor job was in flight. The vendor job is NOT cancelled (no vendor API
    for that is relied on): its id stays recorded, so resuming the project reuses the video if it finishes."""


async def begin(
    session: AsyncSession,
    guard: SpendGuard,
    avatar: AvatarProvider,
    req: AvatarRequest,
    *,
    project: Project,
    slot: str,
    request_hash: str,
    stage: str,
) -> tuple[str, Reservation]:
    """Hold the customer's credits and write the request row in ONE commit, so a crash can neither leak a hold nor
    lose track of a job. If an earlier attempt already holds credits for this exact request, that hold is reused."""
    pr = (
        await session.execute(
            select(ProviderRequest).where(
                ProviderRequest.project_id == project.id,
                ProviderRequest.provider == avatar.name,
                ProviderRequest.slot == slot,
                ProviderRequest.request_hash == request_hash,
            )
        )
    ).scalar_one_or_none()
    if pr is None:
        pr = ProviderRequest(project_id=project.id, provider=avatar.name, slot=slot, request_hash=request_hash)
        session.add(pr)
    if pr.hold:
        res = Reservation.from_json(pr.hold)
    else:
        res = await guard.reserve(
            project.workspace_id, avatar.name, avatar.estimate_cost(req), project_id=project.id, stage=stage
        )
        pr.hold = res.to_json()
    await session.commit()
    return pr.id, res


async def in_flight(pr_id: str) -> bool:
    """True while the vendor holds a job for this request that has neither finished nor been reported failed."""
    async with session_maker()() as s:
        pr = await s.get(ProviderRequest, pr_id)
        return pr is not None and pr.status == "submitted" and bool(pr.vendor_video_id)


async def clear_hold(session: AsyncSession, pr_id: str) -> None:
    pr = await session.get(ProviderRequest, pr_id)
    if pr is not None:
        pr.hold = None


async def _row(project_id: str, provider: str, slot: str, h: str) -> ProviderRequest:
    async with session_maker()() as s:
        pr = (
            await s.execute(
                select(ProviderRequest).where(
                    ProviderRequest.project_id == project_id,
                    ProviderRequest.provider == provider,
                    ProviderRequest.slot == slot,
                    ProviderRequest.request_hash == h,
                )
            )
        ).scalar_one_or_none()
        if pr is None:
            pr = ProviderRequest(project_id=project_id, provider=provider, slot=slot, request_hash=h)
            s.add(pr)
            await s.commit()
        s.expunge(pr)
        return pr


async def _save(pr_id: str, **fields) -> None:
    async with session_maker()() as s:
        pr = await s.get(ProviderRequest, pr_id)
        assert pr is not None
        for k, v in fields.items():
            setattr(pr, k, v)
        await s.commit()


SLOT_CLAIM_TTL = timedelta(
    minutes=3
)  # a slot claimed but never followed by a vendor id is a crashed worker's: free again


def _live_requests(provider: str, policy: VendorPolicy, now: datetime):
    """Requests that really occupy a vendor slot. A row left 'submitted' by a project that was cancelled or abandoned must not
    hold a slot for ever, or the slots all fill up with dead rows and nothing ever runs again."""
    claimed = func.coalesce(ProviderRequest.submitted_at, ProviderRequest.created_at)
    return (
        ProviderRequest.provider == provider,
        ProviderRequest.status == "submitted",
        claimed >= now - timedelta(seconds=policy.timeout_s * 2),
        (ProviderRequest.vendor_video_id.is_not(None)) | (claimed >= now - SLOT_CLAIM_TTL),
    )


_gate: tuple[asyncio.AbstractEventLoop, asyncio.Lock] | None = None


def _in_process_gate() -> asyncio.Lock:
    """One lock per event loop (Celery gives each task its own), so tasks in the same process cannot interleave here."""
    global _gate
    loop = asyncio.get_running_loop()
    if _gate is None or _gate[0] is not loop:
        _gate = (loop, asyncio.Lock())
    return _gate[1]


async def _take_slot(pr_id: str, provider: str, policy: VendorPolicy) -> None:
    """Claim one of the vendor's concurrent slots, or raise 'busy' (the caller waits its turn without using up an attempt).

    Counting and then submitting lets several workers all see a free slot and all submit, so counting and claiming happen
    under a lock: a Postgres advisory lock between worker processes, and an in-process lock beside it (SQLite has no advisory
    locks, and local development runs in one process)."""
    now = datetime.now(UTC)
    async with _in_process_gate(), session_maker()() as s:
        if s.get_bind().dialect.name == "postgresql":
            await s.execute(text("select pg_advisory_xact_lock(hashtext(:k))"), {"k": f"vendor-slots:{provider}"})
        taken = (
            await s.execute(
                select(func.count())
                .select_from(ProviderRequest)
                .where(*_live_requests(provider, policy, now), ProviderRequest.id != pr_id)
            )
        ).scalar_one()
        if taken >= policy.max_concurrency:
            raise ProviderError(f"{provider} is at its concurrency limit", "busy", retry_after=30)
        pr = await s.get(ProviderRequest, pr_id)
        assert pr is not None
        pr.status, pr.submitted_at = "submitted", now
        await s.commit()  # also releases the advisory lock


def _since_submitted(pr: ProviderRequest) -> float:
    """Seconds since the vendor job was submitted (0 if unknown), so waiting is counted across resumes, not per worker visit."""
    t = pr.submitted_at
    if t is None:
        return 0.0
    return (datetime.now(UTC) - (t if t.tzinfo else t.replace(tzinfo=UTC))).total_seconds()


async def generate(
    avatar: AvatarProvider,
    req: AvatarRequest,
    *,
    project_id: str,
    slot: str,
    request_hash: str,
    policy: VendorPolicy,
    is_cancelled: Callable[[], Awaitable[bool]],
) -> AvatarResult:
    """Return the finished clip for this request, submitting to the vendor at most once per (slot, inputs)."""
    pr = await _row(project_id, avatar.name, slot, request_hash)
    if pr.status == "failed":  # the vendor reported a failure for the earlier submission: a fresh one is allowed
        await _save(pr.id, status="new", vendor_video_id=None, error=None)
        pr.status, pr.vendor_video_id = "new", None
    if pr.status in {"new"} or not pr.vendor_video_id:
        await _take_slot(pr.id, avatar.name, policy)
        try:
            vid = await avatar.submit(req)
        except BaseException:
            await _save(pr.id, status="new")  # nothing was submitted: give the slot back at once
            raise
        # recorded BEFORE any waiting: from here a crash or retry resumes this id
        await _save(
            pr.id,
            vendor_video_id=vid,
            status="submitted",
            submitted_at=datetime.now(UTC),
            attempts=pr.attempts + 1,
        )
        pr.vendor_video_id = vid
        pr.submitted_at = datetime.now(UTC)
        log.info("vendor job submitted", extra={"provider": avatar.name, "vendor_id": vid, "slot": slot})
    assert pr.vendor_video_id
    waited = 0.0
    hold = get_settings().vendor_hold_s if get_settings().queue_backend == "celery" else 0.0
    started = time.monotonic()
    while True:
        p = await avatar.poll(pr.vendor_video_id, req)  # also refreshes an expired download link after a crash
        if p.status == "completed" and p.result:
            await _save(
                pr.id,
                status="completed",
                completed_at=datetime.now(UTC),
                result={"video_url": p.result.video_url, "duration_s": p.result.duration_s, "cost": p.result.cost},
            )
            return p.result
        if p.status == "failed":
            await _save(pr.id, status="failed", error=p.error)
            raise ProviderError(f"{avatar.name} could not make this clip: {p.error}", "temporary")
        if await is_cancelled():
            raise Cancelled()
        if waited >= policy.timeout_s or _since_submitted(pr) >= policy.timeout_s:
            raise ProviderPending()
        if hold and time.monotonic() - started >= hold:
            raise Deferred(
                resume_after=20.0
            )  # frees this worker; the vendor job (its id is saved) is polled again soon
        await asyncio.sleep(POLL_INTERVAL_S)
        waited += max(POLL_INTERVAL_S, 0.001)
