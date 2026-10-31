"""Only published editorial snapshots are public; raw source text stays in the back office."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations import registry
from app.models import NewsImage, NewsStory

CATEGORY = "CF Technology Breaking News"


async def images(db: AsyncSession, row: NewsStory) -> list[dict]:
    data = row.published_data or {}
    chosen = data.get("pictures", [])
    rows = {
        i.id: i
        for i in (
            await db.execute(select(NewsImage).where(NewsImage.story_id == row.id, NewsImage.status == "clean"))
        ).scalars()
    }
    return [
        {
            "url": registry.get_storage().presign_get(rows[p["id"]].key, 604800),
            "caption": " · ".join(filter(None, [p.get("caption"), p.get("credit")])),
        }
        for p in chosen
        if p["id"] in rows
    ]


async def card(db: AsyncSession, row: NewsStory) -> dict:
    data = row.published_data or {}
    pictures = await images(db, row)
    return {
        "slug": row.slug,
        "title": data["headline"],
        "summary": data["summary"],
        "company": "Cover Founder News",
        "industry": "Technology",
        "category": CATEGORY,
        "has_video": False,
        "published_at": row.published_at,
        "duration_s": None,
        "thumbnail_url": pictures[0]["url"] if pictures else None,
    }


async def page(db: AsyncSession, row: NewsStory) -> dict:
    data = row.published_data or {}
    return {
        **await card(db, row),
        "dateline": None,
        "sections": [{"heading": "", "paragraphs": [p.strip() for p in data["body"].split("\n\n") if p.strip()]}],
        "about": "",
        "pictures": await images(db, row),
        "video_url": None,
        "disclosure": "",
        "source_name": data.get("source_name"),
        "source_url": data.get("source_url"),
    }


async def find(db: AsyncSession, slug: str) -> NewsStory | None:
    return (
        await db.execute(
            select(NewsStory).where(
                NewsStory.slug == slug, NewsStory.status == "published", NewsStory.published_data.is_not(None)
            )
        )
    ).scalar_one_or_none()
