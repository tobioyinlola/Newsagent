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
async def distribution_data(maker, workspace, monkeypatch):
    # Workflow tests exercise a deliberately free catalog; price-specific tests set their own costs.
    for outlet in routes.OUTLETS.values():
        monkeypatch.setitem(outlet, "credits", "0")
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
    assert len(catalog["outlets"]) == 53
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
    assert row["paid"] and row["status"] == "submitted"
    assert (await client.get(f"/v1/distribution/{id}", headers=OWNER)).json()["email_sent"]
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


@pytest.mark.parametrize("field", ["phone"])
@pytest.mark.parametrize("value", ["08031234567", "2348031234567", "+01234567890", "+2348031234567890"])
async def test_submission_requires_international_phone_format(client, distribution_data, field, value):
    id = await draft(client, {**distribution_data, field: value})
    response = await client.post(f"/v1/distribution/{id}/submit", headers=OWNER)
    assert response.status_code == 422
    row = (await client.get(f"/v1/distribution/{id}", headers=OWNER)).json()
    assert row["status"] == "draft" and not row["paid"]


async def configure_outlet(client, outlet_id, **values):
    configuration = (await client.get("/v1/admin/distribution/config", headers=OPS)).json()
    outlet = next(x for x in configuration["outlets"] if x["id"] == outlet_id)
    response = await client.put(f"/v1/admin/distribution/outlets/{outlet_id}", headers=OPS, json={**outlet, **values})
    assert response.status_code == 200, response.text
    return response.json()


async def paid_details(client, distribution_data):
    id = await draft(client, distribution_data)
    response = await client.post(f"/v1/distribution/{id}/submit", headers=OWNER)
    assert response.status_code == 200, response.text
    return id, (await client.get(f"/v1/admin/distribution/{id}", headers=OPS)).json()


async def test_configured_team_publisher_emails_and_media_receipt(client, distribution_data, maker, workspace):
    from app.models import Asset

    await client.put(
        "/v1/admin/distribution/config",
        headers=OPS,
        json={"team_emails": ["sales@example.com", "ops@example.com", "SALES@example.com"]},
    )
    await configure_outlet(
        client,
        "1",
        credits="2",
        logo_credits="1",
        picture_credits="0.5",
        direct_access=True,
        contact_name="Ada Editor",
        contact_email="publisher@example.com",
    )
    await configure_outlet(
        client,
        "2",
        credits="3",
        accepts_logo=False,
        accepts_images=False,
        direct_access=True,
        contact_email="publisher2@example.com",
    )
    async with maker() as db:
        for key in ["brand/one.png", "brand/two.png"]:
            db.add(
                BrandAsset(
                    workspace_id=workspace,
                    key=key,
                    kind="product_image",
                    content_type="image/png",
                    size_bytes=100,
                    status="clean",
                )
            )
        db.add(
            Asset(
                project_id=distribution_data["project_id"], type="render", storage_key="video/test.mp4", format="16x9"
            )
        )
        await db.commit()
    data = {**distribution_data, "picture_keys": ["brand/one.png", "brand/two.png"]}
    id, admin = await paid_details(client, data)
    assert Decimal(admin["total_credits"]) == 7
    assert len(admin["placements"]) == 2 and len(admin["emails"]) == 6
    assert all(m["status"] == "sent" for m in admin["emails"])
    publisher = next(m for m in admin["emails"] if m["recipient"] == "publisher@example.com")
    assert "sponsorship request" in publisher["body"] and "bank/payment details" in publisher["body"]
    assert "brand/logo.png" in publisher["body"] and "brand/one.png" in publisher["body"]
    assert "video/test.mp4" in publisher["body"] and "Ada Editor" in publisher["body"]
    restricted = next(m for m in admin["emails"] if m["recipient"] == "publisher2@example.com")
    assert "brand/logo.png" not in restricted["body"] and "brand/one.png" not in restricted["body"]
    team = next(m for m in admin["emails"] if m["recipient"] == "sales@example.com")
    assert distribution_data["contact_email"] in team["body"] and distribution_data["phone"] in team["body"]
    assert "WhatsApp" not in team["body"]
    assert distribution_data["announcement"] in team["body"] and "Total: 7" in team["body"]
    assert "brand/logo.png" in team["body"] and "brand/one.png" in team["body"] and "video/test.mp4" in team["body"]
    receipt = await client.get(f"/v1/distribution/{id}/invoice", headers=OWNER)
    assert receipt.status_code == 200 and "CF-DIST-" in receipt.text and "Total: 7" in receipt.text
    assert "Placement credits" in receipt.text and "Logo credits" in receipt.text and "Picture credits" in receipt.text
    assert "attachment;" in receipt.headers["content-disposition"]
    customer = (await client.get(f"/v1/distribution/{id}", headers=OWNER)).json()
    assert customer["invoice"]["number"] == admin["invoice"]["number"]
    assert "publisher@example.com" not in str(customer) and "internal_status" not in str(customer)
    assert "emails" not in customer and "activity" not in customer
    async with maker() as db:
        assert (await db.get(Workspace, workspace)).credit_balance == 3


async def test_media_opt_out_and_stale_displayed_quote(client, distribution_data):
    await configure_outlet(client, "1", logo_credits="3")
    data = {**distribution_data, "media_options": {"1": {"include_logo": False, "include_pictures": False}}}
    id = await draft(client, data)
    old_version = (await client.get("/v1/distribution/outlets", headers=OWNER)).json()["quote_version"]
    await configure_outlet(client, "1", credits="2")
    # Even though saving refreshes the server draft's price, a stale browser cannot authorize a higher charge.
    await client.put(f"/v1/distribution/{id}", headers=OWNER, json=data)
    r = await client.post(
        f"/v1/distribution/{id}/submit", headers=OWNER, json={"expected_total": "0", "quote_version": old_version}
    )
    assert r.status_code == 409
    assert not registry.get_email().sent
    current = (await client.get("/v1/distribution/outlets", headers=OWNER)).json()
    r = await client.post(
        f"/v1/distribution/{id}/submit",
        headers=OWNER,
        json={"expected_total": "2", "quote_version": current["quote_version"]},
    )
    assert r.status_code == 200, r.text
    assert Decimal(r.json()["total_credits"]) == 2
    assert r.json()["data"]["outlets"][0]["logo_fee"] == "0"
    assert r.json()["data"]["outlets"][0]["logo_key"] is None


async def test_published_links_are_per_outlet_notify_once_and_internal_progress_private(client, distribution_data):
    id, admin = await paid_details(client, distribution_data)
    first, second = admin["placements"]
    initial = len(registry.get_email().sent)
    path = f"/v1/admin/distribution/{id}/placements/{first['id']}"
    r = await client.patch(
        path, headers=OPS, json={"internal_status": "payment_made", "internal_notes": "PRIVATE publisher payment 77"}
    )
    assert r.status_code == 200
    customer = (await client.get(f"/v1/distribution/{id}", headers=OWNER)).json()
    assert "payment_made" not in str(customer) and "PRIVATE" not in str(customer)
    assert len(registry.get_email().sent) == initial
    url = "https://publication.example.com/our-launch"
    for _ in range(2):
        r = await client.patch(path, headers=OPS, json={"published_url": url})
        assert r.status_code == 200, r.text
    customer = (await client.get(f"/v1/distribution/{id}", headers=OWNER)).json()
    assert customer["status"] == "in_progress"
    assert customer["placements"][0]["status"] == "published"
    assert customer["placements"][0]["published_url"] == url
    assert customer["placements"][1]["status"] == "pending"
    assert len(registry.get_email().sent) == initial + 2
    assert all("2 media outlets" in m["text"] for m in registry.get_email().sent[-2:])
    r = await client.patch(
        f"/v1/admin/distribution/{id}/placements/{second['id']}",
        headers=OPS,
        json={"published_url": "https://second.example.com/news"},
    )
    assert r.status_code == 200 and r.json()["status"] == "completed"
    assert len(registry.get_email().sent) == initial + 4
    logged = (await client.get(f"/v1/admin/distribution/{id}", headers=OPS)).json()
    assert len([m for m in logged["emails"] if m["kind"] == "published"]) == 4
    assert any(a["kind"] == "placement_updated" for a in logged["activity"])


@pytest.mark.parametrize(
    "url",
    ["javascript:alert(1)", "data:text/html,test", "ftp://example.com/file", "https://user:password@example.com/post"],
)
async def test_rejects_unsafe_publication_links(client, distribution_data, url):
    id, admin = await paid_details(client, distribution_data)
    r = await client.patch(
        f"/v1/admin/distribution/{id}/placements/{admin['placements'][0]['id']}",
        headers=OPS,
        json={"published_url": url},
    )
    assert r.status_code == 422


async def test_no_publication_without_url_or_unpaid_outreach(client, distribution_data):
    id, admin = await paid_details(client, distribution_data)
    placement = admin["placements"][0]
    assert (
        await client.patch(
            f"/v1/admin/distribution/{id}/placements/{placement['id']}", headers=OPS, json={"status": "published"}
        )
    ).status_code == 422
    assert (
        await client.patch(f"/v1/admin/distribution/{id}", headers=OPS, json={"status": "completed"})
    ).status_code == 409
    unpaid = await draft(client, distribution_data)
    assert (
        await client.post(
            f"/v1/admin/distribution/{unpaid}/placements/anything/outreach",
            headers=OPS,
            json={"idempotency_key": "abcdefghijklmnop"},
        )
    ).status_code == 404
    assert (await client.get(f"/v1/distribution/{unpaid}/invoice", headers=OWNER)).status_code == 409


async def test_manual_outreach_saved_copy_and_idempotent_retry(client, distribution_data):
    id, admin = await paid_details(client, distribution_data)
    placement = admin["placements"][0]
    path = f"/v1/admin/distribution/{id}/placements/{placement['id']}"
    assert (
        await client.patch(
            path,
            headers=OPS,
            json={
                "contact_email": "editor@example.com",
                "outreach_subject": "Publication follow-up",
                "outreach_body": "Hello, please confirm placement and payment details.",
            },
        )
    ).status_code == 200
    count = len(registry.get_email().sent)
    responses = await asyncio.gather(
        *[
            client.post(path + "/outreach", headers=OPS, json={"idempotency_key": "same-request-token-12345"})
            for _ in range(2)
        ]
    )
    assert all(r.status_code == 200 for r in responses), [r.text for r in responses]
    assert len(registry.get_email().sent) == count + 1
    mail = registry.get_email().sent[-1]
    assert mail["to"] == "editor@example.com" and mail["subject"] == "Publication follow-up"
    assert "please confirm placement" in mail["text"]


async def test_independent_recipient_retry_without_duplicate_receipts(client, distribution_data, monkeypatch):
    await client.put("/v1/admin/distribution/config", headers=OPS, json={"team_emails": ["sales@example.com"]})
    original = emails.send_email

    async def partial(to, *args, **kwargs):
        return False if to == "sales@example.com" else await original(to, *args, **kwargs)

    monkeypatch.setattr(emails, "send_email", partial)
    id, admin = await paid_details(client, distribution_data)
    failed = next(m for m in admin["emails"] if m["recipient"] == "sales@example.com")
    assert failed["status"] == "failed" and admin["email_sent"]
    assert len(registry.get_email().sent) == 2
    monkeypatch.setattr(emails, "send_email", original)
    await emails.retry_confirmations()
    assert len(registry.get_email().sent) == 3
    admin = (await client.get(f"/v1/admin/distribution/{id}", headers=OPS)).json()
    recovered = next(m for m in admin["emails"] if m["id"] == failed["id"])
    assert recovered["status"] == "sent" and recovered["attempts"] == 2
    await client.post(f"/v1/admin/distribution/{id}/emails/{failed['id']}/retry", headers=OPS)
    assert len(registry.get_email().sent) == 3


async def test_config_and_outreach_access_control_and_template_validation(client, distribution_data):
    assert (await client.get("/v1/admin/distribution/config", headers=OWNER)).status_code == 403
    assert (
        await client.put("/v1/admin/distribution/config", headers=OWNER, json={"team_emails": ["a@example.com"]})
    ).status_code == 403
    assert (
        await client.put("/v1/admin/distribution/config", headers=OPS, json={"team_emails": ["not-email"]})
    ).status_code == 422
    base = (await client.get("/v1/admin/distribution/config", headers=OPS)).json()["outlets"][0]
    for change in [
        {"direct_access": True, "contact_email": None},
        {"email_body": "{headline.__class__}"},
        {"email_subject": "Hello\nCC: attacker@example.com"},
        {"credits": "-1"},
    ]:
        assert (
            await client.put("/v1/admin/distribution/outlets/1", headers=OPS, json={**base, **change})
        ).status_code == 422
    id, admin = await paid_details(client, distribution_data)
    assert (await client.get(f"/v1/admin/distribution/{id}", headers=OWNER)).status_code == 403
    assert (
        await client.patch(
            f"/v1/admin/distribution/{id}/placements/{admin['placements'][0]['id']}",
            headers=OWNER,
            json={"internal_status": "payment_made"},
        )
    ).status_code == 403
    public_catalog = (await client.get("/v1/distribution/outlets", headers=OWNER)).json()
    assert "contact_email" not in str(public_catalog) and "email_body" not in str(public_catalog)


async def test_insufficient_funds_creates_no_emails_or_placements(client, distribution_data):
    await configure_outlet(client, "1", credits="999")
    id = await draft(client, distribution_data)
    assert (await client.post(f"/v1/distribution/{id}/submit", headers=OWNER)).status_code == 402
    admin = (await client.get(f"/v1/admin/distribution/{id}", headers=OPS)).json()
    assert not admin["emails"] and not admin["placements"] and not admin["invoice"]
    assert not registry.get_email().sent


async def test_concurrent_outlet_publications_roll_up_to_completed(client, distribution_data):
    id, admin = await paid_details(client, distribution_data)
    responses = await asyncio.gather(
        *[
            client.patch(
                f"/v1/admin/distribution/{id}/placements/{p['id']}",
                headers=OPS,
                json={"published_url": f"https://publication.example.com/post-{p['outlet_id']}"},
            )
            for p in admin["placements"]
        ]
    )
    assert all(r.status_code == 200 for r in responses), [r.text for r in responses]
    customer = (await client.get(f"/v1/distribution/{id}", headers=OWNER)).json()
    assert customer["status"] == "completed" and all(p["status"] == "published" for p in customer["placements"])
    assert len(registry.get_email().sent) == 6
    overall = await client.patch(f"/v1/admin/distribution/{id}", headers=OPS, json={"status": "in_progress"})
    assert overall.status_code == 200 and overall.json()["status"] == "completed"


async def test_stale_delivery_lease_and_exhausted_retries(client, distribution_data, maker, monkeypatch):
    from datetime import timedelta

    from app.models import DistributionMail
    from app.models.base import utcnow

    original = emails.send_email

    async def fail(*args, **kwargs):
        return False

    monkeypatch.setattr(emails, "send_email", fail)
    id, admin = await paid_details(client, distribution_data)
    ident = admin["emails"][0]["id"]
    async with maker() as db:
        row = await db.get(DistributionMail, ident)
        row.status, row.claimed_at, row.claim_token = "sending", utcnow() - timedelta(minutes=11), "dead-worker"
        await db.commit()
    monkeypatch.setattr(emails, "send_email", original)
    assert await emails.retry_confirmations() == 1
    assert len(registry.get_email().sent) == 2
    async with maker() as db:
        row = await db.get(DistributionMail, ident)
        row.status, row.sent_at, row.attempts = "failed", None, 8
        await db.commit()
    await emails.retry_confirmations()
    assert len(registry.get_email().sent) == 2
    response = await client.post(f"/v1/admin/distribution/{id}/emails/{ident}/retry", headers=OPS)
    assert response.status_code == 200
    assert len(registry.get_email().sent) == 3
    async with maker() as db:
        assert (await db.get(DistributionMail, ident)).attempts == 9


async def test_missing_policy_is_not_advertised_as_free_image_acceptance(client, distribution_data):
    catalog = (await client.get("/v1/distribution/outlets", headers=OWNER)).json()
    assert not catalog["outlets"][0]["media_policy_configured"]
    id, _ = await paid_details(client, distribution_data)
    row = (await client.get(f"/v1/distribution/{id}", headers=OWNER)).json()
    assert row["data"]["outlets"][0]["logo_key"] is None
    assert not row["data"]["outlets"][0]["include_logo"]


async def test_invoice_is_private_and_workspace_erasure_removes_outbox(client, distribution_data, maker, workspace):
    from app.models import DistributionActivity, DistributionMail, DistributionPlacement
    from app.services.privacy import delete_workspace, export_workspace

    id, _ = await paid_details(client, distribution_data)
    async with maker() as db:
        other = Workspace(name="Invoice outsider")
        db.add(other)
        await db.flush()
        db.add(User(email="outsider@example.com", workspace_id=other.id))
        await db.commit()
    assert (
        await client.get(f"/v1/distribution/{id}/invoice", headers={"Authorization": "Bearer dev:outsider@example.com"})
    ).status_code == 404
    async with maker() as db:
        ws = await db.get(Workspace, workspace)
        user = (
            await db.execute(select(User).where(User.workspace_id == workspace, User.email == "owner@acme.test"))
        ).scalar_one()
        exported = await export_workspace(db, ws, user)
        assert len(exported["distribution_requests"][0]["placements"]) == 2
        await delete_workspace(db, ws)
        await db.commit()
        for model in [DistributionActivity, DistributionMail, DistributionPlacement]:
            assert not (await db.execute(select(model).where(model.request_id == id))).scalars().all()


def test_outsize_media_quote_is_rejected_before_database_money_overflow():
    from app.services.distribution_catalog import QuoteTooLarge, quote

    outlets = [
        {
            "id": str(i),
            "name": "Outlet",
            "region": "Africa",
            "credits": "1000000",
            "accepts_logo": True,
            "accepts_images": True,
            "logo_credits": "1000000",
            "picture_credits": "1000000",
            "media_policy_configured": True,
        }
        for i in range(47)
    ]
    with pytest.raises(QuoteTooLarge):
        quote({"outlet_ids": [o["id"] for o in outlets], "logo_key": "logo", "picture_keys": ["picture"] * 10}, outlets)


async def test_outlet_categories_match_groups_and_preserve_existing_ids(client, workspace):
    data = (await client.get("/v1/distribution/outlets", headers=OWNER)).json()
    outlets = data["outlets"]
    assert len(outlets) == 53
    assert len({o["id"] for o in outlets}) == 53
    assert [o["name"] for o in outlets].count("Premium Times") == 1
    expected = {
        "Media outlets": routes.NAMES[:12],
        "Crypto News Channels": [
            "CoinSpeaks",
            "The Cryptofy",
            "The Crypto Reporters",
            "The Coins Report",
            "The Coins Insider",
        ],
        "Business (Africa) Channels": [
            "Business Insider",
            "Street Insider",
            "Bar Chart",
            "The Globe and Mail",
            "Benzinga",
        ],
        "Nigeria News Channels": routes.NAMES[22:38] + routes.NAMES[47:],
        "Entertainment News Channels": [
            "Naijaloaded",
            "Tooxclusive",
            "NotJustOk",
            "9jaflaver",
            "Mp3bullet",
            "Naijamusic",
            "MP3Naija",
            "AlbumTalks",
            "P mp Kulture",
        ],
    }
    for category, names in expected.items():
        assert [o["name"] for o in outlets if o["category"] == category] == names
    assert [(o["id"], o["name"]) for o in outlets] == [(str(i + 1), name) for i, name in enumerate(routes.NAMES)]


async def test_owner_credit_on_cf_prices_for_seventeen_outlets(client, workspace):
    outlets = (await client.get("/v1/distribution/outlets", headers=OWNER)).json()["outlets"]
    expected = [42, 83, 124, 69, 97, 61, 138, 28, 42, 42, 28, 28, 42, 42, 42, 42, 42]
    assert [Decimal(o["credits"]) for o in outlets[:17]] == list(map(Decimal, expected))
    assert all(Decimal(o["credits"]) == 0 for o in outlets if o["name"] not in routes.DEFAULT_OUTLET_CREDITS)


async def test_owner_prices_reach_quote_and_wallet_once(client, distribution_data, maker, workspace, monkeypatch):
    for outlet in routes.OUTLETS.values():
        monkeypatch.setitem(outlet, "credits", routes.DEFAULT_OUTLET_CREDITS.get(outlet["name"], "0"))
    async with maker() as db:
        ws = await db.get(Workspace, workspace)
        await ledger.apply(db, ws, Decimal("200"), "grant", ref="owner-price-test-funding")
        await db.commit()
    id = await draft(client, distribution_data)
    saved = (await client.get(f"/v1/distribution/{id}", headers=OWNER)).json()
    assert Decimal(saved["total_credits"]) == 125
    assert [Decimal(o["credits"]) for o in saved["data"]["outlets"]] == [42, 83]
    for _ in range(2):
        r = await client.post(f"/v1/distribution/{id}/submit", headers=OWNER, json={"expected_total": "125"})
        assert r.status_code == 200, r.text
    async with maker() as db:
        assert (await db.get(Workspace, workspace)).credit_balance == Decimal("85")
        assert await ledger.ledger_sum(db, workspace) == Decimal("85")


async def test_nigeria_sheet_final_margin_prices_reach_catalog(client, workspace):
    outlets = (await client.get("/v1/distribution/outlets", headers=OWNER)).json()["outlets"]
    expected = {
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
    }
    by_name = {o["name"]: o for o in outlets}
    for name, price in expected.items():
        assert by_name[name]["category"] == "Nigeria News Channels"
        assert Decimal(by_name[name]["credits"]) == Decimal(price)
    assert by_name["Naijaloaded"]["id"] == "39"
    assert by_name["P mp Kulture"]["id"] == "47"
    assert by_name["Pilot Newspaper"]["id"] == "48"


async def test_nigeria_fractional_prices_quote_and_debit_once(client, distribution_data, maker, workspace, monkeypatch):
    for outlet in routes.OUTLETS.values():
        monkeypatch.setitem(outlet, "credits", routes.DEFAULT_OUTLET_CREDITS.get(outlet["name"], "0"))
    async with maker() as db:
        ws = await db.get(Workspace, workspace)
        await ledger.apply(db, ws, Decimal("100"), "grant", ref="nigeria-price-test-funding")
        await db.commit()
    data = {**distribution_data, "outlet_ids": ["23", "31"]}
    id = await draft(client, data)
    saved = (await client.get(f"/v1/distribution/{id}", headers=OWNER)).json()
    assert Decimal(saved["total_credits"]) == Decimal("41.7")
    assert [Decimal(o["credits"]) for o in saved["data"]["outlets"]] == [Decimal("18.8"), Decimal("22.9")]
    for _ in range(2):
        r = await client.post(f"/v1/distribution/{id}/submit", headers=OWNER, json={"expected_total": "41.7"})
        assert r.status_code == 200, r.text
    # Subsequent admin price changes cannot reprice the paid request.
    monkeypatch.setitem(routes.OUTLETS["23"], "credits", "999")
    saved = (await client.get(f"/v1/distribution/{id}", headers=OWNER)).json()
    assert Decimal(saved["total_credits"]) == Decimal("41.7")
    async with maker() as db:
        assert (await db.get(Workspace, workspace)).credit_balance == Decimal("68.3")
        assert await ledger.ledger_sum(db, workspace) == Decimal("68.3")


async def test_distribution_submission_needs_only_phone_not_whatsapp(client, distribution_data):
    data = {key: value for key, value in distribution_data.items() if key != "whatsapp"}
    id = await draft(client, data)
    response = await client.post(f"/v1/distribution/{id}/submit", headers=OWNER)
    assert response.status_code == 200 and response.json()["paid"], response.text
