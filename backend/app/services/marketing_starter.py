"""The ready-made welcome sequence: day 1 welcome, day 3 "make your first video", day 7 credits. Built from ordinary segments,
copies and a workflow, so every part can be opened and changed. Anything that already exists by name is reused."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import MarketingCopy, MarketingCopyVersion, MarketingSegment, MarketingWorkflow
from app.services import marketing_copy as mc
from app.services import marketing_segments as segs

SEGMENTS = {
    "joined": (
        "Joined in the last day",
        {"match": "all", "conditions": [{"field": "joined_days_ago", "op": "lte", "value": 1}]},
    ),
    "no_video": (
        "No video started yet",
        {"match": "all", "conditions": [{"field": "videos_started", "op": "eq", "value": 0}]},
    ),
    "low_credits": (
        "Low on credits and never bought",
        {
            "match": "all",
            "conditions": [
                {"field": "has_bought_credits", "op": "is", "value": False},
                {"field": "credits_left", "op": "lte", "value": 3},
            ],
        },
    ),
    "bought": (
        "Has bought credits",
        {"match": "all", "conditions": [{"field": "has_bought_credits", "op": "is", "value": True}]},
    ),
}
COPIES = {
    "welcome": mc.CopyIn(
        name="Welcome",
        category="onboarding",
        subject="Welcome to Cover Founder, {{first_name|there}}",
        preheader="Your first news-style video is a few minutes away.",
        body="Welcome aboard. Cover Founder turns your business news into a news-style video, presented by an AI anchor and ready to share.\n\n"
        "You can start in a few minutes: paste your announcement and we take it from there.",
        button_label="Make my first video",
        button_url="/ai-newsroom/new",
    ),
    "nudge": mc.CopyIn(
        name="Day 3: make your first video",
        category="activation",
        subject="{{first_name|Your}} first video is one step away",
        preheader="It only takes a few minutes to start.",
        body="Hi {{first_name|there}},\n\n{{company}} is set up, but you haven't made a video yet. It only takes a few minutes to start, and we handle the rest.\n\n"
        "Paste your announcement and we'll turn it into a news-style video.",
        button_label="Start my video",
        button_url="/ai-newsroom/new",
    ),
    "credits": mc.CopyIn(
        name="Day 7: credits",
        category="billing",
        subject="Credits for your next video",
        preheader="Top up any time to keep making videos.",
        body="Hi {{first_name|there}},\n\n{{company}} has {{credits_left}} credits left. Add credits whenever you're ready and keep making videos.",
        button_label="Add credits",
        button_url="/billing",
    ),
}


async def _segment(db: AsyncSession, key: str, actor: str) -> MarketingSegment:
    name, rules = SEGMENTS[key]
    found = (
        (
            await db.execute(
                select(MarketingSegment).where(MarketingSegment.name == name, MarketingSegment.archived_at.is_(None))
            )
        )
        .scalars()
        .first()
    )
    if found:
        return found
    seg = MarketingSegment(name=name, rules=segs.validate(rules).model_dump(), created_by=actor)
    db.add(seg)
    await db.flush()
    return seg


async def _copy(db: AsyncSession, key: str, actor: str) -> MarketingCopy:
    c = mc.validate(COPIES[key].model_copy())
    found = (
        (
            await db.execute(
                select(MarketingCopy).where(MarketingCopy.name == c.name, MarketingCopy.archived_at.is_(None))
            )
        )
        .scalars()
        .first()
    )
    if found:
        return found
    row = MarketingCopy(name=c.name, category=c.category, created_by=actor)
    db.add(row)
    await db.flush()
    db.add(
        MarketingCopyVersion(
            copy_id=row.id,
            version=1,
            subject=c.subject,
            preheader=c.preheader,
            body=c.body,
            button_label=c.button_label,
            button_url=c.button_url,
            created_by=actor,
        )
    )
    return row


async def build(db: AsyncSession, actor: str) -> MarketingWorkflow:
    seg = {k: await _segment(db, k, actor) for k in SEGMENTS}
    cp = {k: await _copy(db, k, actor) for k in COPIES}
    wf = MarketingWorkflow(
        name="Welcome sequence",
        status="draft",
        trigger_segment_id=seg["joined"].id,
        goal_segment_id=seg["bought"].id,
        settings={"enabled": True, "start": 9, "end": 18},
        created_by=actor,
        steps=[
            {"type": "email", "copy_id": cp["welcome"].id},
            {"type": "wait", "days": 2, "hours": 0},
            {"type": "email", "copy_id": cp["nudge"].id, "only_if_segment_id": seg["no_video"].id},
            {"type": "wait", "days": 4, "hours": 0},
            {"type": "email", "copy_id": cp["credits"].id, "only_if_segment_id": seg["low_credits"].id},
        ],
    )
    db.add(wf)
    await db.flush()
    return wf
