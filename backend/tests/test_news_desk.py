import base64

import pytest
from sqlalchemy import select

from app.integrations import registry
from app.models import Job, NewsImage, StaffMember, User
from tests.conftest import OPS, OWNER
from tests.helpers import api_path

SOURCE = "A technology company has announced a new service for small businesses in Lagos. The service helps teams manage customer appointments and will be available next month. The company says it plans to add more cities later."
PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)
BASE = "/v1/admin/news-desk"


async def ready(client):
    r = await client.post(BASE, headers=OPS)
    assert r.status_code == 200, r.text
    row = r.json()
    r = await client.put(
        f"{BASE}/{row['id']}",
        headers=OPS,
        json={
            **row["data"],
            "revision": row["revision"],
            "source_name": "Example Technology",
            "source_url": "https://example.com/story",
            "source_text": SOURCE,
        },
    )
    assert r.status_code == 200, r.text
    row = r.json()
    r = await client.post(f"{BASE}/{row['id']}/rewrite", headers=OPS, json={"revision": row["revision"]})
    assert r.status_code == 200, r.text
    return r.json()


async def publish(client, row):
    return await client.post(
        f"{BASE}/{row['id']}/publish", headers=OPS, json={"revision": row["revision"], "editorial_confirmed": True}
    )


async def test_news_rewrite_review_publish_snapshot_unpublish_without_video_jobs(client, workspace, maker):
    row = await ready(client)
    assert row["data"]["presenter_script"] and row["data"]["scenes"]
    assert row["video_generation_enabled"] is False and row["video_status"] == "on_hold"
    assert (await client.get(f"/v1/public/stories/{row['slug']}")).status_code == 404
    assert (await client.post(f"{BASE}/{row['id']}/generate-video", headers=OPS)).status_code == 409
    r = await publish(client, row)
    assert r.status_code == 200, r.text
    row = r.json()
    page = (await client.get(f"/v1/public/stories/{row['slug']}")).json()
    assert page["category"] == "CF Technology Breaking News"
    assert page["company"] == "Cover Founder News" and page["has_video"] is False
    assert page["video_url"] is None and page["source_url"] == "https://example.com/story"
    assert "source_text" not in page and "presenter_script" not in page
    assert (await client.get("/v1/public/stories")).json()[0]["slug"] == row["slug"]
    assert (await client.get(f"/v1/public/stories/{row['slug']}/preview")).status_code == 200
    # Unpublished editor changes never alter the live snapshot.
    edited = await client.put(
        f"{BASE}/{row['id']}",
        headers=OPS,
        json={**row["data"], "revision": row["revision"], "headline": "An edited headline for the next version"},
    )
    assert edited.status_code == 200, edited.text
    assert (await client.get(f"/v1/public/stories/{row['slug']}")).json()["title"] == page["title"]
    row = edited.json()
    r = await client.post(f"{BASE}/{row['id']}/unpublish", headers=OPS, json={"revision": row["revision"]})
    assert r.status_code == 200
    assert (await client.get(f"/v1/public/stories/{row['slug']}")).status_code == 404
    assert (await client.get("/v1/public/stories")).json() == []
    async with maker() as db:
        assert not list((await db.execute(select(Job))).scalars())


async def test_all_active_admin_roles_can_use_news_desk_customers_cannot(client, workspace, maker):
    assert (await client.post(BASE, headers=OWNER)).status_code == 403
    assert (await client.get(BASE)).status_code == 401
    async with maker() as db:
        db.add(User(email="editor@example.com", workspace_id=workspace))
        db.add(
            StaffMember(
                email="editor@example.com",
                role="viewer",
                permissions=["overview.view"],
                status="active",
                workspace_id=workspace,
                invited_by="ops@example.com",
            )
        )
        await db.commit()
    headers = {"Authorization": "Bearer dev:editor@example.com"}
    assert (await client.post(BASE, headers=headers)).status_code == 200
    async with maker() as db:
        staff = (await db.execute(select(StaffMember).where(StaffMember.email == "editor@example.com"))).scalar_one()
        staff.status = "suspended"
        await db.commit()
    assert (await client.get(BASE, headers=headers)).status_code == 403


async def test_conflicting_edits_invalid_source_and_editor_confirmation(client, workspace):
    row = await ready(client)
    stale = await client.put(f"{BASE}/{row['id']}", headers=OPS, json={**row["data"], "revision": 1})
    assert stale.status_code == 409
    assert (
        await client.post(
            f"{BASE}/{row['id']}/publish", headers=OPS, json={"revision": row["revision"], "editorial_confirmed": False}
        )
    ).status_code == 422
    invalid = await client.put(
        f"{BASE}/{row['id']}",
        headers=OPS,
        json={**row["data"], "revision": row["revision"], "source_url": "javascript:alert(1)"},
    )
    assert invalid.status_code == 422
    r = await client.put(
        f"{BASE}/{row['id']}", headers=OPS, json={**row["data"], "revision": row["revision"], "source_url": None}
    )
    assert r.status_code == 200
    assert (await publish(client, r.json())).status_code == 422


async def test_moderation_and_writer_failures_leave_draft_safe(client, workspace, monkeypatch):
    row = await ready(client)
    llm = registry.get_llm()

    async def fail(*args):
        raise RuntimeError("provider failure")

    monkeypatch.setattr(llm, "write_news", fail)
    assert (
        await client.post(f"{BASE}/{row['id']}/rewrite", headers=OPS, json={"revision": row["revision"]})
    ).status_code == 502
    saved = (await client.get(f"{BASE}/{row['id']}", headers=OPS)).json()
    assert saved["data"] == row["data"] and saved["revision"] == row["revision"]
    monkeypatch.setattr(llm, "moderate", fail)
    assert (await publish(client, row)).status_code == 503

    async def block(*args):
        return {"level": "block", "reasons": ["unsafe"]}

    monkeypatch.setattr(llm, "moderate", block)
    assert (await publish(client, row)).status_code == 422
    assert (await client.get(f"/v1/public/stories/{row['slug']}")).status_code == 404


async def test_news_images_are_verified_immutable_scoped_and_published_with_captions(client, workspace, maker):
    row = await ready(client)
    id = row["id"]
    signed = (
        await client.post(
            f"{BASE}/{id}/images",
            headers=OPS,
            json={"filename": "cover.png", "content_type": "image/png", "size_bytes": len(PNG)},
        )
    ).json()
    assert (await client.put(api_path(signed["upload_url"]), content=PNG)).status_code == 200
    r = await client.post(f"{BASE}/{id}/images/confirm", headers=OPS, json={"image_id": signed["image_id"]})
    assert r.status_code == 200, r.text
    # Overwriting the original signed upload cannot mutate verified published bytes.
    await client.put(api_path(signed["upload_url"]), content=b"not the verified file")
    async with maker() as db:
        image = await db.get(NewsImage, signed["image_id"])
        assert await registry.get_storage().get(image.key, 10000) == PNG
    data = {
        **row["data"],
        "pictures": [{"id": signed["image_id"], "caption": "The new service", "credit": "Example photographer"}],
    }
    data["scenes"][0]["image_id"] = signed["image_id"]
    r = await client.put(f"{BASE}/{id}", headers=OPS, json={**data, "revision": row["revision"]})
    assert r.status_code == 200, r.text
    row = r.json()
    other = (await client.post(BASE, headers=OPS)).json()
    assert (
        await client.put(f"{BASE}/{other['id']}", headers=OPS, json={**data, "revision": other["revision"]})
    ).status_code == 422
    assert (await publish(client, row)).status_code == 200
    page = (await client.get(f"/v1/public/stories/{row['slug']}")).json()
    assert page["thumbnail_url"] and page["pictures"][0]["caption"] == "The new service · Example photographer"
    assert (await client.get(f"/v1/public/stories/{row['slug']}/image", follow_redirects=False)).status_code == 302


@pytest.mark.parametrize("content_type,content", [("image/png", b"not an image"), ("image/jpeg", b"also invalid")])
async def test_news_rejects_invalid_image_bytes(client, workspace, content_type, content):
    row = await ready(client)
    signed = (
        await client.post(
            f"{BASE}/{row['id']}/images",
            headers=OPS,
            json={"filename": "bad.png", "content_type": content_type, "size_bytes": len(content)},
        )
    ).json()
    await client.put(api_path(signed["upload_url"]), content=content)
    assert (
        await client.post(f"{BASE}/{row['id']}/images/confirm", headers=OPS, json={"image_id": signed["image_id"]})
    ).status_code == 422
