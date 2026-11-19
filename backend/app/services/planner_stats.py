"""Measuring the outlet planner: how often a plan is made, chosen, carried on to sign-up, and paid for, and whether people change it."""

from datetime import timedelta
from decimal import Decimal

from sqlalchemy import case, func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import PlannerEvent
from app.models.base import utcnow

KINDS = ("shown", "asked", "used", "continued", "submitted")
SOURCES = ("public", "request", "ready_prompt", "email")


def record(
    db: AsyncSession,
    kind: str,
    source: str,
    *,
    workspace_id: str | None = None,
    plan_key: str = "",
    outlets: int = 0,
    credits: Decimal | int | str = 0,
    unchanged: bool | None = None,
) -> None:
    """Add one event. The caller commits. A visitor who is not signed in passes no workspace, so nothing identifies them."""
    db.add(
        PlannerEvent(
            kind=kind,
            source=source,
            plan_key=plan_key,
            outlets=outlets,
            credits=Decimal(str(credits)),
            unchanged=unchanged,
            workspace_id=workspace_id,
        )
    )


def _rate(n: int, d: int) -> float | None:
    return round(n / d, 4) if d else None


async def summary(db: AsyncSession, days: int = 30) -> dict:
    since = utcnow() - timedelta(days=days)
    rows = (
        await db.execute(
            select(
                PlannerEvent.source,
                PlannerEvent.kind,
                func.count(),
                func.coalesce(func.sum(PlannerEvent.credits), 0),
                func.coalesce(func.sum(case((PlannerEvent.unchanged.is_(True), 1), else_=0)), 0),
            )
            .where(PlannerEvent.created_at >= since)
            .group_by(PlannerEvent.source, PlannerEvent.kind)
        )
    ).all()
    by_source = {s: {k: 0 for k in KINDS} for s in SOURCES}
    credits = {s: Decimal(0) for s in SOURCES}
    unchanged = {s: 0 for s in SOURCES}
    for source, kind, n, c, u in rows:
        if source in by_source and kind in KINDS:
            by_source[source][kind] = n
            if kind == "submitted":
                credits[source], unchanged[source] = Decimal(str(c)), int(u)

    def block(counts: dict, spent: Decimal, same: int) -> dict:
        viewed = counts["shown"] + counts["asked"]
        return {
            **counts,
            "unchanged": same,
            "credits_submitted": str(spent.normalize() if spent else 0),
            "rates": {
                "use_of_viewed": _rate(counts["used"], viewed),
                "submitted_of_used": _rate(counts["submitted"], counts["used"]),
                "unchanged_of_submitted": _rate(same, counts["submitted"]),
                "average_credits": str((spent / counts["submitted"]).quantize(Decimal("0.1"))) if counts["submitted"] else None,
            },
        }

    totals = {k: sum(by_source[s][k] for s in SOURCES) for k in KINDS}
    return {
        "days": days,
        "since": since.isoformat(),
        "total": block(totals, sum(credits.values(), Decimal(0)), sum(unchanged.values())),
        "by_source": {s: block(by_source[s], credits[s], unchanged[s]) for s in SOURCES},
    }
