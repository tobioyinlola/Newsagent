"""Announcements: one message to every customer, as a pop-up after they sign in (for a time the team sets) and, if chosen, as an email.

The email is an ordinary marketing campaign to a segment of everyone, so it follows every marketing rule: nobody who unsubscribed,
bounced or complained is emailed, and the daily and per-person caps apply. The pop-up is shown until the time is up, the team ends it, or
the person closes it for good."""

from datetime import UTC, datetime, timedelta

from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Announcement,
    AnnouncementEvent,
    MarketingCampaign,
    MarketingCopy,
    MarketingCopyVersion,
    MarketingSegment,
    User,
)
from app.models.base import utcnow
from app.services import marketing_copy as copies
from app.services import rbac

EVERYONE = "Everyone"
EVERYONE_RULES = {"match": "all", "conditions": [{"field": "joined_days_ago", "op": "gte", "value": 0}]}  # anyone who has joined
MAX_SEEN = 200  # how many closed announcements are remembered per person


def _utc(d: datetime | None) -> datetime | None:
    return d if d is None or d.tzinfo else d.replace(tzinfo=UTC)


def status(a: Announcement, now: datetime | None = None) -> str:
    now = now or utcnow()
    if a.ended_at is not None or _utc(a.shows_until) <= now:  # type: ignore[operator]
        return "ended"
    return "scheduled" if _utc(a.shows_from) > now else "live"  # type: ignore[operator]


def window(starts: datetime | None, amount: int, unit: str) -> tuple[datetime, datetime]:
    """When the pop-up starts and stops showing: from `starts` (default now) for `amount` hours or days."""
    begin = _utc(starts) or utcnow()
    return begin, begin + (timedelta(hours=amount) if unit == "hours" else timedelta(days=amount))


async def everyone_segment(db: AsyncSession, actor: str) -> MarketingSegment:
    seg = (
        await db.execute(
            select(MarketingSegment).where(MarketingSegment.name == EVERYONE, MarketingSegment.archived_at.is_(None))
        )
    ).scalars().first()
    if seg is None:
        seg = MarketingSegment(
            name=EVERYONE,
            description="Every customer who has signed up. Used for announcements.",
            rules=EVERYONE_RULES,
            created_by=actor,
        )
        db.add(seg)
        await db.flush()
    return seg


async def make_email(db: AsyncSession, a: Announcement, actor: str) -> MarketingCampaign:
    """The email for an announcement: the same words as the pop-up, as a campaign to everyone, ready to be scheduled."""
    c = copies.validate(
        copies.CopyIn(
            name=f"Announcement: {a.title}"[:120],
            category="product",
            subject=a.title,
            body=a.message,
            button_label=a.button_label,
            button_url=a.button_url,
        )
    )
    copy = MarketingCopy(name=c.name, category=c.category, created_by=actor)
    db.add(copy)
    await db.flush()
    db.add(
        MarketingCopyVersion(
            copy_id=copy.id,
            version=1,
            subject=c.subject,
            preheader=c.preheader,
            body=c.body,
            button_label=c.button_label,
            button_url=c.button_url,
            created_by=actor,
        )
    )
    seg = await everyone_segment(db, actor)
    camp = MarketingCampaign(
        name=f"Announcement: {a.title}"[:120],
        segment_id=seg.id,
        copy_id=copy.id,
        copy_version=1,
        rules=seg.rules,
        created_by=actor,
    )
    db.add(camp)
    await db.flush()
    return camp


async def active_for(db: AsyncSession, user: User) -> list[Announcement]:
    """What this person should see now: live, and not closed by them for good. Newest first."""
    now = utcnow()
    seen = set(((user.onboarding or {}).get("announcements_seen")) or [])
    rows = (
        await db.execute(
            select(Announcement)
            .where(Announcement.shows_from <= now, Announcement.shows_until > now, Announcement.ended_at.is_(None))
            .order_by(Announcement.shows_from.desc(), Announcement.id)
            .limit(5)
        )
    ).scalars()
    return [a for a in rows if a.id not in seen]


def mark_seen(user: User, announcement_id: str) -> None:
    o = dict(user.onboarding or {})
    seen = [x for x in (o.get("announcements_seen") or []) if x != announcement_id]
    o["announcements_seen"] = [*seen, announcement_id][-MAX_SEEN:]
    user.onboarding = o


KINDS = ("seen", "clicked", "dismissed")


async def record(db: AsyncSession, user: User, announcement_id: str, kind: str) -> None:
    """Note that this person did this, once. Doing it again changes nothing, so the counts are people, not taps."""
    exists = (
        await db.execute(
            select(AnnouncementEvent.id).where(
                AnnouncementEvent.announcement_id == announcement_id,
                AnnouncementEvent.user_id == user.id,
                AnnouncementEvent.kind == kind,
            )
        )
    ).first()
    if exists:
        return
    try:
        async with db.begin_nested():
            db.add(AnnouncementEvent(announcement_id=announcement_id, user_id=user.id, kind=kind))
    except IntegrityError:  # two taps at once: the first one counts
        return


async def eligible(db: AsyncSession) -> int:
    """How many customers could see an announcement: everyone with an account except the team."""
    team = await rbac.team_emails(db)
    q = select(func.count(User.id))
    if team:
        q = q.where(User.email.not_in(team))
    return (await db.execute(q)).scalar_one()


async def stats(db: AsyncSession, announcement_id: str, eligible_count: int) -> dict:
    rows = dict(
        (
            await db.execute(
                select(AnnouncementEvent.kind, func.count())
                .where(AnnouncementEvent.announcement_id == announcement_id)
                .group_by(AnnouncementEvent.kind)
            )
        ).all()
    )
    return {"seen": rows.get("seen", 0), "clicked": rows.get("clicked", 0), "dismissed": rows.get("dismissed", 0), "eligible": eligible_count}


async def revise_email(db: AsyncSession, a: Announcement, c: MarketingCampaign, actor: str) -> None:
    """Put the announcement's new words into its email, as a new version of the copy, while the email has not started going out."""
    copy = await db.get(MarketingCopy, c.copy_id)
    assert copy is not None
    v = copies.validate(
        copies.CopyIn(
            name=copy.name, category=copy.category, subject=a.title, body=a.message, button_label=a.button_label, button_url=a.button_url
        )
    )
    copy.current_version += 1
    copy.name = f"Announcement: {a.title}"[:120]
    db.add(
        MarketingCopyVersion(
            copy_id=copy.id,
            version=copy.current_version,
            subject=v.subject,
            preheader=v.preheader,
            body=v.body,
            button_label=v.button_label,
            button_url=v.button_url,
            created_by=actor,
        )
    )
    c.copy_version = copy.current_version
    c.name = f"Announcement: {a.title}"[:120]
