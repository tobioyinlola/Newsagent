"""Only published editorial snapshots are public; raw source text stays in the back office."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations import registry
from app.models import NewsImage, NewsStory, NewsVideo

CATEGORY = "CF News"


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
            "id": p["id"],
            "url": registry.get_storage().presign_get(rows[p["id"]].key, 604800),
            "caption": " · ".join(filter(None, [p.get("caption"), p.get("credit")])),
        }
        for p in chosen
        if p["id"] in rows
    ]


async def card(db: AsyncSession, row: NewsStory) -> dict:
    data = row.published_data or {}
    pictures = await images(db, row)
    cover_id = data.get("cover_image_id")
    cover = next((picture for picture in pictures if picture["id"] == cover_id), pictures[0] if pictures else None)
    video = await published_video(db, row)
    return {
        "slug": row.slug,
        "title": data["headline"],
        "summary": data["summary"],
        "company": "Cover Founder News",
        "industry": "Technology",
        "category": CATEGORY,
        "has_video": bool(video),
        "published_at": row.published_at,
        "duration_s": video.media["duration_s"] if video else None,
        "thumbnail_url": cover["url"] if cover else None,
    }


async def page(db: AsyncSession, row: NewsStory) -> dict:
    data = row.published_data or {}
    video = await published_video(db, row)
    return {
        **await card(db, row),
        "dateline": None,
        "sections": [{"heading": "", "paragraphs": [p.strip() for p in data["body"].split("\n\n") if p.strip()]}],
        "about": "",
        "pictures": await images(db, row),
        "video_url": registry.get_storage().presign_get(video.media["output_key"], 3600) if video else None,
        "disclosure": "AI-generated presenter · Cover Founder News" if video else "",
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


async def published_video(db: AsyncSession, row: NewsStory) -> NewsVideo | None:
    ident = (row.published_data or {}).get("_video_id")
    video = await db.get(NewsVideo, ident) if ident else None
    if video and video.story_id == row.id and video.status == "ready" and 0 < float(video.media.get("duration_s", 0)) <= 60 and video.media.get("output_key"):
        return video
    return None
