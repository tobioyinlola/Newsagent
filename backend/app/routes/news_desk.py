"""Editorial news desk, shared by all active back-office members. Video jobs are isolated from business generation."""

from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, HttpUrl
from sqlalchemy import select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import Principal, operator
from app.db import get_session
from app.integrations import registry
from app.integrations.llm.base import NewsDraft
from app.integrations.storage.base import ObjectTooLarge
from app.models import NewsImage, NewsStory, NewsVideo
from app.models.base import new_id, utcnow
from app.services import news_video, news_video_rules, uploads
from app.services.audit import audit
from app.services.ratelimit import limit

router = APIRouter(prefix="/v1/admin/news-desk", tags=["news-desk"])
CATEGORY = "CF Technology Breaking News"


class Picture(BaseModel):
    id: str = Field(pattern=r"^[a-f0-9]{32}$")
    caption: str = Field(default="", max_length=500)
    credit: str = Field(default="", max_length=300)


class DraftIn(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    revision: int = Field(ge=1)
    source_name: str = Field(default="", max_length=200)
    source_url: HttpUrl | None = None
    source_text: str = Field(default="", max_length=30000)
    headline: str = Field(default="", max_length=180)
    summary: str = Field(default="", max_length=500)
    body: str = Field(default="", max_length=20000)
    presenter_script: str = Field(default="", max_length=15000)
    scenes: list = Field(default_factory=list, max_length=20)
    cover_image_id: str | None = Field(default=None, pattern=r"^[a-f0-9]{32}$")
    pictures: list[Picture] = Field(default_factory=list, max_length=15)


class Revision(BaseModel):
    revision: int = Field(ge=1)


class Publish(Revision):
    editorial_confirmed: Literal[True]


class NewsUploadIn(BaseModel):
    filename: str = Field(min_length=1, max_length=200)
    content_type: Literal["image/png", "image/jpeg"]
    size_bytes: int = Field(gt=0, le=5 * 1024 * 1024)


class ConfirmIn(BaseModel):
    image_id: str = Field(pattern=r"^[a-f0-9]{32}$")


async def story(db: AsyncSession, id: str) -> NewsStory:
    row = await db.get(NewsStory, id)
    if row is None:
        raise HTTPException(404, "News draft not found")
    return row


async def images_valid(db: AsyncSession, id: str, data: dict):
    ids = [p["id"] for p in data.get("pictures", [])]
    if len(ids) != len(set(ids)):
        raise HTTPException(422, "Choose each image only once")
    scene_ids = [s["image_id"] for s in data.get("scenes", []) if s.get("image_id")]
    if not set(scene_ids).issubset(ids):
        raise HTTPException(422, "Scene pictures must be selected from this story's images")
    if data.get("cover_image_id") and data["cover_image_id"] not in ids:
        raise HTTPException(422, "The cover image must be one of this story’s selected and verified pictures")
    if ids:
        rows = list(
            (
                await db.execute(
                    select(NewsImage).where(
                        NewsImage.id.in_(ids), NewsImage.story_id == id, NewsImage.status == "clean"
                    )
                )
            ).scalars()
        )
        if len(rows) != len(ids):
            raise HTTPException(422, "One or more images have not been verified for this story")


async def out(db: AsyncSession, row: NewsStory):
    images = (
        await db.execute(
            select(NewsImage)
            .where(NewsImage.story_id == row.id, NewsImage.status == "clean")
            .order_by(NewsImage.created_at)
        )
    ).scalars()
    storage = registry.get_storage()
    video = (
        await db.execute(
            select(NewsVideo).where(NewsVideo.story_id == row.id).order_by(NewsVideo.story_revision.desc()).limit(1)
        )
    ).scalar_one_or_none()
    video_data = await news_video.video_out(video)
    if video_data and video:
        video_data["matches_draft"] = video.snapshot == row.data
    return {
        "id": row.id,
        "slug": row.slug,
        "status": row.status,
        "revision": row.revision,
        "data": row.data,
        "category": CATEGORY,
        "created_by": row.created_by,
        "updated_by": row.updated_by,
        "updated_at": row.updated_at,
        "published_at": row.published_at,
        "video_status": video.status if video else "not_started",
        "video_generation_enabled": True,
        "video": video_data,
        "limits": {
            "max_video_seconds": 60,
            "intro_seconds": 5,
            "outro_seconds": 6,
            "sting_seconds": 2,
            "presenter_seconds": 47,
            "article_min_words": 200,
            "article_max_words": 300,
            "script_min_words": 60,
            "script_max_words": 95,
        },
        "images": [{"id": i.id, "url": storage.presign_get(i.key, 900), "filename": i.filename} for i in images],
    }


async def change(db: AsyncSession, id: str, revision: int, **values) -> NewsStory:
    row = (
        await db.execute(
            update(NewsStory)
            .where(NewsStory.id == id, NewsStory.revision == revision)
            .values(**values, revision=NewsStory.revision + 1, updated_at=utcnow())
            .returning(NewsStory)
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()
    if row is None:
        raise HTTPException(409, "This draft changed in another tab. Refresh before saving or publishing.")
    return row


@router.get("")
async def listing(_: Principal = Depends(operator), db: AsyncSession = Depends(get_session)):
    rows = (await db.execute(select(NewsStory).order_by(NewsStory.updated_at.desc()))).scalars()
    return [
        {
            "id": r.id,
            "headline": r.data.get("headline") or "Untitled news draft",
            "status": r.status,
            "updated_at": r.updated_at,
            "updated_by": r.updated_by,
        }
        for r in rows
    ]


@router.post("")
async def create(p: Principal = Depends(operator), db: AsyncSession = Depends(get_session)):
    id = new_id()
    row = NewsStory(
        id=id,
        slug=f"cf-tech-{id}",
        data=DraftIn(revision=1).model_dump(mode="json", exclude={"revision"}),
        created_by=p.user.email,
        updated_by=p.user.email,
    )
    db.add(row)
    audit(db, p.user.email, "news.created", target_type="news_story", target_id=id)
    await db.commit()
    return await out(db, row)


@router.get("/{id}")
async def detail(id: str, _: Principal = Depends(operator), db: AsyncSession = Depends(get_session)):
    return await out(db, await story(db, id))


@router.put("/{id}")
async def save(id: str, body: DraftIn, p: Principal = Depends(operator), db: AsyncSession = Depends(get_session)):
    await story(db, id)
    # Typed scene validation also applies to manually edited drafts.
    from app.integrations.llm.base import NewsScene

    try:
        scenes = [NewsScene.model_validate(s).model_dump() for s in body.scenes]
    except ValueError:
        raise HTTPException(422, "Check the narration, duration and motion for each image scene") from None
    data = body.model_dump(mode="json", exclude={"revision"})
    data["scenes"] = scenes
    await images_valid(db, id, data)
    row = await change(db, id, body.revision, data=data, updated_by=p.user.email)
    audit(db, p.user.email, "news.saved", target_type="news_story", target_id=id)
    await db.commit()
    return await out(db, row)


@router.post("/{id}/rewrite", dependencies=[Depends(limit("news-rewrite", 20, 3600))])
async def rewrite(id: str, body: Revision, p: Principal = Depends(operator), db: AsyncSession = Depends(get_session)):
    row = await story(db, id)
    data = dict(row.data)
    if row.revision != body.revision:
        raise HTTPException(409, "Refresh the changed draft before rewriting")
    if len(data.get("source_text", "").strip()) < 80 or not data.get("source_name"):
        raise HTTPException(422, "Add the source publisher and at least 80 characters of source text, then save")
    await db.commit()  # Do not hold a database transaction while waiting for the writer.
    try:
        draft = await registry.get_llm().write_news(data["source_text"], data["source_name"])
        rewritten = draft.model_dump()
        news_video_rules.validate_copy(rewritten)
        data.update(rewritten)
    except Exception:
        raise HTTPException(
            502, "We couldn't rewrite this story right now. Your saved draft is safe; please retry."
        ) from None
    row = await change(db, id, body.revision, data=data, updated_by=p.user.email)
    audit(db, p.user.email, "news.rewritten", target_type="news_story", target_id=id)
    await db.commit()
    return await out(db, row)


@router.post("/{id}/publish")
async def publish(id: str, body: Publish, p: Principal = Depends(operator), db: AsyncSession = Depends(get_session)):
    row = await story(db, id)
    data = dict(row.data)
    if row.revision != body.revision:
        raise HTTPException(409, "Refresh and review the current draft before publishing")
    if not data.get("source_name") or not data.get("source_url"):
        raise HTTPException(422, "Add the source publisher and original article URL before publishing")
    try:
        NewsDraft.model_validate(data)
    except ValueError:
        raise HTTPException(
            422, "Add a headline, summary, written story and presenter script before publishing"
        ) from None
    await images_valid(db, id, data)
    try:
        news_video_rules.validate_copy(data)
    except ValueError as error:
        raise HTTPException(422, str(error)) from None
    latest = (
        await db.execute(
            select(NewsVideo).where(NewsVideo.story_id == id).order_by(NewsVideo.story_revision.desc()).limit(1)
        )
    ).scalar_one_or_none()
    if latest and latest.snapshot == row.data and latest.status in {"queued", "running"}:
        raise HTTPException(409, "Wait for this version’s video to finish before publishing it")
    video = latest if latest and latest.status == "ready" and latest.snapshot == row.data else None
    if video:
        data["_video_id"] = video.id
    await db.commit()
    try:
        moderation = await registry.get_llm().moderate(
            "\n".join(str(data.get(k, "")) for k in ["headline", "summary", "body", "presenter_script"])
        )
    except Exception:
        raise HTTPException(503, "The publication check is unavailable. Your draft has not been published.") from None
    if moderation.get("level") not in {"allow", "review"}:
        raise HTTPException(422, "This story cannot be published. Review its content before trying again.")
    # The explicit editor confirmation covers human review, including a 'review' moderation result.
    row = await change(
        db, id, body.revision, status="published", published_data=data, published_at=utcnow(), updated_by=p.user.email
    )
    audit(
        db,
        p.user.email,
        "news.published",
        target_type="news_story",
        target_id=id,
        detail={"moderation": moderation, "editorial_confirmed": True},
    )
    await db.commit()
    return await out(db, row)


@router.post("/{id}/unpublish")
async def unpublish(id: str, body: Revision, p: Principal = Depends(operator), db: AsyncSession = Depends(get_session)):
    await story(db, id)
    row = await change(
        db, id, body.revision, status="draft", published_data=None, published_at=None, updated_by=p.user.email
    )
    audit(db, p.user.email, "news.unpublished", target_type="news_story", target_id=id)
    await db.commit()
    return await out(db, row)


@router.post("/{id}/generate-video")
async def generate_video(
    id: str, body: Revision, p: Principal = Depends(operator), db: AsyncSession = Depends(get_session)
):
    row = await story(db, id)
    if row.revision != body.revision:
        raise HTTPException(409, "Save and reload the current draft before generating its video")
    data = dict(row.data)
    try:
        NewsDraft.model_validate(data)
        news_video_rules.validate_copy(data)
    except ValueError as error:
        raise HTTPException(422, str(error)) from None
    if not data.get("source_name") or not data.get("source_url"):
        raise HTTPException(422, "Add the original source publisher and article URL before generating")
    if not data.get("pictures") or not data.get("cover_image_id"):
        raise HTTPException(422, "Select a cover image and at least one verified story picture before generating")
    await images_valid(db, id, data)
    await db.commit()
    try:
        verdict = await registry.get_llm().moderate(
            "\n".join(data[k] for k in ["headline", "body", "presenter_script"])
        )
    except Exception:
        raise HTTPException(503, "The content check is unavailable. No video job was started.") from None
    if verdict.get("level") != "allow":
        raise HTTPException(422, "Review and edit this content before generating its video")
    # Serialize against draft edits as well as double clicks; immutable jobs are unique per revision.
    row = (
        await db.execute(
            select(NewsStory).where(NewsStory.id == id).with_for_update().execution_options(populate_existing=True)
        )
    ).scalar_one()
    if row.revision != body.revision:
        raise HTTPException(409, "The draft changed during the content check. Review it and try again.")
    video = (
        await db.execute(select(NewsVideo).where(NewsVideo.story_id == id, NewsVideo.story_revision == body.revision))
    ).scalar_one_or_none()
    if video is None:
        previous = (
            await db.execute(
                select(NewsVideo).where(NewsVideo.story_id == id).order_by(NewsVideo.story_revision.desc()).limit(1)
            )
        ).scalar_one_or_none()
        if previous and previous.snapshot == data:
            video = previous
    if video is None:
        video = NewsVideo(story_id=id, story_revision=body.revision, snapshot=data)
        db.add(video)
        try:
            await db.flush()
        except IntegrityError:
            await db.rollback()
            row = await story(db, id)
            video = (
                await db.execute(
                    select(NewsVideo).where(NewsVideo.story_id == id, NewsVideo.story_revision == body.revision)
                )
            ).scalar_one()
    elif video.status == "failed":
        video.status, video.error = "queued", ""
    audit(
        db,
        p.user.email,
        "news.video_requested",
        target_type="news_story",
        target_id=id,
        detail={"revision": body.revision, "video_id": video.id},
    )
    await db.commit()
    if video.status == "queued":
        news_video.enqueue(video.id)
    return await out(db, row)


@router.post("/{id}/images")
async def upload_image(
    id: str, body: NewsUploadIn, _: Principal = Depends(operator), db: AsyncSession = Depends(get_session)
):
    await story(db, id)
    image_id = new_id()
    key = f"news-desk/{id}/{image_id}/upload.{'png' if body.content_type == 'image/png' else 'jpg'}"
    db.add(
        NewsImage(
            id=image_id,
            story_id=id,
            key=key,
            filename=body.filename,
            content_type=body.content_type,
            size_bytes=body.size_bytes,
        )
    )
    await db.commit()
    return {"image_id": image_id, "upload_url": registry.get_storage().presign_put(key, 600)}


@router.post("/{id}/images/confirm")
async def confirm_image(
    id: str, body: ConfirmIn, p: Principal = Depends(operator), db: AsyncSession = Depends(get_session)
):
    await story(db, id)
    image = (
        await db.execute(
            update(NewsImage)
            .where(NewsImage.id == body.image_id, NewsImage.story_id == id)
            .values(status=NewsImage.status)
            .returning(NewsImage)
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()
    if image is None or image.status == "rejected":
        raise HTTPException(404, "Image not found")
    if image.status == "clean":
        return {"id": image.id}
    storage = registry.get_storage()
    try:
        content = await storage.get(image.key, 5 * 1024 * 1024)
        if len(content) != image.size_bytes:
            raise uploads.InvalidUpload("File size does not match the declared upload")
        uploads.validate_content(image.content_type, content)
    except (ObjectTooLarge, uploads.InvalidUpload) as error:
        image.status = "rejected"
        await storage.delete(image.key)
        await db.commit()
        raise HTTPException(422, str(error)) from None
    except Exception:
        raise HTTPException(422, "Image upload was not received. Please upload it again.") from None
    try:
        scan = await registry.get_scanner().scan(content)
    except Exception:
        raise HTTPException(503, "We couldn't scan this image. Please retry.") from None
    if not scan.clean:
        image.status = "rejected"
        await storage.delete(image.key)
        await db.commit()
        raise HTTPException(422, "This image was blocked by the security scan")
    original = image.key
    verified = original.replace("/upload.", "/verified.")
    await storage.put(verified, content, image.content_type)
    image.key, image.status = verified, "clean"
    audit(db, p.user.email, "news.image_uploaded", target_type="news_story", target_id=id)
    await db.commit()
    await storage.delete(original)
    return {"id": image.id}
