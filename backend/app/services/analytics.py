"""First-party daily counters and separately attributed publisher snapshots."""

import hashlib
from datetime import UTC, datetime, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert

from app.db import session_maker
from app.models import (
    AudienceDaily,
    AudienceEvent,
    DistributionPlacement,
    DistributionRequest,
    Project,
    PublisherSnapshot,
    ScriptVersion,
    ShareLink,
    Workspace,
)
from app.models.base import new_id

METRICS = ("impressions", "story_visits", "share_visits", "video_views", "video_completions")
KINDS = {
    "impression": "impressions",
    "story_visit": "story_visits",
    "share_visit": "share_visits",
    "video_view": "video_views",
    "video_complete": "video_completions",
}


def today():
    return datetime.now(UTC).date()


def insert_for(db, model):
    return (pg_insert if db.get_bind().dialect.name == "postgresql" else sqlite_insert)(model)


async def record(db, project_id, kind, session_id):
    day = today()
    digest = hashlib.sha256(str(session_id).encode()).hexdigest()
    if kind == "video_complete":
        viewed = (
            await db.execute(
                select(AudienceEvent.id).where(
                    AudienceEvent.project_id == project_id,
                    AudienceEvent.day == day,
                    AudienceEvent.session_hash == digest,
                    AudienceEvent.kind == "video_view",
                )
            )
        ).scalar_one_or_none()
        if not viewed:
            return False
    await db.commit()  # Release read transactions before the atomic writes, including on SQLite.
    event = insert_for(db, AudienceEvent).values(
        id=new_id(), project_id=project_id, day=day, kind=kind, session_hash=digest
    )
    claimed = (
        await db.execute(
            event.on_conflict_do_nothing(index_elements=["project_id", "day", "kind", "session_hash"]).returning(
                AudienceEvent.id
            )
        )
    ).scalar_one_or_none()
    if not claimed:
        await db.commit()
        return False
    values = {name: int(name == KINDS[kind]) for name in METRICS}
    daily = insert_for(db, AudienceDaily).values(id=new_id(), project_id=project_id, day=day, **values)
    await db.execute(
        daily.on_conflict_do_update(
            index_elements=["project_id", "day"], set_={KINDS[kind]: getattr(AudienceDaily, KINDS[kind]) + 1}
        )
    )
    await db.commit()
    return True


async def prune_events():
    async with session_maker()() as db:
        result = await db.execute(delete(AudienceEvent).where(AudienceEvent.day < today() - timedelta(days=2)))
        await db.commit()
        return result.rowcount


def snapshot_output(row, *, admin=False):
    value = {
        "id": row.id,
        "placement_id": row.placement_id,
        "as_of": row.as_of.isoformat(),
        "views": row.views,
        "impressions": row.impressions,
        "source_note": row.source_note,
        "updated_at": row.updated_at.isoformat(),
    }
    if admin:
        value["updated_by"] = row.updated_by
    return value


async def report(db, start, end, *, workspace_id=None, project_id=None, admin=False):
    scope = [Workspace.deleted_at.is_(None)]
    if workspace_id:
        scope.append(Project.workspace_id == workspace_id)
    if project_id:
        scope.append(Project.id == project_id)
    projects = (
        await db.execute(
            select(Project, Workspace.name)
            .join(Workspace, Workspace.id == Project.workspace_id)
            .where(*scope)
            .order_by(Project.created_at.desc())
        )
    ).all()
    ids = [p.id for p, _ in projects]
    scripts = (
        (
            await db.execute(
                select(ScriptVersion).where(ScriptVersion.project_id.in_(ids)).order_by(ScriptVersion.version.desc())
            )
        )
        .scalars()
        .all()
        if ids
        else []
    )
    titles = {}
    for script in scripts:
        if script.project_id not in titles and script.story:
            titles[script.project_id] = script.story.get("headline", "")
    columns = [func.coalesce(func.sum(getattr(AudienceDaily, name)), 0).label(name) for name in METRICS]
    daily = (
        (
            await db.execute(
                select(AudienceDaily.day, *columns)
                .where(AudienceDaily.project_id.in_(ids), AudienceDaily.day >= start, AudienceDaily.day <= end)
                .group_by(AudienceDaily.day)
            )
        )
        .mappings()
        .all()
        if ids
        else []
    )
    by_day = {r["day"]: {m: int(r[m]) for m in METRICS} for r in daily}
    totals = {m: sum(row[m] for row in by_day.values()) for m in METRICS}
    series = [
        {
            "date": (start + timedelta(days=i)).isoformat(),
            **by_day.get(start + timedelta(days=i), {m: 0 for m in METRICS}),
        }
        for i in range((end - start).days + 1)
    ]
    grouped = (
        (
            await db.execute(
                select(AudienceDaily.project_id, *columns)
                .where(AudienceDaily.project_id.in_(ids), AudienceDaily.day >= start, AudienceDaily.day <= end)
                .group_by(AudienceDaily.project_id)
            )
        )
        .mappings()
        .all()
        if ids
        else []
    )
    by_project = {r["project_id"]: {m: int(r[m]) for m in METRICS} for r in grouped}
    first = (
        (await db.execute(select(func.min(AudienceDaily.day)).where(AudienceDaily.project_id.in_(ids)))).scalar_one()
        if ids
        else None
    )
    legacy = (
        (
            await db.execute(select(func.coalesce(func.sum(ShareLink.views), 0)).where(ShareLink.project_id.in_(ids)))
        ).scalar_one()
        if ids
        else 0
    )
    channel_scope = [DistributionRequest.paid_at.is_not(None), Workspace.deleted_at.is_(None)]
    if workspace_id:
        channel_scope.append(DistributionRequest.workspace_id == workspace_id)
    if project_id:
        channel_scope.append(DistributionRequest.data["project_id"].as_string() == project_id)
    placements = (
        await db.execute(
            select(DistributionPlacement, DistributionRequest, Workspace.name)
            .join(DistributionRequest, DistributionPlacement.request_id == DistributionRequest.id)
            .join(Workspace, Workspace.id == DistributionRequest.workspace_id)
            .where(*channel_scope)
            .order_by(DistributionRequest.created_at.desc())
        )
    ).all()
    placement_ids = [p.id for p, _, _ in placements]
    snapshots = (
        (
            await db.execute(
                select(PublisherSnapshot)
                .where(PublisherSnapshot.placement_id.in_(placement_ids), PublisherSnapshot.as_of <= end)
                .order_by(PublisherSnapshot.as_of)
            )
        )
        .scalars()
        .all()
        if placement_ids
        else []
    )
    by_placement = {}
    for snapshot in snapshots:
        by_placement.setdefault(snapshot.placement_id, []).append(snapshot)
    channels = []
    for placement, request, company in placements:
        rows = by_placement.get(placement.id, [])
        current = {}
        for metric in ("views", "impressions"):
            known = [s for s in rows if getattr(s, metric) is not None]
            current[metric] = getattr(known[-1], metric) if known else None
            current[metric + "_as_of"] = known[-1].as_of.isoformat() if known else None
        channels.append(
            {
                "placement_id": placement.id,
                "request_id": request.id,
                "project_id": request.data.get("project_id"),
                "outlet": placement.data["name"],
                "headline": request.data.get("headline", ""),
                "company": company,
                "status": placement.status,
                "published_url": placement.published_url if placement.status == "published" else "",
                **current,
                "history": [snapshot_output(s, admin=admin) for s in rows if s.as_of >= start],
            }
        )
    channel_totals = {
        m: (sum(c[m] for c in channels if c[m] is not None) if any(c[m] is not None for c in channels) else None)
        for m in ("views", "impressions")
    }
    channel_totals.update(
        outlets_with_reports=sum(c["views"] is not None or c["impressions"] is not None for c in channels),
        outlets=len(channels),
    )
    return {
        "start": start.isoformat(),
        "end": end.isoformat(),
        "timezone": "UTC",
        "platform": totals,
        "series": series,
        "first_recorded_activity": first.isoformat() if first else None,
        "legacy_share_opens_lifetime": int(legacy),
        "projects": [
            {
                "id": p.id,
                "title": titles.get(p.id) or f"Video {p.id[:6]}",
                "company": company,
                **by_project.get(p.id, {m: 0 for m in METRICS}),
            }
            for p, company in projects
        ],
        "channels": channels,
        "channel_totals": channel_totals,
        "definitions": {
            "impressions": "A story thumbnail at least 50% visible for one second.",
            "story_visits": "A visible public story page loaded in a browser.",
            "share_visits": "A visible private shared-video page loaded in a browser.",
            "video_views": "At least 10 seconds watched, or the entire clip if shorter.",
            "video_completions": "Playback ended after watching at least 90% of the clip.",
            "deduplication": "Each metric counts once per story, browser-tab session and UTC day. These are recorded sessions, not verified unique people.",
            "publisher": "Publisher figures are manually reported cumulative snapshots. Totals use the latest known value per outlet/metric as of the selected end date, not the sum of snapshots. Missing values are unknown, not zero.",
            "coverage": "Collection begins with this feature. No historical visits or plays are backfilled. Privacy settings, blockers and network failures can reduce measured counts.",
        },
    }
