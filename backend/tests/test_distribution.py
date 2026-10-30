import asyncio
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.integrations import registry
from app.models import BrandAsset, CreditTransaction, Project, ScriptVersion, User, Workspace
from app.routes import distribution as routes
from app.services import distribution as emails
from app.services import ledger
from tests.conftest import OPS, OWNER


@pytest.fixture
async def distribution_data(maker, workspace):
    async with maker() as db:
        project = Project(workspace_id=workspace, state="final_ready")
        db.add(project)
        await db.flush()
        db.add(
            ScriptVersion(
                project_id=project.id,
                story={
                    "headline": "Acme launches",
                    "dek": "The announcement",
                    "sections": [{"heading": "News", "paragraphs": ["A new product."]}],
                },
            )
        )
        db.add(
            BrandAsset(
                workspace_id=workspace,
                key="brand/logo.png",
                kind="product_image",
                content_type="image/png",
                size_bytes=100,
                status="clean",
            )
        )
        await db.commit()
        return {
            "stage": "review",
            "outlet_ids": ["1", "2"],
            "project_id": project.id,
            "headline": "Our custom headline",
            "announcement": "Our edited announcement.",
            "contact_name": "Ada",
            "contact_email": "ada@example.com",
            "phone": "+2348012345678",
            "whatsapp": "+2348012345678",
            "logo_key": "brand/logo.png",
            "picture_keys": [],
        }


async def draft(client, data):
    r = await client.post("/v1/distribution", headers=OWNER)
    assert r.status_code == 200, r.text
    id = r.json()["id"]
    saved = await client.put(f"/v1/distribution/{id}", headers=OWNER, json=data)
    assert saved.status_code == 200, saved.text
    return id


async def test_catalog_draft_video_and_admin_progress(client, distribution_data):
    catalog = (await client.get("/v1/distribution/outlets", headers=OWNER)).json()
    assert len(catalog["outlets"]) == 47
    assert all(o["credits"] == "0" for o in catalog["outlets"])
    assert sum(o["name"] == "Premium Times" for o in catalog["outlets"]) == 1
    assert catalog["coming_soon"] == ["United States", "Canada", "United Kingdom"]
    videos = (await client.get("/v1/distribution/videos", headers=OWNER)).json()
    assert videos[0]["headline"] == "Acme launches"
    assert "A new product." in videos[0]["announcement"]
    id = await draft(client, {**distribution_data, "stage": "contact"})
    rows = (await client.get("/v1/admin/distribution", headers=OPS)).json()
    assert rows[0]["id"] == id and rows[0]["stage"] == "contact"
    assert not rows[0]["paid"]
    assert rows[0]["data"]["outlets"][0]["name"] == "Empire Magazine Africa"
    resumed = (await client.get(f"/v1/distribution/{id}", headers=OWNER)).json()
    assert resumed["data"]["announcement"] == "Our edited announcement."


async def test_free_submit_email_immutable_and_duplicate(client, distribution_data, maker):
    id = await draft(client, distribution_data)
    result = await client.post(f"/v1/distribution/{id}/submit", headers=OWNER)
    assert result.status_code == 200, result.text
    row = result.json()
    assert row["paid"] and row["status"] == "submitted" and row["email_sent"]
    assert Decimal(row["total_credits"]) == 0
    assert "24 hours" in registry.get_email().sent[-1]["text"]
    assert len(registry.get_email().sent) == 2
    again = await client.post(f"/v1/distribution/{id}/submit", headers=OWNER)
    assert again.status_code == 200 and again.json()["paid"]
    assert len(registry.get_email().sent) == 2
    assert (await client.put(f"/v1/distribution/{id}", headers=OWNER, json=distribution_data)).status_code == 409
    async with maker() as db:
        assert (
            not (await db.execute(select(CreditTransaction).where(CreditTransaction.ref == f"distribution:{id}")))
            .scalars()
            .all()
        )


async def test_paid_submit_once_and_ledger_balance(client, distribution_data, maker, workspace, monkeypatch):
    monkeypatch.setitem(routes.OUTLETS["1"], "credits", "3")
    monkeypatch.setitem(routes.OUTLETS["2"], "credits", "2")
    id = await draft(client, distribution_data)
    # Concurrent delivery from a double-click or a retry must debit just once.
    results = await asyncio.gather(*[client.post(f"/v1/distribution/{id}/submit", headers=OWNER) for _ in range(2)])
    assert all(r.status_code == 200 for r in results), [r.text for r in results]
    async with maker() as db:
        ws = await db.get(Workspace, workspace)
        assert ws.credit_balance == Decimal("5")
        txs = (
            (await db.execute(select(CreditTransaction).where(CreditTransaction.ref == f"distribution:{id}")))
            .scalars()
            .all()
        )
        assert len(txs) == 1 and txs[0].amount == Decimal("-5")
        assert await ledger.ledger_sum(db, workspace) == ws.credit_balance


async def test_insufficient_credit_saved_draft_and_retry(client, distribution_data, maker, workspace, monkeypatch):
    monkeypatch.setitem(routes.OUTLETS["1"], "credits", "12")
    id = await draft(client, distribution_data)
    r = await client.post(f"/v1/distribution/{id}/submit", headers=OWNER)
    assert r.status_code == 402
    saved = (await client.get(f"/v1/distribution/{id}", headers=OWNER)).json()
    assert (
        saved["stage"] == "review" and not saved["paid"] and saved["data"]["headline"] == distribution_data["headline"]
    )
    async with maker() as db:
        ws = await db.get(Workspace, workspace)
        assert ws.credit_balance == Decimal("10")
        await ledger.apply(db, ws, Decimal("5"), "grant")
        await db.commit()
    assert (await client.post(f"/v1/distribution/{id}/submit", headers=OWNER)).status_code == 200


@pytest.mark.parametrize(
    "change",
    [
        {"outlet_ids": ["unknown"]},
        {"outlet_ids": ["1", "1"]},
        {"project_id": "foreign"},
        {"logo_key": "unverified.png"},
    ],
)
async def test_rejects_invalid_or_foreign_content(client, distribution_data, change):
    r = await client.post("/v1/distribution", headers=OWNER)
    id = r.json()["id"]
    assert (
        await client.put(f"/v1/distribution/{id}", headers=OWNER, json={**distribution_data, **change})
    ).status_code == 422


@pytest.mark.parametrize("field", ["contact_email", "phone", "logo_key", "announcement", "project_id", "outlet_ids"])
async def test_incomplete_submission_rolls_back(client, distribution_data, field):
    data = {**distribution_data, field: [] if field == "outlet_ids" else None if field == "project_id" else ""}
    id = await draft(client, data)
    assert (await client.post(f"/v1/distribution/{id}/submit", headers=OWNER)).status_code == 422
    row = (await client.get(f"/v1/distribution/{id}", headers=OWNER)).json()
    assert row["status"] == "draft" and not row["paid"]


async def test_workspace_isolation_and_admin_permissions(client, distribution_data, maker):
    id = await draft(client, distribution_data)
    async with maker() as db:
        ws = Workspace(name="Other")
        db.add(ws)
        await db.flush()
        db.add(User(email="other@example.com", workspace_id=ws.id))
        await db.commit()
    other = {"Authorization": "Bearer dev:other@example.com"}
    for method, path in [("GET", f"/v1/distribution/{id}"), ("POST", f"/v1/distribution/{id}/submit")]:
        assert (await client.request(method, path, headers=other)).status_code == 404
    assert (await client.get("/v1/distribution", headers=other)).json() == []
    assert (await client.get("/v1/admin/distribution", headers=OWNER)).status_code == 403
    assert (await client.get(f"/v1/admin/distribution/{id}/assets", headers=OWNER)).status_code == 403
    assert (
        await client.patch(f"/v1/admin/distribution/{id}", headers=OPS, json={"status": "completed"})
    ).status_code == 409
    await client.post(f"/v1/distribution/{id}/submit", headers=OWNER)
    assert (await client.patch(f"/v1/admin/distribution/{id}", headers=OPS, json={"status": "in_progress"})).json()[
        "status"
    ] == "in_progress"


async def test_email_failure_keeps_submission_and_retries(client, distribution_data, monkeypatch):
    original = emails.send_email

    async def failure(*args, **kwargs):
        return False

    monkeypatch.setattr(emails, "send_email", failure)
    id = await draft(client, distribution_data)
    r = (await client.post(f"/v1/distribution/{id}/submit", headers=OWNER)).json()
    assert r["paid"] and not r["email_sent"]
    monkeypatch.setattr(emails, "send_email", original)
    assert await emails.retry_confirmations() == 1
    assert await emails.retry_confirmations() == 0
    assert (await client.get(f"/v1/distribution/{id}", headers=OWNER)).json()["email_sent"]


async def test_changed_price_requires_review(client, distribution_data, monkeypatch):
    id = await draft(client, distribution_data)
    monkeypatch.setitem(routes.OUTLETS["1"], "credits", "2")
    r = await client.post(f"/v1/distribution/{id}/submit", headers=OWNER)
    assert r.status_code == 409
    row = (await client.get(f"/v1/distribution/{id}", headers=OWNER)).json()
    assert Decimal(row["total_credits"]) == 2 and not row["paid"]


async def test_platform_story_selection_and_edited_copy(client, distribution_data, maker):
    stories = (await client.get("/v1/distribution/stories", headers=OWNER)).json()
    assert stories[0]["project_id"] == distribution_data["project_id"]
    assert stories[0]["headline"] == "Acme launches"
    assert "A new product." in stories[0]["announcement"]
    async with maker() as db:
        db.add(
            ScriptVersion(
                project_id=distribution_data["project_id"],
                version=2,
                story={
                    "headline": "Updated announcement",
                    "sections": [{"heading": "Launch", "paragraphs": ["Our latest details."]}],
                },
            )
        )
        await db.commit()
    latest = (await client.get("/v1/distribution/stories", headers=OWNER)).json()
    assert len(latest) == 1 and latest[0]["headline"] == "Updated announcement"
    data = {
        **distribution_data,
        "announcement_source": "platform",
        "story_project_id": latest[0]["project_id"],
        "headline": latest[0]["headline"],
        "announcement": "An edited version of our platform story.",
    }
    id = await draft(client, data)
    result = await client.post(f"/v1/distribution/{id}/submit", headers=OWNER)
    assert result.status_code == 200, result.text
    assert result.json()["data"]["story_project_id"] == latest[0]["project_id"]
    assert result.json()["data"]["announcement"] == data["announcement"]


async def test_story_selection_draft_can_be_incomplete_but_not_submitted(client, distribution_data):
    id = await draft(client, {**distribution_data, "announcement_source": "platform", "story_project_id": None})
    assert (await client.post(f"/v1/distribution/{id}/submit", headers=OWNER)).status_code == 422
    assert (await client.get(f"/v1/distribution/{id}", headers=OWNER)).json()["status"] == "draft"


async def test_platform_stories_are_private_to_workspace(client, distribution_data, maker):
    async with maker() as db:
        ws = Workspace(name="Other story workspace")
        db.add(ws)
        await db.flush()
        db.add(User(email="story-other@example.com", workspace_id=ws.id))
        await db.commit()
    other = {"Authorization": "Bearer dev:story-other@example.com"}
    assert (await client.get("/v1/distribution/stories", headers=other)).json() == []
    created = (await client.post("/v1/distribution", headers=other)).json()
    result = await client.put(
        f"/v1/distribution/{created['id']}",
        headers=other,
        json={"announcement_source": "platform", "story_project_id": distribution_data["project_id"]},
    )
    assert result.status_code == 422


async def test_contact_country_choices_survive_draft_reload(client, distribution_data):
    data = {**distribution_data, "phone_country": "NG", "whatsapp_country": "CA", "whatsapp": "+19058052110"}
    id = await draft(client, data)
    row = (await client.get(f"/v1/distribution/{id}", headers=OWNER)).json()
    assert row["data"]["phone_country"] == "NG"
    assert row["data"]["whatsapp_country"] == "CA"
    assert row["data"]["whatsapp"] == "+19058052110"


@pytest.mark.parametrize("field", ["phone", "whatsapp"])
@pytest.mark.parametrize("value", ["08031234567", "2348031234567", "+01234567890", "+2348031234567890"])
async def test_submission_requires_international_phone_format(client, distribution_data, field, value):
    id = await draft(client, {**distribution_data, field: value})
    response = await client.post(f"/v1/distribution/{id}/submit", headers=OWNER)
    assert response.status_code == 422
    row = (await client.get(f"/v1/distribution/{id}", headers=OWNER)).json()
    assert row["status"] == "draft" and not row["paid"]
