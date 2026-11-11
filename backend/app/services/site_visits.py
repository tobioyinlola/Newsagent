"""Cookie-free visitor counting for the public website and customer app.

Nothing is stored on the visitor's device. A visitor is a one-way code made from the day, a secret, their IP address and browser; the
IP address itself is never stored, and the code changes every day, so nobody can be followed from one day to the next. Only daily
totals are kept (visitors, page views, where visitors came from); the short-lived codes are deleted after two days.

What is never counted: the operator back office, private interview and share links, robots, and anyone whose browser sends
"Do Not Track" or "Global Privacy Control". Page names come from a fixed list, so nobody can fill the tables with made-up pages."""

import hashlib
import re
from datetime import UTC, date, datetime, timedelta

from sqlalchemy import delete, func, select
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import session_maker
from app.models import SiteDaily, SitePageDaily, SiteSourceDaily, SiteVisitMark
from app.models.base import new_id

MAX_SOURCES_PER_DAY = 300  # beyond this, new sources are lumped together as "other"
BOT = re.compile(
    r"bot\b|crawler|spider|slurp|facebookexternalhit|headless|monitor|preview|curl/|wget/|python-requests|httpclient",
    re.I,
)

NEVER = (re.compile(r"^/admin(/|$)"), re.compile(r"^/i/"), re.compile(r"^/s/"))
EXACT = {
    "/",
    "/ai-newsroom",
    "/ai-newsroom/new",
    "/ai-newsroom/new-classic",
    "/ai-newsroom/videos",
    "/press-distribution",
    "/distribution",
    "/distribution/request",
    "/latest-stories",
    "/cf-news",
    "/terms",
    "/privacy",
    "/login",
    "/signup",
    "/otp",
    "/forgot",
    "/join",
    "/security",
    "/dashboard",
    "/brand",
    "/analytics",
    "/billing",
    "/referrals",
    "/account",
    "/settings",
    "/newsroom",
    "/projects",
    "/settings/profile",
    "/settings/password",
    "/settings/billing",
    "/settings/referral",
}
PATTERNS = (
    (re.compile(r"^/latest-stories/[a-z0-9-]+$"), "/latest-stories/:story"),
    (re.compile(r"^/(ai-newsroom|projects)/:id$"), None),  # keeps its own name
    (re.compile(r"^/billing/(pay|card|stripe|transfer|bank)/:id$"), None),
)
_HEX = re.compile(r"^[0-9a-f]{20,}$", re.I)


def _id_like(seg: str) -> bool:
    return bool(_HEX.match(seg)) or (
        len(seg) >= 22 and bool(re.fullmatch(r"[A-Za-z0-9_-]+", seg)) and seg != seg.lower() and seg != seg.upper()
    )


def normalize_path(raw: str) -> str | None:
    """The page's name: None if it must never be counted, "/other" if it isn't one we know, otherwise one of a fixed list."""
    path = raw.split("?", 1)[0].split("#", 1)[0].strip()
    if not path.startswith("/") or len(path) > 200:
        return "/other"
    path = re.sub(r"/{2,}", "/", path)
    if any(r.match(path) for r in NEVER):
        return None
    path = "/".join(":id" if _id_like(s) else s for s in path.split("/"))
    if len(path) > 1:
        path = path.rstrip("/")
    if path in EXACT:
        return path
    for rx, name in PATTERNS:
        if rx.match(path):
            return name or path
    return "/other"


SEARCH = ("google", "bing", "duckduckgo", "yahoo", "baidu", "yandex", "ecosia", "brave", "startpage")
SOCIAL = {
    "facebook": ("facebook.com", "fb.com", "fb.me"),
    "x": ("twitter.com", "t.co", "x.com"),
    "linkedin": ("linkedin.com", "lnkd.in"),
    "instagram": ("instagram.com",),
    "whatsapp": ("whatsapp.com", "wa.me"),
    "youtube": ("youtube.com", "youtu.be"),
    "tiktok": ("tiktok.com",),
    "reddit": ("reddit.com",),
    "telegram": ("t.me", "telegram.org"),
}


def _slug(text: str) -> str:
    return re.sub(r"[^a-z0-9]+", "-", text.lower()).strip("-")[:60]


def classify(referrer_host: str, utm_source: str, utm_medium: str, utm_campaign: str) -> tuple[str, str]:
    """Where a visitor came from: (source, detail). Our own emails carry their campaign's name."""
    medium = utm_medium.strip().lower()
    if medium == "email":
        return "email", _slug(utm_campaign) or _slug(utm_source) or "email"
    if medium in {"cpc", "ppc", "paid", "paidsocial", "display"}:
        return "other", "paid"
    host = referrer_host.strip().lower()
    if not re.fullmatch(r"[a-z0-9.-]{1,253}", host):
        return "direct", ""
    host = host.removeprefix("www.")
    for engine in SEARCH:
        if re.search(rf"(^|\.){engine}\.", host):
            return "search", engine
    for name, hosts in SOCIAL.items():
        if any(host == h or host.endswith("." + h) for h in hosts):
            return "social", name
    return "referral", host[:100]


def visitor_hash(day: date, ip: str, user_agent: str) -> str:
    secret = get_settings().secret_key or "local-development"
    return hashlib.sha256(f"{secret}|{day.isoformat()}|{ip}|{user_agent[:300]}".encode()).hexdigest()


def today() -> date:
    return datetime.now(UTC).date()


def _insert(db: AsyncSession, model):
    return (pg_insert if db.get_bind().dialect.name == "postgresql" else sqlite_insert)(model)


async def record(db: AsyncSession, *, day: date, vhash: str, path: str, source: str, detail: str) -> bool:
    """Count one page view, and the visitor if it's their first today. Returns whether it was a new visitor."""
    views = _insert(db, SitePageDaily).values(id=new_id(), day=day, path=path, views=1)
    await db.execute(
        views.on_conflict_do_update(index_elements=["day", "path"], set_={"views": SitePageDaily.views + 1})
    )
    total = _insert(db, SiteDaily).values(day=day, visitors=0, pageviews=1)
    await db.execute(total.on_conflict_do_update(index_elements=["day"], set_={"pageviews": SiteDaily.pageviews + 1}))
    await db.commit()
    claimed = (
        await db.execute(
            _insert(db, SiteVisitMark)
            .values(id=new_id(), day=day, visitor_hash=vhash)
            .on_conflict_do_nothing(index_elements=["day", "visitor_hash"])
            .returning(SiteVisitMark.id)
        )
    ).scalar_one_or_none()
    if not claimed:
        await db.commit()
        return False
    visitors = _insert(db, SiteDaily).values(day=day, visitors=1, pageviews=0)
    await db.execute(visitors.on_conflict_do_update(index_elements=["day"], set_={"visitors": SiteDaily.visitors + 1}))
    known = (
        await db.execute(
            select(SiteSourceDaily.id).where(
                SiteSourceDaily.day == day, SiteSourceDaily.source == source, SiteSourceDaily.detail == detail
            )
        )
    ).first()
    if (
        not known
        and (
            await db.execute(select(func.count()).select_from(SiteSourceDaily).where(SiteSourceDaily.day == day))
        ).scalar_one()
        >= MAX_SOURCES_PER_DAY
    ):
        source, detail = "other", ""
    row = _insert(db, SiteSourceDaily).values(id=new_id(), day=day, source=source, detail=detail, visitors=1)
    await db.execute(
        row.on_conflict_do_update(
            index_elements=["day", "source", "detail"], set_={"visitors": SiteSourceDaily.visitors + 1}
        )
    )
    await db.commit()
    return True


async def report(db: AsyncSession, start: date, end: date) -> dict:
    daily = {
        d.day: d
        for d in (await db.execute(select(SiteDaily).where(SiteDaily.day >= start, SiteDaily.day <= end))).scalars()
    }
    series, day = [], start
    while day <= end:
        row = daily.get(day)
        series.append(
            {
                "date": day.isoformat(),
                "visitors": int(row.visitors) if row else 0,
                "pageviews": int(row.pageviews) if row else 0,
            }
        )
        day += timedelta(days=1)
    pages = (
        await db.execute(
            select(SitePageDaily.path, func.sum(SitePageDaily.views))
            .where(SitePageDaily.day >= start, SitePageDaily.day <= end)
            .group_by(SitePageDaily.path)
            .order_by(func.sum(SitePageDaily.views).desc())
            .limit(25)
        )
    ).all()
    sources = (
        await db.execute(
            select(SiteSourceDaily.source, SiteSourceDaily.detail, func.sum(SiteSourceDaily.visitors))
            .where(SiteSourceDaily.day >= start, SiteSourceDaily.day <= end)
            .group_by(SiteSourceDaily.source, SiteSourceDaily.detail)
            .order_by(func.sum(SiteSourceDaily.visitors).desc())
            .limit(50)
        )
    ).all()
    return {
        "start": start.isoformat(),
        "end": end.isoformat(),
        "totals": {"visitors": sum(s["visitors"] for s in series), "pageviews": sum(s["pageviews"] for s in series)},
        "series": series,
        "pages": [{"path": p, "views": int(v)} for p, v in pages],
        "sources": [{"source": s, "detail": d, "visitors": int(v)} for s, d, v in sources],
        "definitions": {
            "visitors": "Each visitor is counted once a day. Someone who comes on two different days counts as two, because nothing is stored on a visitor's device to recognise them between days.",
            "pageviews": "Every time a page or screen was opened.",
            "excluded": "Robots, visitors whose browser sends Do Not Track or Global Privacy Control, the back office, and private interview and share links.",
        },
    }


async def prune_marks() -> int:
    async with session_maker()() as db:
        result = await db.execute(delete(SiteVisitMark).where(SiteVisitMark.day < today() - timedelta(days=2)))
        await db.commit()
        return int(getattr(result, "rowcount", 0) or 0)
