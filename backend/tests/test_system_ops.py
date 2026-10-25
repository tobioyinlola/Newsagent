"""Readiness, honesty about demo mode, pipeline metrics and the HeyGen callback."""

import hashlib
import hmac
import json

from sqlalchemy import select

from app.config import get_settings
from app.integrations import registry
from app.models import ProviderRequest, WebhookEvent
from app.pipeline.queue import get_queue
from tests.conftest import OPS, OWNER
from tests.helpers import make_final_ready
from tests.test_pipeline_reliability import AsyncVendor, approved_project, no_waiting  # noqa: F401


async def test_readiness_reports_the_database(client, workspace):
    r = await client.get("/health/ready")
    assert r.status_code == 200 and r.json()["checks"]["database"] == "ok" and r.json()["checks"]["storage"] == "ok"
    assert (await client.get("/health")).json() == {"status": "ok"}


async def test_demo_mode_is_declared_not_hidden(client, workspace):
    r = await client.get("/v1/capabilities", headers=OWNER)
    c = r.json()
    assert c["demo_mode"] is True and c["presenter"] == "demo" and "stand-ins" in c["message"]
    assert (await client.get("/v1/capabilities")).status_code == 401


async def test_metrics_are_for_operators_only(client, workspace):
    await make_final_ready(client)
    assert (await client.get("/v1/admin/pipeline-metrics", headers=OWNER)).status_code == 403
    m = (await client.get("/v1/admin/pipeline-metrics", headers=OPS)).json()
    assert m["projects_by_state"]["final_ready"] == 1 and m["jobs_24h_by_status"]["succeeded"] >= 1
    assert m["possibly_stuck_projects"] == [] and m["vendor_jobs_in_flight"] == 0


def sign(secret, body):
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


async def test_heygen_webhook_is_off_until_configured(client, workspace):
    r = await client.post("/v1/webhooks/heygen", content=b"{}")
    assert r.status_code == 404


async def test_heygen_webhook_checks_the_signature_and_ignores_repeats(client, workspace, maker, monkeypatch):
    monkeypatch.setattr(get_settings(), "heygen_webhook_secret", "s3cret-s3cret-s3cret")
    vendor = AsyncVendor()
    vendor.pending_polls = 10**6
    registry.override(avatar=vendor)

    async def stop_waiting():
        if vendor.polls >= 2:
            vendor.pending_polls = 0

    vendor.on_poll = stop_waiting
    from app.services import provider_requests

    monkeypatch.setattr(provider_requests, "POLL_INTERVAL_S", 0.0)
    pid = await approved_project(client, drain=False)
    await get_queue().drain()
    async with maker() as s:
        pr = (await s.execute(select(ProviderRequest).where(ProviderRequest.project_id == pid))).scalars().first()
        assert pr is not None and pr.vendor_video_id == "vid-1"
    body = json.dumps(
        {"event_type": "avatar_video.success", "event_id": "e-1", "event_data": {"video_id": "vid-1"}}
    ).encode()
    bad = await client.post("/v1/webhooks/heygen", content=body, headers={"signature": "nope"})
    assert bad.status_code == 401
    ok = await client.post(
        "/v1/webhooks/heygen", content=body, headers={"signature": sign("s3cret-s3cret-s3cret", body)}
    )
    assert ok.status_code == 200 and ok.json()["result"] == "accepted"
    again = await client.post(
        "/v1/webhooks/heygen", content=body, headers={"signature": "sha256=" + sign("s3cret-s3cret-s3cret", body)}
    )
    assert again.json()["result"] == "duplicate"
    await get_queue().drain()
    async with maker() as s:
        assert len((await s.execute(select(WebhookEvent))).scalars().all()) == 1
        assert (
            (await s.execute(select(ProviderRequest).where(ProviderRequest.project_id == pid)))
            .scalars()
            .first()
            .last_webhook_at
        )
    other = json.dumps({"event_id": "e-2", "event_data": {"video_id": "someone-elses"}}).encode()
    r = await client.post(
        "/v1/webhooks/heygen", content=other, headers={"signature": sign("s3cret-s3cret-s3cret", other)}
    )
    assert r.json()["result"] == "ignored"
