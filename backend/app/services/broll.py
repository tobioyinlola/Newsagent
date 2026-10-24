"""Product footage in interview videos: the owner's own images and clips, plus optional AI-generated shots that are always
labelled as synthetic. The owner chooses; nothing is added to a video on its own."""

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations import registry
from app.models import Asset, BrandAsset, Project

MAX_ITEMS = 5
IMAGE_SECONDS = (3.0, 8.0)
VIDEO_SECONDS = (2.0, 8.0)  # a clip plays from its start for at most this long
GENERATED_TYPE = "broll_generated"


async def candidates(session: AsyncSession, project: Project, *, with_urls: bool = True) -> list[dict]:
    """Everything the owner may put in this video: their clean product images and videos, and clips generated for it."""
    storage = registry.get_storage()
    out: list[dict] = []
    rows = (
        (
            await session.execute(
                select(BrandAsset)
                .where(
                    BrandAsset.workspace_id == project.workspace_id,
                    BrandAsset.status == "clean",
                    BrandAsset.kind.in_(["product_image", "product_video"]),
                )
                .order_by(BrandAsset.created_at)
            )
        )
        .scalars()
        .all()
    )
    for a in rows:
        out.append(
            {
                "key": a.key,
                "kind": "video" if a.kind == "product_video" else "image",
                "source": "upload",
                "synthetic": False,
                "duration_s": a.duration_s,
                "url": storage.presign_get(a.key, 900) if with_urls else None,
            }
        )
    gen = (
        (
            await session.execute(
                select(Asset)
                .where(Asset.project_id == project.id, Asset.type == GENERATED_TYPE)
                .order_by(Asset.created_at)
            )
        )
        .scalars()
        .all()
    )
    for g in gen:
        out.append(
            {
                "key": g.storage_key,
                "kind": "video",
                "source": "generated",
                "synthetic": True,
                "duration_s": float(g.duration or 0),
                "url": storage.presign_get(g.storage_key, 900) if with_urls else None,
            }
        )
    return out


def normalise(items: list[dict], cands: list[dict]) -> list[dict]:
    """Check the owner's choices against what they may use and clamp each to what the renderer can show."""
    by_key = {c["key"]: c for c in cands}
    if len(items) > MAX_ITEMS:
        raise ValueError(f"Choose at most {MAX_ITEMS} pieces of product footage.")
    out: list[dict] = []
    for it in items:
        c = by_key.get(it["key"])
        if c is None:
            raise ValueError("That file isn't one of your product images or videos.")
        lo, hi = IMAGE_SECONDS if c["kind"] == "image" else VIDEO_SECONDS
        if c["kind"] == "video" and c["duration_s"]:
            hi = min(hi, float(c["duration_s"]))
        seconds = float(it["seconds"])
        if not lo <= seconds <= max(lo, hi):
            raise ValueError(f"Show each {c['kind']} for {lo:g} to {max(lo, hi):g} seconds.")
        out.append(
            {
                "key": c["key"],
                "kind": c["kind"],
                "caption": (it.get("caption") or "").strip()[:80],
                "seconds": seconds,
                "synthetic": c["synthetic"],
            }
        )
    return out
