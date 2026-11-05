"""Human-fulfilled distribution requests. Payment and submission are one atomic operation."""

import re
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Response
from fastapi.responses import HTMLResponse
from pydantic import BaseModel, EmailStr, Field, TypeAdapter, ValidationError
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import Principal, current_principal, require
from app.db import get_session
from app.integrations import registry
from app.models import Asset, BrandAsset, Brief, DistributionRequest, Project, ScriptVersion, Workspace
from app.models.base import utcnow
from app.services import distribution as fulfillment
from app.services import distribution_catalog as catalog_service
from app.services import ledger
from app.services.audit import audit
from app.services.ratelimit import limit

router = APIRouter(tags=["distribution"])
NAMES = [
    "Empire Magazine Africa",
    "Techpoint Africa",
    "Nairametrics",
    "Tech Next",
    "Tech Cabal",
    "Techeconomy",
    "Condia",
    "88 Lately",
    "Crest Africa",
    "Talented Women Network",
    "Iconic Africa",
    "Iconic Global",
    "CoinSpeaks",
    "The Cryptofy",
    "The Crypto Reporters",
    "The Coins Report",
    "The Coins Insider",
    "Business Insider",
    "Street Insider",
    "Bar Chart",
    "The Globe and Mail",
    "Benzinga",
    "Tribune",
    "Sun",
    "New Telegraph",
    "Independent",
    "Vanguard",
    "ThisDay",
    "The Guardian",
    "Punch",
    "Daily Trust",
    "Daily Post",
    "Business Day",
    "P.M. News",
    "Premium Times",
    "The Nation",
    "Celeb Spotlight",
    "News Nine",
    "Naijaloaded",
    "Tooxclusive",
    "NotJustOk",
    "9jaflaver",
    "Mp3bullet",
    "Naijamusic",
    "MP3Naija",
    "AlbumTalks",
    "P mp Kulture",
    "Pilot Newspaper",
    "Leadership Newspaper",
    "AIT News",
    "TVC News",
    "The Daily Times",
    "Daily Nation",
    # United States tech news channels (appended, so every earlier outlet keeps its ID)
    "TechBullion",
    "Investing.com",
    "USA Today",
    "Business Outstanders",
    "Big News Network",
    "MSN",
    "NewsBreak",
    "USA Wire",
    # Canadian news channels (appended)
    "Toronto Star",
    "Montreal Gazette",
    "Toronto Sun",
    "Vancouver Sun",
    "Hello! Canada",
    "National Post",
    "Financial Post",
    "Canada-Wide Newswire",
    # UK and European news channels (appended)
    "The Sun (UK)",
    "Rolling Stones UK",
    "London Loves Business",
    "Business Matters UK",
    "Property Portfolio Investor UK",
    "Techround UK",
    "Luxury Lifestyle Magazine UK",
    "Vanity Fair Germany",
    "Mashable NL",
    "European Business Review",
    "Vogue Switzerland",
    "Forbes Liechtenstein",
    "Portugal News",
    # Middle East news channels (appended)
    "Gulf Business",
    "Forbes Middle East",
    "Arabian Business",
    "Cosmopolitan Middle East",
    "Gulf Times",
    "Gulf News",
    "Qatar Tribune",
    "Dubai Weekly",
    "Arabian Startup",
    # United States news channels (appended)
    "US-Wide Newswire",
    "Fortune",
    "Apple News",
    "Associated Press",
    "New York Weekly",
    "Reuters",
    "Bloomberg",
    "Fox Business",
]
# Keep the existing IDs stable: drafts and paid requests refer to these outlets by ID.
OUTLET_CATEGORIES = {
    "Media outlets": NAMES[:12],
    "Crypto News Channels": NAMES[12:17],
    "Tech News Channels": NAMES[17:22]
    + NAMES[53:61],  # the owner's sheet: US channels (and The Globe and Mail, a Canadian one)
    "Nigeria News Channels": NAMES[22:38] + NAMES[47:53],
    "Entertainment News Channels": NAMES[38:47],
    "Canada News Channels": NAMES[61:69],
    "UK & Europe News Channels": NAMES[69:82],
    "Middle East News Channels": NAMES[82:91],
    "US News Channels": NAMES[91:],
}
CATEGORY_BY_NAME = {name: category for category, names in OUTLET_CATEGORIES.items() for name in names}
# Owner-supplied prices: original Credit on CF values plus the Nigerian sheet's final CF Credit + Margins values (already include its five-credit margin).
DEFAULT_OUTLET_CREDITS = {
    "Empire Magazine Africa": "42",
    "Techpoint Africa": "83",
    "Nairametrics": "124",
    "Tech Next": "69",
    "Tech Cabal": "97",
    "Techeconomy": "61",
    "Condia": "138",
    "88 Lately": "28",
    "Crest Africa": "42",
    "Talented Women Network": "42",
    "Iconic Africa": "28",
    "Iconic Global": "28",
    "CoinSpeaks": "42",
    "The Cryptofy": "42",
    "The Crypto Reporters": "42",
    "The Coins Report": "42",
    "The Coins Insider": "42",
    "Tribune": "18.8",
    "Sun": "87.5",
    "New Telegraph": "60.0",
    "Independent": "18.8",
    "Vanguard": "18.8",
    "ThisDay": "27.0",
    "The Guardian": "115.1",
    "Punch": "128.8",
    "Daily Trust": "22.9",
    "Daily Post": "128.8",
    "Business Day": "101.3",
    "P.M. News": "18.8",
    "Premium Times": "87.5",
    "The Nation": "73.8",
    "Pilot Newspaper": "87.5",
    "Leadership Newspaper": "87.5",
    "AIT News": "115.1",
    "TVC News": "115.1",
    "The Daily Times": "137.1",
    "Daily Nation": "651.6",
    # Tech news channels (US): the sheet's CF Credit + Margins value (30% margin added).
    "TechBullion": "19.5",
    "Street Insider": "36.4",
    "Investing.com": "191.1",
    "Bar Chart": "24.7",
    "USA Today": "92.3",
    "The Globe and Mail": "94.9",
    "Benzinga": "143",
    "Business Outstanders": "29.9",
    "Big News Network": "19.5",
    "Business Insider": "87.1",
    "MSN": "94.9",
    "NewsBreak": "44.2",
    "USA Wire": "19.5",
    # Canada news channels: the sheet's CF Credit + Margins value (30% margin added).
    "Toronto Star": "1084.2",
    "Montreal Gazette": "241.8",
    "Toronto Sun": "241.8",
    "Vancouver Sun": "217.1",
    "Hello! Canada": "1565.2",
    "National Post": "1878.5",
    "Financial Post": "1878.5",
    "Canada-Wide Newswire": "386.1",
    # UK and Europe news channels: the sheet's CF Credit + Margins value.
    "The Sun (UK)": "9149.4",
    "Rolling Stones UK": "1589.9",
    "London Loves Business": "722.8",
    "Business Matters UK": "482.3",
    "Property Portfolio Investor UK": "482.3",
    "Techround UK": "422.5",
    "Luxury Lifestyle Magazine UK": "313.3",
    "Vanity Fair Germany": "239.2",
    "Mashable NL": "1011.4",
    "European Business Review": "180.7",
    "Vogue Switzerland": "109.2",
    "Forbes Liechtenstein": "180.7",
    "Portugal News": "422.5",
    # Middle East news channels: the sheet's CF Credit + Margins value.
    "Gulf Business": "3192.8",
    "Forbes Middle East": "2407.6",
    "Arabian Business": "1901.9",
    "Cosmopolitan Middle East": "1901.9",
    "Gulf Times": "1016.6",
    "Gulf News": "939.9",
    "Qatar Tribune": "431.6",
    "Dubai Weekly": "157.3",
    "Arabian Startup": "157.3",
    # US news channels: the sheet's CF Credit + Margins value (30% margin added).
    "US-Wide Newswire": "867.1",
    "Fortune": "843.7",
    "Apple News": "301.6",
    "Associated Press": "241.8",
    "New York Weekly": "239.2",
    "Reuters": "1084.2",
    "Bloomberg": "4815.2",
    "Fox Business": "4695.6",
    # Entertainment news channels: the sheet's CF Credit + Margins value (61) for every one of them.
    "Naijaloaded": "61",
    "Tooxclusive": "61",
    "NotJustOk": "61",
    "9jaflaver": "61",
    "Mp3bullet": "61",
    "Naijamusic": "61",
    "MP3Naija": "61",
    "AlbumTalks": "61",
    "P mp Kulture": "61",
}
# Where an outlet can be found, for the filters visitors and customers use: a topic and a country (the region follows from the country).
TOPICS = ("Technology", "General News", "Gossip Blogs")
LOCATIONS = {
    "Africa": ("Nigeria", "Ghana", "Kenya", "Uganda"),
    "North America": ("Canada", "United States"),
    "Middle East": ("United Arab Emirates", "Qatar"),
    "Europe": ("United Kingdom", "Germany", "Netherlands", "Switzerland", "Liechtenstein", "Portugal"),
}
REGION_OF = {country: region for region, countries in LOCATIONS.items() for country in countries}
_TECH = ("Techpoint Africa", "Tech Next", "Tech Cabal", "Techeconomy", "Condia")
_CRYPTO = ("CoinSpeaks", "The Cryptofy", "The Crypto Reporters", "The Coins Report", "The Coins Insider")
_GOSSIP = (
    "88 Lately",
    "Celeb Spotlight",
    "Naijaloaded",
    "Tooxclusive",
    "NotJustOk",
    "9jaflaver",
    "Mp3bullet",
    "Naijamusic",
    "MP3Naija",
    "AlbumTalks",
    "P mp Kulture",
)
_US_TECH = (
    "TechBullion",
    "Street Insider",
    "Investing.com",
    "Bar Chart",
    "USA Today",
    "The Globe and Mail",
    "Benzinga",
    "Business Outstanders",
    "Big News Network",
    "Business Insider",
    "MSN",
    "NewsBreak",
    "USA Wire",
)  # the owner's "Tech news channels" sheet
_ABROAD = {
    "TechBullion": "United States",
    "Investing.com": "United States",
    "USA Today": "United States",
    "Business Outstanders": "United States",
    "Big News Network": "United States",
    "MSN": "United States",
    "NewsBreak": "United States",
    "USA Wire": "United States",
    "Business Insider": "United States",
    "Street Insider": "United States",
    "Bar Chart": "United States",
    "Benzinga": "United States",
    "The Globe and Mail": "Canada",
    "US-Wide Newswire": "United States",
    "Fortune": "United States",
    "Apple News": "United States",
    "Associated Press": "United States",
    "New York Weekly": "United States",
    "Reuters": "United States",
    "Bloomberg": "United States",
    "Fox Business": "United States",
    "Gulf Business": "United Arab Emirates",
    "Forbes Middle East": "United Arab Emirates",
    "Arabian Business": "United Arab Emirates",
    "Cosmopolitan Middle East": "United Arab Emirates",
    "Gulf Times": "Qatar",
    "Gulf News": "United Arab Emirates",
    "Qatar Tribune": "Qatar",
    "Dubai Weekly": "United Arab Emirates",
    "Arabian Startup": "United Arab Emirates",
    "The Sun (UK)": "United Kingdom",
    "Rolling Stones UK": "United Kingdom",
    "London Loves Business": "United Kingdom",
    "Business Matters UK": "United Kingdom",
    "Property Portfolio Investor UK": "United Kingdom",
    "Techround UK": "United Kingdom",
    "Luxury Lifestyle Magazine UK": "United Kingdom",
    "Vanity Fair Germany": "Germany",
    "Mashable NL": "Netherlands",
    "European Business Review": "United Kingdom",
    "Vogue Switzerland": "Switzerland",
    "Forbes Liechtenstein": "Liechtenstein",
    "Portugal News": "Portugal",
    "Toronto Star": "Canada",
    "Montreal Gazette": "Canada",
    "Toronto Sun": "Canada",
    "Vancouver Sun": "Canada",
    "Hello! Canada": "Canada",
    "National Post": "Canada",
    "Financial Post": "Canada",
    "Canada-Wide Newswire": "Canada",
    "Daily Nation": "Kenya",
}


def outlet_tags(name: str) -> tuple[str, str | None]:
    """(topic, country) for an outlet. The crypto channels cover Africa as a whole, so they have no single country."""
    topic = (
        "Technology"
        if name in _TECH or name in _CRYPTO or name in _US_TECH or name in ("Techround UK", "Arabian Startup")
        else "Gossip Blogs"
        if name in _GOSSIP
        else "General News"
    )
    return topic, None if name in _CRYPTO else _ABROAD.get(name, "Nigeria")


def _outlet(i: int, name: str) -> dict:
    topic, country = outlet_tags(name)
    return {
        "id": str(i + 1),
        "name": name,
        "region": REGION_OF[country] if country else "Africa",
        "country": country,
        "topic": topic,
        "credits": DEFAULT_OUTLET_CREDITS.get(name, "0"),
        "category": CATEGORY_BY_NAME[name],
    }


OUTLETS = {str(i + 1): _outlet(i, name) for i, name in enumerate(NAMES)}


class MediaChoice(BaseModel):
    include_logo: bool = True
    include_pictures: bool = True


class SubmissionQuote(BaseModel):
    expected_total: Decimal | None = Field(default=None, ge=0)
    quote_version: str | None = Field(default=None, max_length=64)


class DraftIn(BaseModel):
    stage: Literal["outlets", "content", "contact", "review"] = "outlets"
    outlet_ids: list[str] = Field(default_factory=list, max_length=100)
    project_id: str | None = None
    story_project_id: str | None = None
    announcement_source: Literal["platform", "custom"] = "custom"
    headline: str = Field(default="", max_length=300)
    announcement: str = Field(default="", max_length=50000)
    contact_name: str = Field(default="", max_length=200)
    contact_email: str = Field(default="", max_length=320)
    phone: str = Field(default="", max_length=40)
    # Optional legacy fields preserve existing drafts and older clients.
    whatsapp: str = Field(default="", max_length=40)
    phone_country: str = Field(default="", pattern=r"^(?:[A-Z]{2})?$")
    whatsapp_country: str = Field(default="", pattern=r"^(?:[A-Z]{2})?$")
    logo_key: str = Field(default="", max_length=500)
    picture_keys: list[str] = Field(default_factory=list, max_length=10)
    media_options: dict[str, MediaChoice] = Field(default_factory=dict, max_length=100)


class StatusIn(BaseModel):
    status: Literal["submitted", "in_progress", "completed"]


def quoted_lines(body, catalog):
    try:
        return catalog_service.quote(body.model_dump(), catalog)
    except catalog_service.QuoteTooLarge as error:
        raise HTTPException(422, str(error)) from error


def out(row: DistributionRequest) -> dict:
    return {
        "id": row.id,
        "workspace_id": row.workspace_id,
        "created_by": row.created_by,
        "status": row.status,
        "stage": row.stage,
        "data": {
            **row.data,
            "outlets": row.data.get("outlets", [OUTLETS[i] for i in row.data.get("outlet_ids", []) if i in OUTLETS]),
        },
        "total_credits": str(row.total_credits),
        "paid": row.paid_at is not None,
        "created_at": row.created_at,
        "updated_at": row.updated_at,
        "submitted_at": row.submitted_at,
        "email_sent": row.email_sent_at is not None,
    }


async def result(db, row, *, admin=False):
    value = {**out(row), **await fulfillment.details(db, row, admin=admin)}
    await db.commit()  # Release read locks before post-response notification tasks open their session.
    return value


async def owned(db: AsyncSession, id: str, p: Principal) -> DistributionRequest:
    row = await db.get(DistributionRequest, id)
    if row is None or row.workspace_id != p.workspace.id:
        raise HTTPException(404, "Distribution request not found")
    return row


async def validate(db: AsyncSession, body: DraftIn, workspace_id: str):
    if len(set(body.outlet_ids)) != len(body.outlet_ids) or any(i not in OUTLETS for i in body.outlet_ids):
        raise HTTPException(422, "Choose valid, distinct outlets")
    if any(i not in OUTLETS for i in body.media_options):
        raise HTTPException(422, "Choose valid outlet media options")
    hidden = {o["id"] for o in await catalog_service.catalog(db) if catalog_service.is_hidden(o)}
    if hidden & set(body.outlet_ids):
        raise HTTPException(422, "One of the outlets you chose is not available right now. Remove it and try again.")
    if body.project_id:
        project = await db.get(Project, body.project_id)
        if project is None or project.workspace_id != workspace_id or project.state != "final_ready":
            raise HTTPException(422, "Select one of your completed videos")
    if body.story_project_id:
        story = (
            await db.execute(
                select(ScriptVersion.id)
                .join(Project, Project.id == ScriptVersion.project_id)
                .where(
                    Project.workspace_id == workspace_id,
                    Project.id == body.story_project_id,
                    ScriptVersion.story.is_not(None),
                )
            )
        ).first()
        if story is None:
            raise HTTPException(422, "Choose a story written in your workspace")
    for key, kinds in [
        (body.logo_key, {"logo_light", "logo_dark", "product_image"}),
        *[(k, {"product_image"}) for k in body.picture_keys],
    ]:
        if not key:
            continue
        asset = (
            await db.execute(
                select(BrandAsset).where(
                    BrandAsset.key == key, BrandAsset.workspace_id == workspace_id, BrandAsset.status == "clean"
                )
            )
        ).scalar_one_or_none()
        if asset is None or asset.kind not in kinds:
            raise HTTPException(422, "Images must be your own checked uploads")


@router.get("/v1/distribution/outlets")
async def outlets(p: Principal = Depends(current_principal), db: AsyncSession = Depends(get_session)) -> dict:
    items = await catalog_service.catalog(db)
    shown = [o for o in items if not catalog_service.is_hidden(o)]  # free channels are hidden for now
    return {
        "outlets": shown,
        "quote_version": catalog_service.version(
            items
        ),  # always over the full list, so a submit's price check still matches
        "coming_soon": _coming_soon(shown),
        "filters": _filters(),
    }


def _filters() -> dict:
    return {"topics": list(TOPICS), "locations": [{"region": r, "countries": list(c)} for r, c in LOCATIONS.items()]}


def _coming_soon(shown: list[dict]) -> list[str]:
    """Countries people can filter by that have no outlet yet."""
    have = {o.get("country") for o in shown}
    return [c for c in REGION_OF if c not in have]


@router.get("/v1/public/distribution/outlets", dependencies=[Depends(limit("public-outlets", 120, 60))])
async def public_outlets(response: Response, db: AsyncSession = Depends(get_session)) -> dict:
    """What a visitor who is not signed in may browse before choosing outlets: name, topic, place and price. Nothing internal."""
    response.headers["Cache-Control"] = "public, max-age=60"
    shown = [o for o in await catalog_service.catalog(db) if not catalog_service.is_hidden(o)]
    keep = ("id", "name", "topic", "category", "region", "country", "credits")
    return {
        "outlets": [{k: o[k] for k in keep} for o in shown],
        "coming_soon": _coming_soon(shown),
        "filters": _filters(),
    }


@router.get("/v1/distribution/stories")
async def stories(p: Principal = Depends(current_principal), db: AsyncSession = Depends(get_session)) -> list[dict]:
    scripts = (
        (
            await db.execute(
                select(ScriptVersion)
                .join(Project, Project.id == ScriptVersion.project_id)
                .where(Project.workspace_id == p.workspace.id, ScriptVersion.story.is_not(None))
                .order_by(ScriptVersion.created_at.desc(), ScriptVersion.version.desc())
            )
        )
        .scalars()
        .all()
    )
    result, seen = [], set()
    for script in scripts:
        if script.project_id in seen or not script.story:
            continue
        seen.add(script.project_id)
        story = script.story
        parts = [story.get("dek", "")]
        for section in story.get("sections", []):
            if section.get("heading"):
                parts.append(section["heading"])
            parts.extend(section.get("paragraphs", []))
        if story.get("about"):
            parts.append(story["about"])
        result.append(
            {
                "project_id": script.project_id,
                "headline": story.get("headline", ""),
                "announcement": "\n\n".join(x for x in parts if x.strip()),
            }
        )
    return result


@router.get("/v1/distribution/videos")
async def videos(p: Principal = Depends(current_principal), db: AsyncSession = Depends(get_session)) -> list[dict]:
    projects = (
        (
            await db.execute(
                select(Project)
                .where(Project.workspace_id == p.workspace.id, Project.state == "final_ready")
                .order_by(Project.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    result = []
    for project in projects:
        script = (
            (
                await db.execute(
                    select(ScriptVersion)
                    .where(ScriptVersion.project_id == project.id)
                    .order_by(ScriptVersion.version.desc())
                )
            )
            .scalars()
            .first()
        )
        story = script.story if script and script.story else {}
        text = "\n\n".join(
            [story.get("dek", ""), *[p for s in story.get("sections", []) for p in s.get("paragraphs", [])]]
        )
        brief = (await db.execute(select(Brief).where(Brief.project_id == project.id))).scalar_one_or_none()
        video = (
            (await db.execute(select(Asset).where(Asset.project_id == project.id, Asset.type == "render")))
            .scalars()
            .first()
        )
        result.append(
            {
                "id": project.id,
                "headline": story.get("headline") or (brief.raw_text[:120] if brief else ""),
                "announcement": text
                or "\n\n".join(segment.get("text", "") for segment in (script.segments if script else [])),
                "video_url": registry.get_storage().presign_get(video.storage_key, 600) if video else None,
            }
        )
    return result


@router.get("/v1/distribution")
async def listing(p: Principal = Depends(current_principal), db: AsyncSession = Depends(get_session)) -> list[dict]:
    rows = (
        await db.execute(
            select(DistributionRequest)
            .where(DistributionRequest.workspace_id == p.workspace.id)
            .order_by(DistributionRequest.updated_at.desc())
        )
    ).scalars()
    return [await result(db, r) for r in rows]


@router.post("/v1/distribution", dependencies=[Depends(limit("distribution-create", 30, 3600))])
async def create(p: Principal = Depends(current_principal), db: AsyncSession = Depends(get_session)) -> dict:
    row = DistributionRequest(workspace_id=p.workspace.id, created_by=p.user.email, data=DraftIn().model_dump())
    db.add(row)
    await db.commit()
    return await result(db, row)


@router.get("/v1/distribution/{id}")
async def detail(id: str, p: Principal = Depends(current_principal), db: AsyncSession = Depends(get_session)) -> dict:
    return await result(db, await owned(db, id, p))


@router.put("/v1/distribution/{id}")
async def save(
    id: str, body: DraftIn, p: Principal = Depends(current_principal), db: AsyncSession = Depends(get_session)
) -> dict:
    await owned(db, id, p)
    await validate(db, body, p.workspace.id)
    catalog = await catalog_service.catalog(db, admin=True)
    lines = quoted_lines(body, catalog)
    total = sum((Decimal(o["credits"]) for o in lines), Decimal("0"))
    row = (
        await db.execute(
            update(DistributionRequest)
            .where(DistributionRequest.id == id, DistributionRequest.status == "draft")
            .values(data=body.model_dump(), stage=body.stage, total_credits=total, updated_at=utcnow())
            .returning(DistributionRequest)
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(409, "Submitted requests cannot be edited")
    await db.commit()
    return await result(db, row)


@router.post("/v1/distribution/{id}/submit")
async def submit(
    id: str,
    tasks: BackgroundTasks,
    expected: SubmissionQuote | None = None,
    p: Principal = Depends(current_principal),
    db: AsyncSession = Depends(get_session),
) -> dict:
    # A conditional update claims the request on both SQLite and Postgres; concurrent submits cannot debit twice.
    await owned(db, id, p)
    now = utcnow()
    row = (
        await db.execute(
            update(DistributionRequest)
            .where(DistributionRequest.id == id, DistributionRequest.status == "draft")
            .values(status="submitted", updated_at=now)
            .returning(DistributionRequest)
        )
    ).scalar_one_or_none()
    if row is None:
        row = await owned(db, id, p)
        tasks.add_task(fulfillment.deliver_request, row.id)
        return await result(db, row)
    body = DraftIn.model_validate(row.data)
    if body.announcement_source == "platform" and not body.story_project_id:
        raise HTTPException(422, "Select the platform story you want to use")
    await validate(db, body, p.workspace.id)
    if not body.outlet_ids or not all(
        x.strip()
        for x in [
            body.headline,
            body.announcement,
            body.contact_name,
            body.contact_email,
            body.phone,
        ]
    ):
        raise HTTPException(422, "Choose outlets, add your release and all contact details")
    try:
        TypeAdapter(EmailStr).validate_python(body.contact_email)
    except ValidationError as e:
        raise HTTPException(422, "Enter a valid contact email") from e
    if not re.fullmatch(r"\+[1-9][0-9]{6,14}", re.sub(r"[() .-]", "", body.phone)):
        raise HTTPException(422, "Enter a valid phone number, including the country code")
    catalog = await catalog_service.catalog(db, admin=True)
    lines = quoted_lines(body, catalog)
    total = sum((Decimal(o["credits"]) for o in lines), Decimal("0"))
    if total != row.total_credits or (
        expected
        and (
            (expected.expected_total is not None and expected.expected_total != total)
            or (expected.quote_version is not None and expected.quote_version != catalog_service.version(catalog))
        )
    ):
        row.status, row.total_credits, row.stage = "draft", total, "review"
        await db.commit()
        raise HTTPException(
            409, "Outlet pricing or image policies changed. Review the updated total before submitting."
        )
    ws = (
        await db.execute(
            select(Workspace)
            .where(Workspace.id == p.workspace.id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).scalar_one()
    if ws.suspended:
        raise HTTPException(403, "This workspace is suspended")
    if ws.credit_balance < total:
        # Persist the draft's checkout stage even though payment failed.
        row.status, row.stage, row.total_credits = "draft", "review", total
        await db.commit()
        raise HTTPException(
            402,
            {
                "error": "insufficient_credits",
                "message": "Top up your wallet to submit. Your draft is saved.",
                "required": str(total),
                "balance": str(ws.credit_balance),
                "shortfall": str(total - ws.credit_balance),
            },
        )
    if total:
        await ledger.apply(
            db,
            ws,
            -total,
            "usage",
            ref=f"distribution:{id}",
            stage="distribution",
            description=f"Distribution to {len(body.outlet_ids)} outlets",
        )
    row.data = {**body.model_dump(), "outlets": lines}
    row.total_credits, row.paid_at, row.submitted_at, row.stage = total, now, now, "submitted"
    audit(
        db,
        p.user.email,
        "distribution.submitted",
        target_type="distribution",
        target_id=id,
        detail={"credits": str(total), "outlets": len(body.outlet_ids)},
    )
    await fulfillment.plan_submission(db, row, catalog)
    await db.commit()
    tasks.add_task(fulfillment.deliver_request, row.id)
    return await result(db, row)


@router.get("/v1/admin/distribution")
async def admin_list(
    p: Principal = Depends(require("operations.view")), db: AsyncSession = Depends(get_session)
) -> list[dict]:
    rows = (await db.execute(select(DistributionRequest).order_by(DistributionRequest.updated_at.desc()))).scalars()
    return [await result(db, r) for r in rows]


@router.get("/v1/admin/distribution/{id}/assets")
async def admin_assets(
    id: str, p: Principal = Depends(require("operations.view")), db: AsyncSession = Depends(get_session)
) -> dict:
    row = await db.get(DistributionRequest, id)
    if row is None:
        raise HTTPException(404, "Request not found")
    data = row.data
    video = (
        (await db.execute(select(Asset).where(Asset.project_id == data["project_id"], Asset.type == "render")))
        .scalars()
        .first()
        if data.get("project_id")  # a video is optional: a request can be just the story
        else None
    )
    keys = [data.get("logo_key"), *data.get("picture_keys", [])]
    return {
        "video_url": registry.get_storage().presign_get(video.storage_key, 600) if video else None,
        "images": [{"key": k, "url": registry.get_storage().presign_get(k, 600)} for k in keys if k],
    }


@router.patch("/v1/admin/distribution/{id}")
async def admin_status(
    id: str,
    body: StatusIn,
    p: Principal = Depends(require("operations.manage")),
    db: AsyncSession = Depends(get_session),
) -> dict:
    row = await db.get(DistributionRequest, id)
    if row is None:
        raise HTTPException(404, "Request not found")
    if not row.paid_at:
        raise HTTPException(409, "An unpaid draft cannot be marked as submitted")
    row = (
        await db.execute(
            update(DistributionRequest)
            .where(DistributionRequest.id == id)
            .values(updated_at=utcnow())
            .returning(DistributionRequest)
            .execution_options(populate_existing=True)
        )
    ).scalar_one()
    from app.models import DistributionPlacement

    placements = (
        (await db.execute(select(DistributionPlacement).where(DistributionPlacement.request_id == id))).scalars().all()
    )
    if body.status == "completed" and (
        not placements or any(x.status != "published" or not x.published_url for x in placements)
    ):
        raise HTTPException(409, "Add each outlet's published link before completing the request")
    if body.status != "completed":
        for placement in placements:
            if placement.status != "published":
                placement.status = "pending" if body.status == "submitted" else "in_progress"
    row.status = "completed" if placements and all(x.status == "published" for x in placements) else body.status
    row.updated_at = utcnow()
    fulfillment.activity(db, row, "status_changed", {"status": row.status}, actor=p.user.email)
    audit(
        db,
        p.user.email,
        "distribution.status_changed",
        target_type="distribution",
        target_id=id,
        detail={"status": row.status},
    )
    await db.commit()
    return await result(db, row)


@router.post("/v1/admin/distribution/{id}/confirmation")
async def retry_email(
    id: str,
    tasks: BackgroundTasks,
    p: Principal = Depends(require("operations.manage")),
    db: AsyncSession = Depends(get_session),
) -> dict:
    row = await db.get(DistributionRequest, id)
    if row is None or row.paid_at is None:
        raise HTTPException(404, "Submitted request not found")
    tasks.add_task(fulfillment.deliver_request, row.id)
    return await result(db, row)


@router.get("/v1/distribution/{id}/invoice", response_class=HTMLResponse)
async def download_invoice(id: str, p: Principal = Depends(current_principal), db: AsyncSession = Depends(get_session)):
    row = await owned(db, id, p)
    if not row.paid_at:
        raise HTTPException(409, "Receipts are available after payment and submission")
    return HTMLResponse(
        fulfillment.receipt_html(row),
        headers={
            "Content-Disposition": f'attachment; filename="distribution-{row.id}.html"',
            "Cache-Control": "no-store",
        },
    )
