"""Cookie-free visitor counting: who is counted, who never is, and what the report says."""

import pytest
from sqlalchemy import select

from app.models import SiteDaily, SiteSourceDaily, SiteVisitMark
from app.services import site_visits as svc
from tests.conftest import OPS, OWNER

UA = "Mozilla/5.0 (X11; Linux x86_64) Chrome/120.0 Safari/537.36"


@pytest.fixture(autouse=True)
def behind_a_proxy(monkeypatch):
    """In production the visitor's address arrives in X-Forwarded-For; the tests do the same to act as different visitors."""
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "trust_proxy_headers", True)


def h(ip="203.0.113.7", ua=UA, **more):
    return {"user-agent": ua, "x-forwarded-for": ip, **more}


async def visit(client, path="/", ip="203.0.113.7", ua=UA, headers=None, **body):
    return await client.post("/v1/public/visit", json={"path": path, **body}, headers={**h(ip, ua), **(headers or {})})


async def totals(maker):
    async with maker() as s:
        row = (await s.execute(select(SiteDaily))).scalar_one_or_none()
        return (row.visitors, row.pageviews) if row else (0, 0)


async def test_a_visitor_is_counted_once_a_day_and_every_page_view_is_counted(client, maker):
    for path in ("/", "/signup", "/"):
        assert (await visit(client, path)).status_code == 204
    assert await totals(maker) == (1, 3)
    await visit(client, "/", ip="198.51.100.9")  # someone else
    await visit(
        client, "/", ip="203.0.113.7", ua="Mozilla/5.0 Firefox/121.0"
    )  # the same address on another browser is another visitor
    assert await totals(maker) == (3, 5)


async def test_nothing_that_identifies_a_visitor_is_stored(client, maker):
    await visit(client, "/", ip="203.0.113.7")
    async with maker() as s:
        mark = (await s.execute(select(SiteVisitMark))).scalar_one()
    assert "203.0.113.7" not in mark.visitor_hash and len(mark.visitor_hash) == 64
    # the code is different on another day, so a visitor can't be followed
    from datetime import date

    assert svc.visitor_hash(date(2030, 1, 1), "203.0.113.7", UA) != svc.visitor_hash(
        date(2030, 1, 2), "203.0.113.7", UA
    )


@pytest.mark.parametrize(
    "headers,ua",
    [
        ({"dnt": "1"}, UA),
        ({"sec-gpc": "1"}, UA),
        ({}, "Googlebot/2.1 (+http://www.google.com/bot.html)"),
        ({}, "curl/8.0"),
        ({}, "   "),
    ],
)
async def test_robots_and_privacy_signals_are_never_counted(client, maker, headers, ua):
    r = await client.post(
        "/v1/public/visit",
        json={"path": "/"},
        headers={"x-forwarded-for": "203.0.113.7", **({"user-agent": ua} if ua else {}), **headers},
    )
    assert r.status_code == 204 and await totals(maker) == (0, 0)


@pytest.mark.parametrize(
    "path", ["/admin", "/admin/marketing/campaigns", "/i/abc123", "/s/AbCdEf0123456789xyzQWERTYuiop1234"]
)
async def test_the_back_office_and_private_links_are_never_counted(client, maker, path):
    assert (await visit(client, path)).status_code == 204
    assert await totals(maker) == (0, 0)


@pytest.mark.parametrize(
    "raw,name",
    [
        ("/", "/"),
        ("/signup?token=secret", "/signup"),
        ("/privacy#storage", "/privacy"),
        ("//signup/", "/signup"),
        ("/ai-newsroom/0123456789abcdef0123456789abcdef", "/ai-newsroom/:id"),
        ("/ai-newsroom/new", "/ai-newsroom/new"),
        ("/billing/stripe/9f86d081884c7d659a2feaa0c55ad015", "/billing/stripe/:id"),
        ("/latest-stories/acme-launches-its-new-payments-product", "/latest-stories/:story"),
        ("/made-up/page/xyz", "/other"),
        ("no-slash", "/other"),
        ("/" + "a" * 300, "/other"),
        ("/admin/x", None),
        ("/i/x", None),
        ("/s/x", None),
    ],
)
def test_pages_are_named_from_a_fixed_list(raw, name):
    assert svc.normalize_path(raw) == name


async def test_made_up_pages_cannot_fill_the_tables(client, maker):
    for i in range(20):
        await visit(client, f"/spam/{i}", ip=f"198.51.100.{i}")
    from app.models import SitePageDaily

    async with maker() as s:
        rows = (await s.execute(select(SitePageDaily))).scalars().all()
    assert [(r.path, r.views) for r in rows] == [("/other", 20)]


@pytest.mark.parametrize(
    "ref,source,medium,campaign,expected",
    [
        ("", "", "", "", ("direct", "")),
        ("www.google.com", "", "", "", ("search", "google")),
        ("duckduckgo.com", "", "", "", ("search", "duckduckgo")),
        ("l.facebook.com", "", "", "", ("social", "facebook")),
        ("t.co", "", "", "", ("social", "x")),
        ("lnkd.in", "", "", "", ("social", "linkedin")),
        ("news.example.org", "", "", "", ("referral", "news.example.org")),
        ("", "cover_founder", "email", "Welcome Nudge: Week 1!", ("email", "welcome-nudge-week-1")),
        (
            "mail.google.com",
            "cover_founder",
            "email",
            "spring",
            ("email", "spring"),
        ),  # our own email wins over the webmail it was opened in
        ("", "ads", "cpc", "", ("other", "paid")),
        ("not a host!", "", "", "", ("direct", "")),
        ("notgoogle.com", "", "", "", ("referral", "notgoogle.com")),
    ],
)
def test_where_visitors_came_from(ref, source, medium, campaign, expected):
    assert svc.classify(ref, source, medium, campaign) == expected


async def test_each_visitor_is_credited_to_where_they_first_came_from_that_day(client, maker):
    await visit(client, "/", ip="198.51.100.1", referrer_host="www.google.com")
    await visit(client, "/signup", ip="198.51.100.1")  # moving around the site does not change it
    await visit(client, "/", ip="198.51.100.2", utm_source="cover_founder", utm_medium="email", utm_campaign="welcome")
    await visit(client, "/", ip="198.51.100.3")
    async with maker() as s:
        rows = {(r.source, r.detail): r.visitors for r in (await s.execute(select(SiteSourceDaily))).scalars()}
    assert rows == {("search", "google"): 1, ("email", "welcome"): 1, ("direct", ""): 1}


async def test_too_many_different_sources_are_lumped_together(client, maker, monkeypatch):
    monkeypatch.setattr(svc, "MAX_SOURCES_PER_DAY", 3)
    for i in range(6):
        await visit(client, "/", ip=f"198.51.100.{i}", referrer_host=f"site{i}.example.org")
    async with maker() as s:
        rows = {(r.source, r.detail): r.visitors for r in (await s.execute(select(SiteSourceDaily))).scalars()}
    assert len(rows) == 4 and rows[("other", "")] == 3


async def test_the_report_has_every_day_pages_and_sources(client, maker, workspace):
    await visit(client, "/", ip="198.51.100.1", referrer_host="www.google.com")
    await visit(client, "/signup", ip="198.51.100.1")
    await visit(client, "/", ip="198.51.100.2")
    r = (
        await client.get(
            "/v1/admin/site-visits?start=" + svc.today().isoformat() + "&end=" + svc.today().isoformat(), headers=OPS
        )
    ).json()
    assert r["totals"] == {"visitors": 2, "pageviews": 3}
    assert r["series"] == [{"date": svc.today().isoformat(), "visitors": 2, "pageviews": 3}]
    assert r["pages"] == [{"path": "/", "views": 2}, {"path": "/signup", "views": 1}]
    assert {(s["source"], s["detail"]): s["visitors"] for s in r["sources"]} == {
        ("search", "google"): 1,
        ("direct", ""): 1,
    }
    assert "once a day" in r["definitions"]["visitors"]
    wide = (await client.get("/v1/admin/site-visits", headers=OPS)).json()
    assert len(wide["series"]) == 30 and wide["totals"]["visitors"] == 2  # a month by default, empty days included


async def test_the_report_checks_its_dates_and_who_asks(client, workspace):
    assert (await client.get("/v1/admin/site-visits?start=2030-02-01&end=2030-01-01", headers=OPS)).status_code == 422
    assert (await client.get("/v1/admin/site-visits?start=2020-01-01&end=2030-01-01", headers=OPS)).status_code == 422
    assert (await client.get("/v1/admin/site-visits", headers=OWNER)).status_code in (401, 403)
    assert (await client.get("/v1/admin/site-visits")).status_code in (401, 403)


async def test_old_daily_codes_are_removed_but_the_totals_stay(client, maker):
    from datetime import timedelta

    await visit(client, "/")
    async with maker() as s:
        mark = (await s.execute(select(SiteVisitMark))).scalar_one()
        mark.day = svc.today() - timedelta(days=3)
        await s.commit()
    assert await svc.prune_marks() == 1
    assert await totals(maker) == (1, 1)


async def test_bad_beacons_are_refused(client):
    assert (await client.post("/v1/public/visit", json={}, headers=h())).status_code == 422
    assert (await client.post("/v1/public/visit", json={"path": "/" + "x" * 400}, headers=h())).status_code == 422
