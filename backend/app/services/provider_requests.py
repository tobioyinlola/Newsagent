"""Paid vendor generations that survive crashes: submit once, record the vendor's id at once, then only ever poll it."""

import asyncio
import logging
from collections.abc import Awaitable, Callable
from datetime import UTC, datetime

from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import VendorPolicy
from app.db import session_maker
from app.integrations.avatar.base import AvatarProvider, AvatarRequest, AvatarResult
from app.integrations.errors import ProviderError, ProviderPending
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
        async with session_maker()() as s:
            busy = (
                await s.execute(
                    select(func.count())
                    .select_from(ProviderRequest)
                    .where(
                        ProviderRequest.provider == avatar.name,
                        ProviderRequest.status == "submitted",
                        ProviderRequest.id != pr.id,
                    )
                )
            ).scalar_one()
        if busy >= policy.max_concurrency:
            raise ProviderError(f"{avatar.name} is at its concurrency limit", "busy", retry_after=30)
        vid = await avatar.submit(req)
        # recorded BEFORE any waiting: from here a crash or retry resumes this id
        await _save(
            pr.id,
            vendor_video_id=vid,
            status="submitted",
            submitted_at=datetime.now(UTC),
            attempts=pr.attempts + 1,
        )
        pr.vendor_video_id = vid
        log.info("vendor job submitted", extra={"provider": avatar.name, "vendor_id": vid, "slot": slot})
    assert pr.vendor_video_id
    waited = 0.0
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
        if waited >= policy.timeout_s:
            raise ProviderPending()
        await asyncio.sleep(POLL_INTERVAL_S)
        waited += max(POLL_INTERVAL_S, 0.001)
