"""Campaigns: send one copy to one segment, now or at a time, spread out over minutes.

When the time comes the audience is fixed (everyone the rules match who can be emailed), written down as recipients, and then
delivered a few at a time. Every send goes through marketing.send(), so opt-outs, the pause switch, the gap between emails to
one person and the daily cap all apply, and a person is never sent the same campaign twice."""

import hashlib
import logging
from datetime import datetime, timedelta

from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import session_maker
from app.models import (
    MarketingCampaign,
    MarketingCopyVersion,
    MarketingRecipient,
    MarketingSend,
    User,
    Workspace,
)
from app.models.base import utcnow
from app.services import marketing
from app.services import marketing_copy as copies
from app.services import marketing_segments as segs
from app.services.marketing_hours import Hours, next_open, tz_for

log = logging.getLogger("marketing.campaigns")
# These skips are about the moment, not the person: leave the recipient waiting and try again on a later tick.
WAIT = {"paused", "daily_cap", "engine_off"}
SCAN_BATCH = 200  # people looked at in one go
MAX_SCANS = 10  # batches per campaign per minute, so people waiting for their morning never hide the ones who can be sent to now


async def counts(db: AsyncSession, campaign_id: str) -> dict:
    rows = (
        await db.execute(
            select(MarketingRecipient.status, MarketingRecipient.reason, func.count())
            .where(MarketingRecipient.campaign_id == campaign_id)
            .group_by(MarketingRecipient.status, MarketingRecipient.reason)
        )
    ).all()
    totals = {"pending": 0, "held": 0, "sent": 0, "skipped": 0, "failed": 0}
    by_reason: dict[str, int] = {}
    for status, reason, n in rows:
        totals[status] += n
        if status == "skipped":
            by_reason[reason or "other"] = n
    seen = (
        await db.execute(
            select(func.count(MarketingSend.opened_at), func.count(MarketingSend.clicked_at)).where(
                MarketingSend.kind == "campaign", MarketingSend.ref == campaign_id, MarketingSend.status == "sent"
            )
        )
    ).one()
    deferred = (
        await db.execute(
            select(func.count())
            .select_from(MarketingRecipient)
            .where(
                MarketingRecipient.campaign_id == campaign_id,
                MarketingRecipient.status == "pending",
                MarketingRecipient.send_after > utcnow(),
            )
        )
    ).scalar_one()
    return {
        **totals,
        "deferred": deferred,  # waiting for the sending hours where they live
        "skipped_by_reason": by_reason,
        "opened": seen[0],
        "clicked": seen[1],
        "variants": await variant_results(db, campaign_id),
    }


async def variant_results(db: AsyncSession, campaign_id: str) -> dict:
    """How each subject line did: people emailed, who opened, who clicked. Empty when there is no test."""
    rows = (
        await db.execute(
            select(
                MarketingRecipient.variant,
                func.count(),
                func.count(MarketingSend.opened_at),
                func.count(MarketingSend.clicked_at),
            )
            .join(
                MarketingSend,
                (MarketingSend.ref == MarketingRecipient.campaign_id)
                & (MarketingSend.user_id == MarketingRecipient.user_id),
            )
            .where(
                MarketingRecipient.campaign_id == campaign_id,
                MarketingRecipient.variant.in_(("A", "B")),
                MarketingRecipient.status == "sent",
                MarketingSend.kind == "campaign",
                MarketingSend.status == "sent",
            )
            .group_by(MarketingRecipient.variant)
        )
    ).all()
    return {v: {"sent": n, "opened": o, "clicked": c} for v, n, o, c in rows}


def bucket(campaign_id: str, user_id: str) -> int:
    """A fixed 0 to 99 for this person in this campaign, so the split is the same however many times it is worked out."""
    return int(hashlib.sha256(f"{campaign_id}:{user_id}".encode()).hexdigest()[:8], 16) % 100


def pick_winner(results: dict, metric: str) -> str:
    """The subject line with the higher rate of opens (or clicks) among those emailed; a tie or no data keeps A."""
    key = "clicked" if metric == "clicks" else "opened"

    def rate(v: str) -> float:
        r = results.get(v)
        return (r[key] / r["sent"]) if r and r["sent"] else 0.0

    return "B" if rate("B") > rate("A") else "A"


async def start(db: AsyncSession, c: MarketingCampaign) -> None:
    """Fix the audience: write a recipient for everyone the rules match who can be emailed right now."""
    rules = segs.Rules.model_validate(c.rules)
    ids = (
        (await db.execute(segs.members_query(rules).where(*segs.reachable_clause()).with_only_columns(User.id)))
        .scalars()
        .all()
    )
    for uid in ids:
        status, variant = "pending", ""
        if c.subject_b:
            b = bucket(c.id, uid)
            if c.ab_mode == "split":
                variant = "A" if b < 50 else "B"
            elif b < c.test_percent / 2:
                variant = "A"
            elif b < c.test_percent:
                variant = "B"
            else:
                status = "held"  # waits for the winner
        db.add(MarketingRecipient(campaign_id=c.id, user_id=uid, status=status, variant=variant))
    c.status, c.started_at, c.audience = "sending", utcnow(), len(ids)


async def _deliver_one(
    db: AsyncSession, c: MarketingCampaign, r: MarketingRecipient, version: MarketingCopyVersion, now: datetime
) -> str:
    user = await db.get(User, r.user_id)
    if user is None:
        r.status, r.reason, r.done_at = "skipped", "account_gone", utcnow()
        return "skipped"
    if c.hours and c.hours.get("enabled"):
        h = Hours.model_validate(c.hours)
        ws = await db.get(Workspace, user.workspace_id)
        later = next_open(now, tz_for(ws.country if ws else None), h.start, h.end)
        if later is not None:  # outside their day: leave them waiting, and don't look at them again until it opens
            r.send_after = later
            return "deferred"
    values = await copies.values_for(db, user)
    f = copies.fields_for(version, values)
    if r.variant.upper() == "B" and c.subject_b:  # b: the winner, sent to everyone who was waiting
        f["subject"] = copies.fill(c.subject_b, values)
    out = await marketing.send(
        db,
        user,
        f["subject"],
        f["body"],
        button=f["button"],
        preheader=f["preheader"],
        kind="campaign",
        ref=c.id,
        idempotency_key=f"campaign:{c.id}:{user.id}",
    )
    if out.startswith("skipped:") and out.split(":", 1)[1] in WAIT:
        return "wait"
    if out in {"sent", "dry_run"}:
        r.status = "sent"
    elif out == "failed":
        r.status = "failed"
    else:
        r.status, r.reason = "skipped", out.split(":", 1)[1]
    r.done_at = utcnow()
    return r.status


async def deliver_due(now: datetime | None = None) -> dict:
    """One tick (run every minute): start campaigns whose time has come, then deliver up to `per_minute` emails in all."""
    if marketing.engine_mode() == "off":
        return {"started": 0, "delivered": 0}
    now = now or utcnow()
    started = delivered = 0
    async with session_maker()() as db:
        cfg = await marketing.get_config(db)
        if cfg.paused:
            return {"started": 0, "delivered": 0}
        due = (
            (
                await db.execute(
                    select(MarketingCampaign)
                    .where(MarketingCampaign.status == "scheduled", MarketingCampaign.send_at <= now)
                    .with_for_update(skip_locked=True)
                )
            )
            .scalars()
            .all()
        )
        for c in due:
            await start(db, c)
            started += 1
        await db.commit()
        budget = cfg.per_minute
        live = (
            (
                await db.execute(
                    select(MarketingCampaign)
                    .where(MarketingCampaign.status == "sending")
                    .order_by(MarketingCampaign.started_at)
                )
            )
            .scalars()
            .all()
        )
        for c in live:
            if budget <= 0:
                break
            await _decide_winner(db, c, now)
            version = (
                await db.execute(
                    select(MarketingCopyVersion).where(
                        MarketingCopyVersion.copy_id == c.copy_id, MarketingCopyVersion.version == c.copy_version
                    )
                )
            ).scalar_one()
            scans = 0
            while budget > 0 and scans < MAX_SCANS:
                scans += 1
                batch = (
                    (
                        await db.execute(
                            select(MarketingRecipient)
                            .where(
                                MarketingRecipient.campaign_id == c.id,
                                MarketingRecipient.status == "pending",
                                or_(MarketingRecipient.send_after.is_(None), MarketingRecipient.send_after <= now),
                            )
                            .order_by(MarketingRecipient.id)
                            .limit(SCAN_BATCH)
                        )
                    )
                    .scalars()
                    .all()
                )
                if not batch:
                    break
                for r in batch:
                    try:
                        out = await _deliver_one(db, c, r, version, now)
                    except Exception:  # noqa: BLE001  one bad row must not stop the rest
                        log.exception("campaign %s: recipient %s failed", c.id, r.id)
                        r.status, r.reason, r.done_at = "failed", "error", utcnow()
                        out = "failed"
                    await db.commit()
                    if out == "wait":
                        budget = (
                            0  # paused or at today's limit: nobody else will get through either; try again next tick
                        )
                        break
                    if out == "deferred":
                        continue  # waiting for their morning: costs nothing, and the next person is looked at
                    delivered += 1
                    budget -= 1
                    if budget <= 0:
                        break
            left = (
                await db.execute(
                    select(func.count())
                    .select_from(MarketingRecipient)
                    .where(MarketingRecipient.campaign_id == c.id, MarketingRecipient.status.in_(("pending", "held")))
                )
            ).scalar_one()
            if left == 0:
                c.status, c.finished_at = "sent", utcnow()
                await db.commit()
    return {"started": started, "delivered": delivered}


async def _decide_winner(db: AsyncSession, c: MarketingCampaign, now: datetime) -> None:
    """Winner mode: once the test group has all been emailed, wait, then send everyone else the better subject line."""
    if not (c.subject_b and c.ab_mode == "winner") or c.winner:
        return

    async def n(status: str) -> int:
        q = select(func.count()).select_from(MarketingRecipient)
        return (
            await db.execute(q.where(MarketingRecipient.campaign_id == c.id, MarketingRecipient.status == status))
        ).scalar_one()

    held, testing = await n("held"), await n("pending")
    if not held or testing:
        return
    if c.decide_at is None:
        c.decide_at = now + timedelta(hours=c.wait_hours)
        await db.commit()
        return
    decide = c.decide_at if c.decide_at.tzinfo else c.decide_at.replace(tzinfo=now.tzinfo)
    if now < decide:
        return
    c.winner = pick_winner(await variant_results(db, c.id), c.metric)
    await db.execute(
        update(MarketingRecipient)
        .where(MarketingRecipient.campaign_id == c.id, MarketingRecipient.status == "held")
        .values(status="pending", variant=c.winner.lower())  # lower case: not part of the test results
    )
    await db.commit()


async def cancel(db: AsyncSession, c: MarketingCampaign) -> None:
    """Stop a campaign: whoever hasn't been emailed yet won't be. What was already sent stays sent."""
    await db.execute(
        update(MarketingRecipient)
        .where(MarketingRecipient.campaign_id == c.id, MarketingRecipient.status.in_(("pending", "held")))
        .values(status="skipped", reason="cancelled", done_at=utcnow())
    )
    c.status, c.finished_at = "cancelled", utcnow()
