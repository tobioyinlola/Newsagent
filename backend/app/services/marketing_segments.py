"""Segments: rules that pick out users, mainly by when they joined and what they have done in the product.

A rule set is {"match": "all" | "any", "conditions": [{"field", "op", "value"}]}. Every field is declared once in FIELDS, which
says how to read it, which operators it takes, and the SQL for it. The editor is built from the same list, and nothing from the
request ever becomes SQL text: a rule can only name a field and operator that exist here."""

from collections.abc import Callable
from dataclasses import dataclass
from datetime import UTC, date, datetime, timedelta
from typing import Any, Literal

from pydantic import BaseModel, Field
from sqlalchemy import ColumnElement, Select, and_, exists, func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import (
    Checkout,
    CreditTransaction,
    DistributionRequest,
    MarketingPref,
    MarketingSuppression,
    Project,
    ReferralReward,
    User,
    Workspace,
)
from app.services.industries import INDUSTRIES


class Invalid(ValueError):
    """The rules can't be used; the message is shown to the operator."""


class Condition(BaseModel):
    field: str
    op: str
    value: Any = None


class Rules(BaseModel):
    match: Literal["all", "any"] = "all"
    conditions: list[Condition] = Field(default_factory=list, max_length=20)


Build = Callable[[str, Any, datetime], ColumnElement[bool]]


@dataclass(frozen=True)
class Field_:
    key: str
    label: str
    group: str
    kind: Literal["number", "bool", "choice", "dates"]
    ops: tuple[str, ...]
    build: Build
    unit: str = ""
    options: tuple[tuple[str, str], ...] = ()


# ---------- helpers ----------
def _num(value: Any, what: str) -> float:
    try:
        n = float(value)
    except (TypeError, ValueError):
        raise Invalid(f"{what}: enter a number.") from None
    if n < 0 or n != n:
        raise Invalid(f"{what}: enter a number that is zero or more.")
    return n


def _compare(col: Any, op: str, value: Any, what: str) -> ColumnElement[bool]:
    """A number test on a column or count: eq | gte | lte | between ([low, high])."""
    if op == "between":
        if not isinstance(value, list) or len(value) != 2:
            raise Invalid(f"{what}: enter a from and a to.")
        lo, hi = _num(value[0], what), _num(value[1], what)
        if lo > hi:
            raise Invalid(f"{what}: the first number must not be bigger than the second.")
        return and_(col >= lo, col <= hi)
    n = _num(value, what)
    if op == "eq":
        return col == n
    if op == "gte":
        return col >= n
    if op == "lte":
        return col <= n
    raise Invalid(f"{what}: that comparison isn't available.")


def _age_days(col: Any, op: str, value: Any, now: datetime, what: str) -> ColumnElement[bool]:
    """Whole days since a moment: 0 = today. The moment `col`, `d` days ago, falls in [now-(d+1) days, now-d days]."""

    def before(d: float) -> Any:  # the moment is at least d whole days old
        return col <= now - timedelta(days=d)

    def within(d: float) -> Any:  # the moment is less than d+1 whole days old
        return col > now - timedelta(days=d + 1)

    if op == "between":
        if not isinstance(value, list) or len(value) != 2:
            raise Invalid(f"{what}: enter a from and a to.")
        lo, hi = _num(value[0], what), _num(value[1], what)
        if lo > hi:
            raise Invalid(f"{what}: the first number must not be bigger than the second.")
        return and_(before(lo), within(hi))
    n = _num(value, what)
    if op == "eq":
        return and_(before(n), within(n))
    if op == "gte":  # at least n days ago
        return before(n)
    if op == "lte":  # at most n days ago
        return within(n)
    raise Invalid(f"{what}: that comparison isn't available.")


def _count(model: Any, where: list[Any], link: Any) -> Any:
    return select(func.count()).select_from(model).where(link, *where).correlate(User, Workspace).scalar_subquery()


def _joined(op: str, value: Any, now: datetime) -> ColumnElement[bool]:
    return _age_days(User.created_at, op, value, now, "Days since joining")


def _joined_dates(op: str, value: Any, now: datetime) -> ColumnElement[bool]:
    if not isinstance(value, list) or len(value) != 2:
        raise Invalid("Joined between dates: choose a start and an end date.")
    try:
        start, end = (date.fromisoformat(str(v)[:10]) for v in value)
    except ValueError:
        raise Invalid("Joined between dates: use real dates.") from None
    if start > end:
        raise Invalid("Joined between dates: the start must not be after the end.")
    lo = datetime(start.year, start.month, start.day, tzinfo=UTC)
    hi = datetime(end.year, end.month, end.day, tzinfo=UTC) + timedelta(days=1)
    return and_(User.created_at >= lo, User.created_at < hi)


def _last_seen(op: str, value: Any, now: datetime) -> ColumnElement[bool]:
    # someone who has never signed in again counts from the day they joined
    return _age_days(func.coalesce(User.last_login_at, User.created_at), op, value, now, "Days since last sign-in")


def _bool(value: Any, expr: ColumnElement[bool]) -> ColumnElement[bool]:
    if not isinstance(value, bool):
        raise Invalid("Choose yes or no.")
    return expr if value else ~expr


def _videos(op: str, value: Any, now: datetime) -> ColumnElement[bool]:
    return _compare(_count(Project, [], Project.workspace_id == Workspace.id), op, value, "Videos started")


def _videos_done(op: str, value: Any, now: datetime) -> ColumnElement[bool]:
    done = _count(Project, [Project.completed_at.is_not(None)], Project.workspace_id == Workspace.id)
    return _compare(done, op, value, "Videos finished")


def _bought(op: str, value: Any, now: datetime) -> ColumnElement[bool]:
    return _bool(
        value, exists().where(Checkout.workspace_id == Workspace.id, Checkout.status == "paid").correlate(Workspace)
    )


def _balance(op: str, value: Any, now: datetime) -> ColumnElement[bool]:
    return _compare(Workspace.credit_balance, op, value, "Credits left")


def _used_credits(op: str, value: Any, now: datetime) -> ColumnElement[bool]:
    return _bool(
        value,
        exists()
        .where(CreditTransaction.workspace_id == Workspace.id, CreditTransaction.kind == "usage")
        .correlate(Workspace),
    )


def _distribution(op: str, value: Any, now: datetime) -> ColumnElement[bool]:
    paid = _count(
        DistributionRequest,
        [DistributionRequest.paid_at.is_not(None)],
        DistributionRequest.workspace_id == Workspace.id,
    )
    return _compare(paid, op, value, "Distribution requests paid")


def _referred(op: str, value: Any, now: datetime) -> ColumnElement[bool]:
    return _bool(value, exists().where(ReferralReward.referrer_user_id == User.id).correlate(User))


def _choice(col: Any, valid: set[str], what: str) -> Build:
    def build(op: str, value: Any, now: datetime) -> ColumnElement[bool]:
        if not isinstance(value, list) or not value or not all(isinstance(v, str) for v in value):
            raise Invalid(f"{what}: choose at least one.")
        bad = [v for v in value if valid and v not in valid]
        if bad:
            raise Invalid(f"{what}: {bad[0]} isn't an option.")
        return col.in_(value)

    return build


def _country(op: str, value: Any, now: datetime) -> ColumnElement[bool]:
    if not isinstance(value, list) or not value or not all(isinstance(v, str) for v in value):
        raise Invalid("Country: type at least one.")
    return func.lower(Workspace.country).in_([v.strip().lower() for v in value])


NUM = ("gte", "lte", "eq", "between")
FIELDS: tuple[Field_, ...] = (
    Field_(
        "joined_days_ago", "Days since they joined", "When", "number", NUM, lambda o, v, n: _joined(o, v, n), "days"
    ),
    Field_("joined_dates", "Joined between dates", "When", "dates", ("between",), _joined_dates),
    Field_("last_seen_days_ago", "Days since last sign-in", "When", "number", NUM, _last_seen, "days"),
    Field_("videos_started", "Videos started", "Activity", "number", NUM, _videos, "videos"),
    Field_("videos_finished", "Videos finished", "Activity", "number", NUM, _videos_done, "videos"),
    Field_("has_used_credits", "Has spent credits on a video", "Activity", "bool", ("is",), _used_credits),
    Field_("distribution_paid", "Distribution requests paid", "Activity", "number", NUM, _distribution, "requests"),
    Field_("has_referred", "Has referred someone", "Activity", "bool", ("is",), _referred),
    Field_("has_bought_credits", "Has bought credits", "Money", "bool", ("is",), _bought),
    Field_("credits_left", "Credits left", "Money", "number", NUM, _balance, "credits"),
    Field_(
        "industry",
        "Industry",
        "Profile",
        "choice",
        ("in",),
        _choice(Workspace.industry, set(INDUSTRIES), "Industry"),
        options=tuple((k, v[0]) for k, v in INDUSTRIES.items()),
    ),
    Field_("country", "Country", "Profile", "choice", ("in",), _country),
    Field_(
        "plan",
        "Plan",
        "Profile",
        "choice",
        ("in",),
        _choice(Workspace.plan, set(), "Plan"),
    ),
)
BY_KEY = {f.key: f for f in FIELDS}


def catalog() -> list[dict]:
    """What the editor shows: every field, its group, kind, operators and (for choices) its options."""
    return [
        {
            "key": f.key,
            "label": f.label,
            "group": f.group,
            "kind": f.kind,
            "ops": list(f.ops),
            "unit": f.unit,
            "options": [{"value": k, "label": v} for k, v in f.options],
        }
        for f in FIELDS
    ]


def validate(raw: dict | Rules) -> Rules:
    """The rules as a Rules, or Invalid with a plain message. Compiles every condition once, so a bad value fails here."""
    try:
        rules = raw if isinstance(raw, Rules) else Rules.model_validate(raw or {})
    except Exception:  # noqa: BLE001
        raise Invalid("The rules aren't in the right shape.") from None
    if not rules.conditions:
        raise Invalid("Add at least one rule.")
    compile_rules(rules, datetime.now(UTC))
    return rules


def compile_rules(rules: Rules, now: datetime) -> ColumnElement[bool]:
    parts = []
    for c in rules.conditions:
        f = BY_KEY.get(c.field)
        if f is None:
            raise Invalid(f"Unknown rule: {c.field}.")
        if c.op not in f.ops:
            raise Invalid(f"{f.label}: that comparison isn't available.")
        parts.append(f.build(c.op, c.value, now))
    return and_(*parts) if rules.match == "all" else or_(*parts)


# ---------- using a segment ----------
def _base() -> Select:
    return select(User).join(Workspace, Workspace.id == User.workspace_id).where(Workspace.deleted_at.is_(None))


def members_query(rules: Rules, now: datetime | None = None) -> Select:
    """Everyone the rules match right now (reachable or not)."""
    return _base().where(compile_rules(rules, now or datetime.now(UTC)))


def reachable_clause() -> list[ColumnElement[bool]]:
    """Who can be emailed at all: not suspended, not opted out, not on the suppression list."""
    out = exists().where(MarketingPref.user_id == User.id, MarketingPref.opted_out_at.is_not(None)).correlate(User)
    sup = exists().where(MarketingSuppression.email == func.lower(User.email)).correlate(User)
    return [Workspace.suspended.is_(False), ~out, ~sup]


async def matches(db: AsyncSession, rules: Rules, user_id: str) -> bool:
    """Whether one person matches the rules right now."""
    q = members_query(rules).where(User.id == user_id).with_only_columns(User.id).limit(1)
    return (await db.execute(q)).first() is not None


async def preview(db: AsyncSession, rules: Rules, sample: int = 10) -> dict:
    now = datetime.now(UTC)
    q = members_query(rules, now)
    matched = (await db.execute(select(func.count()).select_from(q.subquery()))).scalar_one()
    reach = q.where(*reachable_clause())
    reachable = (await db.execute(select(func.count()).select_from(reach.subquery()))).scalar_one()
    rows = (await db.execute(reach.order_by(User.created_at.desc()).limit(sample))).scalars().all()
    names = {
        w.id: w.name
        for w in (
            await db.execute(select(Workspace).where(Workspace.id.in_({u.workspace_id for u in rows} or {"-"})))
        ).scalars()
    }
    return {
        "matched": matched,
        "reachable": reachable,
        "excluded": matched - reachable,  # matched but opted out, suppressed or suspended: never emailed
        "sample": [
            {
                "user_id": u.id,
                "email": u.email,
                "company": names.get(u.workspace_id, ""),
                "joined": u.created_at.isoformat(),
            }
            for u in rows
        ],
    }


__all__ = ["BY_KEY", "FIELDS", "Condition", "Invalid", "Rules", "catalog", "members_query", "preview", "validate"]
