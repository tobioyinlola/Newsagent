"""Campaigns: send one copy to one segment, now or at a time, spread out over minutes.

When the time comes the audience is fixed (everyone the rules match who can be emailed), written down as recipients, and then
delivered a few at a time. Every send goes through marketing.send(), so opt-outs, the pause switch, the gap between emails to
one person and the daily cap all apply, and a person is never sent the same campaign twice."""

import logging
from datetime import datetime

from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.db import session_maker
from app.models import (
    MarketingCampaign,
    MarketingCopyVersion,
    MarketingRecipient,
    User,
)
from app.models.base import utcnow
from app.services import marketing
from app.services import marketing_copy as copies
from app.services import marketing_segments as segs

log = logging.getLogger("marketing.campaigns")
# These skips are about the moment, not the person: leave the recipient waiting and try again on a later tick.
WAIT = {"paused", "daily_cap", "engine_off"}


async def counts(db: AsyncSession, campaign_id: str) -> dict:
    rows = (
        await db.execute(
            select(MarketingRecipient.status, MarketingRecipient.reason, func.count())
            .where(MarketingRecipient.campaign_id == campaign_id)
            .group_by(MarketingRecipient.status, MarketingRecipient.reason)
        )
    ).all()
    totals = {"pending": 0, "sent": 0, "skipped": 0, "failed": 0}
    by_reason: dict[str, int] = {}
    for status, reason, n in rows:
        totals[status] += n
        if status == "skipped":
            by_reason[reason or "other"] = n
    return {**totals, "skipped_by_reason": by_reason}


async def start(db: AsyncSession, c: MarketingCampaign) -> None:
    """Fix the audience: write a recipient for everyone the rules match who can be emailed right now."""
    rules = segs.Rules.model_validate(c.rules)
    ids = (
        (await db.execute(segs.members_query(rules).where(*segs.reachable_clause()).with_only_columns(User.id)))
        .scalars()
        .all()
    )
    db.add_all(MarketingRecipient(campaign_id=c.id, user_id=uid) for uid in ids)
    c.status, c.started_at, c.audience = "sending", utcnow(), len(ids)


async def _deliver_one(
    db: AsyncSession, c: MarketingCampaign, r: MarketingRecipient, version: MarketingCopyVersion
) -> str:
    user = await db.get(User, r.user_id)
    if user is None:
        r.status, r.reason, r.done_at = "skipped", "account_gone", utcnow()
        return "skipped"
    f = copies.fields_for(version, await copies.values_for(db, user))
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
            version = (
                await db.execute(
                    select(MarketingCopyVersion).where(
                        MarketingCopyVersion.copy_id == c.copy_id, MarketingCopyVersion.version == c.copy_version
                    )
                )
            ).scalar_one()
            batch = (
                (
                    await db.execute(
                        select(MarketingRecipient)
                        .where(MarketingRecipient.campaign_id == c.id, MarketingRecipient.status == "pending")
                        .order_by(MarketingRecipient.id)
                        .limit(budget)
                    )
                )
                .scalars()
                .all()
            )
            for r in batch:
                try:
                    out = await _deliver_one(db, c, r, version)
                except Exception:  # noqa: BLE001  one bad row must not stop the rest
                    log.exception("campaign %s: recipient %s failed", c.id, r.id)
                    r.status, r.reason, r.done_at = "failed", "error", utcnow()
                    out = "failed"
                await db.commit()
                if out == "wait":
                    budget = 0  # paused or at today's limit: nobody else will get through either; try again next tick
                    break
                delivered += 1
                budget -= 1
            left = (
                await db.execute(
                    select(func.count())
                    .select_from(MarketingRecipient)
                    .where(MarketingRecipient.campaign_id == c.id, MarketingRecipient.status == "pending")
                )
            ).scalar_one()
            if left == 0:
                c.status, c.finished_at = "sent", utcnow()
                await db.commit()
    return {"started": started, "delivered": delivered}


async def cancel(db: AsyncSession, c: MarketingCampaign) -> None:
    """Stop a campaign: whoever hasn't been emailed yet won't be. What was already sent stays sent."""
    await db.execute(
        update(MarketingRecipient)
        .where(MarketingRecipient.campaign_id == c.id, MarketingRecipient.status == "pending")
        .values(status="skipped", reason="cancelled", done_at=utcnow())
    )
    c.status, c.finished_at = "cancelled", utcnow()
