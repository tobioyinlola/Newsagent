import json

import pytest
from cryptography.fernet import Fernet
from sqlalchemy import select

from app.config import Settings
from app.integrations import registry
from app.models import Asset, AuditLog, BrandAsset, CreditTransaction, InterviewSession, Project, Take, User, Workspace
from app.runtime_checks import assert_runtime_ok, problems
from tests.conftest import OWNER
from tests.helpers import invite, make_awaiting_founder, make_final_ready, record

GOOD = dict(
    environment="production",
    use_mocks=False,
    operator_emails="ops@example.com",
    secret_key=Fernet.generate_key().decode(),
    renderer_shared_secret="r" * 32,
    billing_webhook_secret="b" * 32,
    billing_provider="stripe",
    clamd_host="clamd.internal",
    email_api_key="re_x",
    storage_access_key="AKIAXYZ",
    storage_secret_key="s3cr3t",
    database_url="postgresql+asyncpg://u:p@db.railway.internal/app",
    redis_url="redis://redis.railway.internal:6379",
    app_base_url="https://app.example.com",
    admin_base_url="https://admin.example.com",
    queue_backend="celery",
    trust_proxy_headers=True,
)


def settings(**over):
    return Settings(_env_file=None, **{**GOOD, **over})


# ---------- fail-fast config ----------
def test_a_correct_production_config_has_no_problems():
    assert problems(settings()) == []
    assert_runtime_ok(settings())


def test_local_is_exempt():
    assert problems(Settings(_env_file=None, environment="local")) == []


@pytest.mark.parametrize(
    "override,needle",
    [
        ({"use_mocks": True}, "USE_MOCKS"),
        ({"operator_emails": ""}, "OPERATOR_EMAILS"),
        ({"secret_key": ""}, "SECRET_KEY"),
        ({"secret_key": "not-a-key"}, "valid Fernet"),
        ({"renderer_shared_secret": "short"}, "RENDERER_SHARED_SECRET"),
        ({"billing_webhook_secret": ""}, "BILLING_WEBHOOK_SECRET"),
        ({"billing_provider": "mock"}, "BILLING_PROVIDER"),
        ({"clamd_host": ""}, "CLAMD_HOST"),
        ({"storage_access_key": "minioadmin"}, "MinIO defaults"),
        ({"database_url": "postgresql+asyncpg://newsagent:newsagent@localhost/x"}, "DATABASE_URL"),
        ({"app_base_url": "http://app.example.com"}, "https"),
        ({"admin_base_url": "http://admin.example.com"}, "ADMIN_BASE_URL"),
        ({"admin_base_url": "https://app.example.com"}, "different site"),
        ({"queue_backend": "inline"}, "QUEUE_BACKEND"),
        ({"environment": "prod"}, "ENVIRONMENT"),
    ],
)
def test_each_insecure_setting_is_caught(override, needle):
    assert any(needle in p for p in problems(settings(**override)))


def test_all_problems_are_reported_together():
    with pytest.raises(RuntimeError) as e:
        assert_runtime_ok(settings(use_mocks=True, clamd_host="", secret_key=""))
    assert str(e.value).count("\n - ") >= 3


# ---------- headers ----------
async def test_security_headers_and_no_store(client, workspace):
    r = await client.get("/v1/me", headers=OWNER)
    assert r.headers["x-content-type-options"] == "nosniff" and r.headers["x-frame-options"] == "DENY"
    assert r.headers["referrer-policy"] == "no-referrer" and r.headers["cache-control"] == "no-store"
    assert "camera=()" in r.headers["permissions-policy"]
    assert "no-store" not in (await client.get("/health")).headers.get("cache-control", "")


# ---------- export ----------
async def test_export_contains_everything_and_no_vendor_costs(client, workspace):
    pid = await make_awaiting_founder(client)
    token = await invite(client, pid, email="ada@startup.example.com")
    await client.post(f"/v1/interview/{token}/consent")
    await record(client, token, 0)
    r = await client.get("/v1/account/export", headers=OWNER)
    d = r.json()
    assert d["account"]["email"] == "owner@acme.test" and d["workspace"]["name"] == "Acme"
    p = d["projects"][0]
    assert (
        p["brief"]["text"]
        and p["scripts"][0]["segments"]
        and p["founder_interviews"][0]["founder_email"] == "ada@startup.example.com"
    )
    assert p["founder_interviews"][0]["consent_version"] and p["founder_answers"][0]["transcript"]
    assert d["credit_ledger"] and "vendor_cost" not in json.dumps(d) and token not in json.dumps(d)


async def test_export_is_private_and_audited(client, workspace, maker):
    await client.get("/v1/account/export", headers=OWNER)
    assert (await client.get("/v1/account/export")).status_code == 401
    async with maker() as s:
        assert (
            await s.execute(select(AuditLog).where(AuditLog.action == "account.export"))
        ).scalar_one().actor == "owner@acme.test"


# ---------- workspace deletion ----------
async def test_deleting_the_workspace_erases_data_but_keeps_financial_records(client, workspace, maker):
    pid = await make_final_ready(client)
    storage = registry.get_storage()
    async with maker() as s:
        keys = [a.storage_key for a in (await s.execute(select(Asset).where(Asset.project_id == pid))).scalars()]
        s.add(
            BrandAsset(
                workspace_id=workspace,
                key=f"brand/{workspace}/logo.png",
                kind="logo_light",
                content_type="image/png",
                size_bytes=3,
                status="clean",
            )
        )
        await storage.put(f"brand/{workspace}/logo.png", b"x")
        await s.commit()
    assert all([await storage.exists(k) for k in keys if "anchor" not in k])

    bad = await client.request("DELETE", "/v1/account", json={"confirm": "delete acme"}, headers=OWNER)
    assert bad.status_code == 422
    ok = await client.request("DELETE", "/v1/account", json={"confirm": "DELETE Acme"}, headers=OWNER)
    assert ok.status_code == 200
    assert not any([await storage.exists(k) for k in keys if "anchor" not in k]) and not await storage.exists(
        f"brand/{workspace}/logo.png"
    )
    async with maker() as s:
        ws = await s.get(Workspace, workspace)
        assert ws.deleted_at is not None and ws.name.startswith("deleted-") and ws.suspended
        assert (await s.execute(select(User).where(User.workspace_id == workspace))).first() is None
        assert (await s.execute(select(Project).where(Project.workspace_id == workspace))).first() is None
        assert (
            await s.execute(select(CreditTransaction).where(CreditTransaction.workspace_id == workspace))
        ).first() is not None  # books kept
        assert (
            await s.execute(select(AuditLog).where(AuditLog.action == "account.delete"))
        ).scalar_one().target_id == workspace
    assert (await client.get("/v1/me", headers=OWNER)).status_code == 403  # the account no longer exists


async def test_workspace_deletion_is_blocked_while_a_video_is_being_made(client, workspace, maker):
    pid = await make_final_ready(client)
    async with maker() as s:
        (await s.get(Project, pid)).state = "rendering_anchor"
        await s.commit()
    r = await client.request("DELETE", "/v1/account", json={"confirm": "DELETE Acme"}, headers=OWNER)
    assert r.status_code == 409


# ---------- founder erasure ----------
async def test_founder_can_erase_their_recordings_and_the_owner_is_told(client, workspace, maker):
    pid = await make_awaiting_founder(client)
    token = await invite(client, pid)
    await record(client, token, 0)
    await record(client, token, 1)
    await client.post(f"/v1/interview/{token}/submit")
    storage = registry.get_storage()
    async with maker() as s:
        t = (await s.execute(select(Take).where(Take.project_id == pid))).scalars().first()
        keys = [f"projects/{pid}/takes/{t.id}/raw/00000", t.processed_video_key]
    assert all([await storage.exists(k) for k in keys])
    registry.get_email().sent.clear()
    assert (await client.request("DELETE", f"/v1/interview/{token}/data")).status_code == 200
    assert not any([await storage.exists(k) for k in keys])
    async with maker() as s:
        assert (await s.execute(select(Take))).first() is None
        assert (await s.execute(select(Asset).where(Asset.type == "founder_take"))).first() is None
        assert (await s.get(Project, pid)).state == "awaiting_founder"
        assert (await s.execute(select(InterviewSession))).scalar_one().revoked_at is not None
    assert (await client.get(f"/v1/interview/{token}")).status_code == 404  # the link is closed
    assert "Your founder deleted their recordings" in {m["subject"] for m in registry.get_email().sent}


async def test_consent_text_tells_the_founder_about_deletion(client, workspace):
    pid = await make_awaiting_founder(client)
    token = await invite(client, pid)
    assert "delete all of your recordings" in (await client.get(f"/v1/interview/{token}")).json()["consent_text"]
