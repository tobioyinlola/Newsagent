"""Workflows: a sequence of emails and waits for everyone who comes to match a segment.

People are enrolled as they match the segment (re-checked every minute), then walk the steps. An email step can carry an
"only if" segment (skipped for people who don't match, the sequence carries on). A goal segment ends the sequence for anyone
who matches it. Every email goes through marketing.send(), so opt-outs, pause, the gap and the daily cap all apply, and the
idempotency key means a step is never sent twice to one person. Emails go out inside the sending hours of the person's country."""

import logging
from datetime import datetime, timedelta
from typing import Annotated, Literal

from pydantic import BaseModel, Field, model_validator
from sqlalchemy import exists, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import session_maker
from app.models import (
    MarketingCopy,
    MarketingCopyVersion,
    MarketingEnrollment,
    MarketingSegment,
    MarketingSend,
    MarketingWorkflow,
    User,
    Workspace,
)
from app.models.base import utcnow
from app.services import marketing, marketing_campaigns
from app.services import marketing_copy as copies
from app.services import marketing_segments as segs
from app.services.marketing_hours import Hours, next_open, tz_for

log = logging.getLogger("marketing.workflows")
WAIT = {"paused", "daily_cap", "engine_off"}  # about the moment, not the person: stop for now, try again next minute
LEAVE = {"opted_out", "suppressed", "account_inactive"}  # the person can't be emailed: they leave the workflow
ENROLL_PER_TICK = 200
MAX_TRIES = 3


class Invalid(ValueError):
    """The workflow can't be saved or switched on; the message is shown to the operator."""


class WaitStep(BaseModel):
    type: Literal["wait"]
    days: int = Field(0, ge=0, le=90)
    hours: int = Field(0, ge=0, le=23)

    @model_validator(mode="after")
    def _some_time(self) -> "WaitStep":
        if self.days == 0 and self.hours == 0:
            raise ValueError("A wait needs at least an hour.")
        return self


class EmailStep(BaseModel):
    type: Literal["email"]
    copy_id: str
    copy_version: int | None = None  # fixed when the workflow is switched on
    only_if_segment_id: str | None = None
    only_if_rules: dict | None = None  # that segment's rules, fixed when switched on


class BranchStep(BaseModel):
    """If they are in the segment, jump to one step; if not, jump to another. A target is a LATER step number (0 is the first
    step), or empty to finish. Jumps only go forward, so a workflow can never loop."""

    type: Literal["branch"]
    segment_id: str
    rules: dict | None = None  # that segment's rules, fixed when switched on
    yes_to: int | None = Field(None, ge=0)
    no_to: int | None = Field(None, ge=0)


class EndStep(BaseModel):
    """Finish here: the person leaves the workflow as completed."""

    type: Literal["end"]


Step = Annotated[WaitStep | EmailStep | BranchStep | EndStep, Field(discriminator="type")]


class WorkflowIn(BaseModel):
    name: str = Field(min_length=1, max_length=120)
    trigger_segment_id: str
    steps: list[Step] = Field(min_length=1, max_length=20)
    goal_segment_id: str | None = None
    hours: Hours = Field(default_factory=Hours)
    reentry_days: int | None = Field(None, ge=7, le=365)  # empty: nobody goes through twice


# ---------- checking and switching on ----------
async def check(db: AsyncSession, w: WorkflowIn) -> None:
    seg = await db.get(MarketingSegment, w.trigger_segment_id)
    if seg is None or seg.archived_at is not None:
        raise Invalid("Choose who gets in from your segments.")
    if w.goal_segment_id:
        goal = await db.get(MarketingSegment, w.goal_segment_id)
        if goal is None or goal.archived_at is not None:
            raise Invalid("Choose the goal from your segments.")
    if not any(s.type == "email" for s in w.steps):
        raise Invalid("Add at least one email.")
    if w.steps[-1].type in {"wait", "branch"}:
        raise Invalid("The last step should be an email or an end: a wait or a branch at the end does nothing.")
    for i, s in enumerate(w.steps, 1):
        if s.type == "branch":
            only = await db.get(MarketingSegment, s.segment_id)
            if only is None or only.archived_at is not None:
                raise Invalid(f"Step {i}: choose the branch group from your segments.")
            for target in (s.yes_to, s.no_to):
                if target is not None and not (i - 1 < target < len(w.steps)):
                    raise Invalid(f"Step {i}: a branch can only jump to a later step (or finish).")
            continue
        if s.type != "email":
            continue
        copy = await db.get(MarketingCopy, s.copy_id)
        if copy is None or copy.archived_at is not None:
            raise Invalid(f"Step {i}: choose an email from your copy.")
        if s.only_if_segment_id:
            only = await db.get(MarketingSegment, s.only_if_segment_id)
            if only is None or only.archived_at is not None:
                raise Invalid(f"Step {i}: choose the “only if” group from your segments.")


async def _members(db: AsyncSession, rules: dict) -> list[str]:
    q = segs.members_query(segs.Rules.model_validate(rules)).with_only_columns(User.id)
    return list((await db.execute(q)).scalars())


async def activate(db: AsyncSession, wf: MarketingWorkflow, include_existing: bool) -> None:
    """Switch on. Fixes the words (copy versions) and every rule as they are now, then either lets today's matches in or
    marks them as already past so only people who match from now on are mailed."""
    seg = await db.get(MarketingSegment, wf.trigger_segment_id)
    wf.rules = seg.rules if seg else {}
    steps = []
    for s in wf.steps:
        s = dict(s)
        if s["type"] == "email":
            copy = await db.get(MarketingCopy, s["copy_id"])
            s["copy_version"] = copy.current_version if copy else s.get("copy_version")
            only = await db.get(MarketingSegment, s["only_if_segment_id"]) if s.get("only_if_segment_id") else None
            s["only_if_rules"] = only.rules if only else None
        elif s["type"] == "branch":
            seg_b = await db.get(MarketingSegment, s["segment_id"])
            s["rules"] = seg_b.rules if seg_b else None
        steps.append(s)
    wf.steps = steps
    goal = await db.get(MarketingSegment, wf.goal_segment_id) if wf.goal_segment_id else None
    wf.goal_rules = goal.rules if goal else None
    now = utcnow()
    wf.status, wf.activated_at = "active", now
    if not include_existing:
        for uid in await _members(db, wf.rules):
            db.add(
                MarketingEnrollment(
                    workflow_id=wf.id, user_id=uid, status="exited", exit_reason="existing_at_start", finished_at=now
                )
            )


async def stop(db: AsyncSession, wf: MarketingWorkflow) -> None:
    now = utcnow()
    for e in (
        await db.execute(
            select(MarketingEnrollment).where(
                MarketingEnrollment.workflow_id == wf.id, MarketingEnrollment.status == "active"
            )
        )
    ).scalars():
        e.status, e.exit_reason, e.finished_at, e.next_run_at = "exited", "workflow_stopped", now, None
    wf.status = "stopped"


# ---------- running ----------
def _key(wf: MarketingWorkflow, e: MarketingEnrollment) -> str:
    """One send per person per step per run. The first run keeps the original key; a person who comes back gets fresh ones."""
    run = "" if e.runs <= 1 else f"r{e.runs}:"
    return f"wf:{wf.id}:{e.user_id}:{run}{e.step_index}"


def _leave(e: MarketingEnrollment, reason: str, now: datetime) -> str:
    e.status, e.exit_reason, e.finished_at, e.next_run_at = "exited", reason, now, None
    return "moved"


def _advance(e: MarketingEnrollment, to: datetime | None = None) -> None:
    e.step_index, e.attempts, e.next_run_at = e.step_index + 1, 0, to


async def _process(db: AsyncSession, wf: MarketingWorkflow, e: MarketingEnrollment, now: datetime) -> str:
    """Run one enrollment forward until it sends an email, waits, or ends. Returns "sent", "moved" or "wait" (stop the whole tick)."""
    user = await db.get(User, e.user_id)
    if user is None:
        return _leave(e, "account_gone", now)
    if wf.goal_rules and await segs.matches(db, segs.Rules.model_validate(wf.goal_rules), user.id):
        return _leave(e, "goal_reached", now)
    hours = Hours.model_validate(wf.settings or {})
    while True:
        if e.step_index >= len(wf.steps):
            e.status, e.finished_at, e.next_run_at = "completed", now, None
            return "moved"
        step = wf.steps[e.step_index]
        if step["type"] == "end":
            e.status, e.finished_at, e.next_run_at = "completed", now, None
            return "moved"
        if step["type"] == "branch":
            hit = bool(step.get("rules")) and await segs.matches(db, segs.Rules.model_validate(step["rules"]), user.id)
            target = step.get("yes_to") if hit else step.get("no_to")
            if target is None or target <= e.step_index:  # finish (a jump back can't happen: it is refused when saving)
                e.status, e.finished_at, e.next_run_at = "completed", now, None
                return "moved"
            e.step_index, e.attempts = target, 0
            continue
        if step["type"] == "wait":
            _advance(e, now + timedelta(days=step.get("days", 0), hours=step.get("hours", 0)))
            return "moved"
        only = step.get("only_if_rules")
        if only and not await segs.matches(db, segs.Rules.model_validate(only), user.id):
            _advance(e, now)
            continue
        if hours.enabled:
            ws = await db.get(Workspace, user.workspace_id)
            later = next_open(now, tz_for(ws.country if ws else None), hours.start, hours.end)
            if later is not None:
                e.next_run_at = later
                return "moved"
        version = (
            await db.execute(
                select(MarketingCopyVersion).where(
                    MarketingCopyVersion.copy_id == step["copy_id"],
                    MarketingCopyVersion.version == step["copy_version"],
                )
            )
        ).scalar_one()
        f = copies.fields_for(version, await copies.values_for(db, user))
        out = await marketing.send(
            db,
            user,
            f["subject"],
            f["body"],
            button=f["button"],
            preheader=f["preheader"],
            kind="workflow",
            ref=f"{wf.id}:{e.step_index}",
            idempotency_key=_key(wf, e),
        )
        reason = out.split(":", 1)[1] if out.startswith("skipped:") else ""
        if out in {"sent", "dry_run"}:
            _advance(e, now)
            nxt = wf.steps[e.step_index] if e.step_index < len(wf.steps) else None
            if nxt is None:
                e.status, e.finished_at, e.next_run_at = "completed", now, None
            elif nxt["type"] == "wait":  # the wait starts now, not on the next pass
                _advance(e, now + timedelta(days=nxt.get("days", 0), hours=nxt.get("hours", 0)))
            return "sent"
        if reason in WAIT:
            return "wait"
        if reason in LEAVE:
            return _leave(e, reason, now)
        if reason == "already_sent":
            _advance(e, now)
            continue
        # too soon after another marketing email, or the provider failed: try again later, then give up on this email
        e.attempts += 1
        if e.attempts >= MAX_TRIES:
            _advance(e, now)
            if e.step_index >= len(wf.steps):
                e.status, e.finished_at, e.next_run_at = "completed", now, None
        else:
            e.next_run_at = now + (timedelta(hours=12) if reason == "too_soon" else timedelta(minutes=15))
        return "moved"


async def enroll_new(db: AsyncSession, wf: MarketingWorkflow, now: datetime) -> int:
    """Let in people who now match the segment and aren't in the workflow yet (a batch at a time)."""
    already = (
        exists().where(MarketingEnrollment.workflow_id == wf.id, MarketingEnrollment.user_id == User.id).correlate(User)
    )
    q = (
        segs.members_query(segs.Rules.model_validate(wf.rules))
        .where(*segs.reachable_clause(), ~already)
        .with_only_columns(User.id)
        .limit(ENROLL_PER_TICK)
    )
    ids = list((await db.execute(q)).scalars())
    db.add_all(MarketingEnrollment(workflow_id=wf.id, user_id=uid, next_run_at=now) for uid in ids)
    return len(ids)


async def reenter(db: AsyncSession, wf: MarketingWorkflow, now: datetime) -> int:
    """Let people back in who finished the workflow long enough ago, and match the segment again (if re-entry is switched on)."""
    days = (wf.settings or {}).get("reentry_days")
    if not days:
        return 0
    cutoff = now - timedelta(days=days)
    finished = (
        exists()
        .where(
            MarketingEnrollment.workflow_id == wf.id,
            MarketingEnrollment.user_id == User.id,
            MarketingEnrollment.status == "completed",
            MarketingEnrollment.finished_at <= cutoff,
        )
        .correlate(User)
    )
    q = (
        segs.members_query(segs.Rules.model_validate(wf.rules))
        .where(*segs.reachable_clause(), finished)
        .with_only_columns(User.id)
        .limit(ENROLL_PER_TICK)
    )
    ids = list((await db.execute(q)).scalars())
    if not ids:
        return 0
    rows = (
        await db.execute(
            select(MarketingEnrollment).where(
                MarketingEnrollment.workflow_id == wf.id, MarketingEnrollment.user_id.in_(ids)
            )
        )
    ).scalars()
    n = 0
    for e in rows:
        e.status, e.exit_reason, e.step_index, e.attempts, e.runs = "active", "", 0, 0, e.runs + 1
        e.next_run_at, e.finished_at = now, None
        n += 1
    return n


async def tick(budget: int) -> dict:
    """One minute of work: enrol new matches, then move due people along, sending at most `budget` emails."""
    enrolled = sent = 0
    if marketing.engine_mode() == "off":
        return {"enrolled": 0, "sent": 0}
    async with session_maker()() as db:
        if (await marketing.get_config(db)).paused:
            return {"enrolled": 0, "sent": 0}
        now = utcnow()
        live = (await db.execute(select(MarketingWorkflow).where(MarketingWorkflow.status == "active"))).scalars().all()
        for wf in live:
            enrolled += await enroll_new(db, wf, now)
            enrolled += await reenter(db, wf, now)
        await db.commit()
        for wf in live:
            due = (
                (
                    await db.execute(
                        select(MarketingEnrollment)
                        .where(
                            MarketingEnrollment.workflow_id == wf.id,
                            MarketingEnrollment.status == "active",
                            MarketingEnrollment.next_run_at <= now,
                        )
                        .order_by(MarketingEnrollment.next_run_at)
                        .limit(500)
                        .with_for_update(skip_locked=True)
                    )
                )
                .scalars()
                .all()
            )
            for e in due:
                if sent >= budget:
                    break
                try:
                    out = await _process(db, wf, e, now)
                except Exception:  # noqa: BLE001  one bad person must not stop the rest
                    log.exception("workflow %s: enrollment %s failed", wf.id, e.id)
                    await db.rollback()
                    continue
                await db.commit()
                if out == "wait":
                    return {"enrolled": enrolled, "sent": sent}
                if out == "sent":
                    sent += 1
    return {"enrolled": enrolled, "sent": sent}


async def tick_all() -> dict:
    """What the background job runs every minute: campaigns first, workflows with whatever sending budget is left."""
    c = await marketing_campaigns.deliver_due()
    async with session_maker()() as db:
        per_minute = (await marketing.get_config(db)).per_minute
    w = await tick(max(0, per_minute - c["delivered"]))
    return {"campaign_emails": c["delivered"], "workflow_emails": w["sent"], "enrolled": w["enrolled"]}


# ---------- numbers for the screen ----------
async def stats(db: AsyncSession, wf: MarketingWorkflow) -> dict:
    rows = (
        await db.execute(
            select(MarketingEnrollment.status, MarketingEnrollment.exit_reason, func.count())
            .where(MarketingEnrollment.workflow_id == wf.id)
            .group_by(MarketingEnrollment.status, MarketingEnrollment.exit_reason)
        )
    ).all()
    totals = {"active": 0, "completed": 0, "exited": 0}
    exits: dict[str, int] = {}
    for status, reason, n in rows:
        totals[status] += n
        if status == "exited":
            exits[reason or "other"] = n
    per_ref = {
        ref: (n, o, c)
        for ref, n, o, c in (
            await db.execute(
                select(
                    MarketingSend.ref,
                    func.count(),
                    func.count(MarketingSend.opened_at),
                    func.count(MarketingSend.clicked_at),
                )
                .where(
                    MarketingSend.kind == "workflow",
                    MarketingSend.ref.like(f"{wf.id}:%"),
                    MarketingSend.status.in_(("sent", "dry_run")),
                )
                .group_by(MarketingSend.ref)
            )
        ).all()
    }
    emails = [i for i, st in enumerate(wf.steps) if st["type"] == "email"]
    by_step = {i: per_ref.get(f"{wf.id}:{i}", (0, 0, 0))[0] for i in emails}
    opened = {i: per_ref.get(f"{wf.id}:{i}", (0, 0, 0))[1] for i in emails}
    clicked = {i: per_ref.get(f"{wf.id}:{i}", (0, 0, 0))[2] for i in emails}
    return {**totals, "exits": exits, "sent_by_step": by_step, "opened_by_step": opened, "clicked_by_step": clicked}
