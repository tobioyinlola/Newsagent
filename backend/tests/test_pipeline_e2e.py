from decimal import Decimal

import pytest
from sqlalchemy import select

from app.integrations import registry
from app.models import Asset, Job, Project, Workspace
from app.pipeline.queue import get_queue
from tests.conftest import OWNER, VIDEO

BRIEF = {"brief_text": "Acme helps farmers sell produce online. We have 5,000 users and we are the first of our kind."}


async def _to_ready(client):
    r = await client.post("/v1/projects", json=BRIEF, headers=OWNER)
    pid = r.json()["id"]
    r = await client.post(f"/v1/projects/{pid}/script/generate", headers=OWNER)
    assert r.status_code == 200, r.text
    return pid, r.json()


async def test_account_requires_invite(client, maker):
    r = await client.get("/v1/me", headers={"Authorization": "Bearer dev:stranger@x.test"})
    assert r.status_code == 403


async def test_unauthenticated_rejected(client, maker):
    assert (await client.get("/v1/me")).status_code == 401


async def test_claims_block_approval_until_confirmed(client, workspace):
    pid, script = await _to_ready(client)
    assert script["claim_flags"], "brief mentions users and a superlative"
    r = await client.post(f"/v1/projects/{pid}/script/approve", headers=OWNER)
    assert r.status_code == 422 and r.json()["detail"]["error"] == "claims_unconfirmed"


@pytest.mark.parametrize("vertical", [False, True])
async def test_full_mock_pipeline_run(client, workspace, maker, monkeypatch, vertical):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "render_vertical", vertical)
    pid, script = await _to_ready(client)
    body = {k: script[k] for k in ("segments", "ticker_lines", "lower_thirds", "interview_questions")}
    body["segments"] = [{"kind": "intro", "text": "Tonight we feature Acme, a farm marketplace."}]
    r = await client.put(f"/v1/projects/{pid}/script", json=body, headers=OWNER)
    assert r.status_code == 200 and r.json()["claim_flags"] == []

    r = await client.post(f"/v1/projects/{pid}/script/approve", headers=OWNER)
    assert r.status_code == 200, r.text
    await get_queue().drain()

    r = await client.get(f"/v1/projects/{pid}", headers=OWNER)
    data = r.json()
    assert data["state"] == "final_ready", data
    assert {a["format"] for a in data["assets"] if a["type"] == "render"} == (
        {"16x9", "9x16"} if vertical else {"16x9"}
    )  # vertical only when RENDER_VERTICAL is on
    assert {a["type"] for a in data["assets"]} >= {"anchor", "preview", "render", "thumbnail", "caption"}
    sent = registry.get_email().sent
    assert {m["to"] for m in sent} == {"owner@acme.test", "ops@example.com"}
    assert {m["subject"] for m in sent} == {"Your video is ready"} and "/ai-newsroom/" in sent[0]["text"]
    assert Decimal(data["cost_total"]) > 0

    async with maker() as s:
        jobs = (await s.execute(select(Job).where(Job.project_id == pid))).scalars().all()
        assert {j.stage for j in jobs} == {"anchor_render", "preview_render", "final_render"}
        assert all(j.status == "succeeded" and j.attempts == 1 for j in jobs)
        ws = await s.get(Workspace, workspace)
        assert ws.credit_balance == Decimal("10") - VIDEO - Decimal(data["cost_total"])
        job = next(j for j in jobs if j.stage == "final_render")
        # hard rule 2: disclosures are always in the render props
        assert job.result["props"]["disclosures"] == {"tag": "Featured", "anchor": "AI-generated anchor"}


async def test_rerun_is_idempotent_and_does_not_double_charge(client, workspace, maker):
    pid, script = await _to_ready(client)
    body = {k: script[k] for k in ("segments", "ticker_lines", "lower_thirds", "interview_questions")}
    body["segments"] = [{"kind": "intro", "text": "Tonight we feature Acme."}]
    await client.put(f"/v1/projects/{pid}/script", json=body, headers=OWNER)
    await client.post(f"/v1/projects/{pid}/script/approve", headers=OWNER)
    await get_queue().drain()
    from app.pipeline.runner import run_step

    async with maker() as s:
        before = (await s.get(Workspace, workspace)).credit_balance
    await run_step("anchor_render", {"project_id": pid})
    async with maker() as s:
        assert (await s.get(Workspace, workspace)).credit_balance == before


async def test_limit_reached_state_and_resume(client, workspace, maker, monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "credit_markup", "1000")  # the steps now cost more than the workspace holds
    pid, script = await _to_ready(client)
    body = {k: script[k] for k in ("segments", "ticker_lines", "lower_thirds", "interview_questions")}
    body["segments"] = [{"kind": "intro", "text": "Tonight we feature Acme."}]
    await client.put(f"/v1/projects/{pid}/script", json=body, headers=OWNER)
    await client.post(f"/v1/projects/{pid}/script/approve", headers=OWNER)
    await get_queue().drain()
    data = (await client.get(f"/v1/projects/{pid}", headers=OWNER)).json()
    assert data["state"] == "limit_reached" and Decimal(data["cost_total"]) == 0

    monkeypatch.setattr(get_settings(), "credit_markup", "1")  # affordable again
    await client.post(f"/v1/projects/{pid}/retry", headers=OWNER)
    await get_queue().drain()
    assert (await client.get(f"/v1/projects/{pid}", headers=OWNER)).json()["state"] == "final_ready"


async def test_vendor_failure_retries_then_fails_retryable(client, workspace, maker, monkeypatch):
    from app.integrations import registry
    from app.integrations.avatar.mock import MockAvatarProvider

    calls = {"n": 0}

    class Flaky(MockAvatarProvider):
        async def generate(self, req):
            calls["n"] += 1
            raise RuntimeError("vendor down")

    registry.reset_providers(avatar=Flaky())
    pid, script = await _to_ready(client)
    body = {k: script[k] for k in ("segments", "ticker_lines", "lower_thirds", "interview_questions")}
    body["segments"] = [{"kind": "intro", "text": "Tonight we feature Acme."}]
    await client.put(f"/v1/projects/{pid}/script", json=body, headers=OWNER)
    await client.post(f"/v1/projects/{pid}/script/approve", headers=OWNER)
    await get_queue().drain()
    data = (await client.get(f"/v1/projects/{pid}", headers=OWNER)).json()
    assert data["state"] == "failed" and data["failure_retryable"] is True
    assert calls["n"] == 3
    async with maker() as s:  # failed attempts cost nothing
        assert (await s.get(Workspace, workspace)).credit_balance == Decimal("10") - VIDEO
        assert (await s.get(Project, pid)).cost_total == 0
        assert (await s.execute(select(Asset).where(Asset.project_id == pid))).first() is None


async def test_admin_requires_operator(client, workspace):
    r = await client.post("/v1/admin/invites", json={"email": "a@b.example.com", "workspace_name": "X"}, headers=OWNER)
    assert r.status_code == 403
