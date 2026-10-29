from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.config import get_settings
from app.integrations import registry
from app.models import AuditLog, Job, Project
from app.pipeline.queue import get_queue
from tests.conftest import OPS, OWNER, VIDEO
from tests.helpers import make_awaiting_founder, make_final_ready


async def test_console_requires_operator(client, workspace):
    for path in (
        "/v1/admin/queue",
        "/v1/admin/jobs",
        "/v1/admin/cost-report",
        "/v1/admin/settings",
        "/v1/admin/audit",
        "/v1/admin/moderation",
    ):
        assert (await client.get(path, headers=OWNER)).status_code == 403
        assert (await client.get(path)).status_code == 401
        assert (await client.get(path, headers=OPS)).status_code == 200


async def test_queue_overview_counts_everything(client, workspace):
    await make_final_ready(client)
    await make_awaiting_founder(client)
    q = (await client.get("/v1/admin/queue", headers=OPS)).json()
    assert (
        q["projects"] == {"final_ready": 1, "awaiting_founder": 1} and q["jobs"]["succeeded"] == 5
    )  # 3 for the anchor-only video, 2 (anchor + clips) for the interview
    assert q["moderation_pending"] == 0 and q["paused"] is False


async def test_jobs_list_filters_and_flags_stuck_jobs(client, workspace, maker):
    pid = await make_final_ready(client)
    jobs = (await client.get("/v1/admin/jobs", headers=OPS)).json()
    assert {j["stage"] for j in jobs} == {"anchor_render", "preview_render", "final_render"} and jobs[0][
        "workspace_name"
    ] == "Acme"
    assert len((await client.get("/v1/admin/jobs?stage=final_render", headers=OPS)).json()) == 1
    assert (await client.get("/v1/admin/jobs?status=failed", headers=OPS)).json() == []
    async with maker() as s:
        j = (await s.execute(select(Job).where(Job.project_id == pid, Job.stage == "final_render"))).scalar_one()
        j.status, j.started_at = "running", datetime.now(UTC) - timedelta(hours=3)
        await s.commit()
    stuck = (await client.get("/v1/admin/jobs?status=running", headers=OPS)).json()
    assert len(stuck) == 1 and stuck[0]["stuck"] is True


async def test_operator_can_restart_a_failed_project_for_the_owner(client, workspace, maker):
    from app.integrations.avatar.mock import MockAvatarProvider

    class Flaky(MockAvatarProvider):
        async def generate(self, req):
            raise RuntimeError("down")

    registry.override(avatar=Flaky())
    pid = await make_final_ready(client)
    assert (await client.get(f"/v1/projects/{pid}", headers=OWNER)).json()["state"] == "failed"
    registry.override(avatar=MockAvatarProvider())  # vendor is back
    assert (await client.post(f"/v1/admin/projects/{pid}/retry", headers=OWNER)).status_code == 403
    assert (await client.post(f"/v1/admin/projects/{pid}/retry", headers=OPS)).status_code == 200
    await get_queue().drain()
    assert (await client.get(f"/v1/projects/{pid}", headers=OWNER)).json()["state"] == "final_ready"
    assert (await client.post(f"/v1/admin/projects/{pid}/retry", headers=OPS)).status_code == 409
    async with maker() as s:
        assert (
            await s.execute(select(AuditLog).where(AuditLog.action == "project.retry"))
        ).scalar_one().target_id == pid


async def test_cost_report_reconciles_with_the_ledger_and_computes_margin(client, workspace, maker, monkeypatch):
    monkeypatch.setattr(get_settings(), "credit_markup", "2")
    monkeypatch.setattr(get_settings(), "usd_per_credit", "1")
    a = await make_final_ready(client)
    b = await make_awaiting_founder(client)
    r = (await client.get("/v1/admin/cost-report", headers=OPS)).json()
    rows = {x["project_id"]: x for x in r["rows"]}
    async with maker() as s:
        pa, pb = await s.get(Project, a), await s.get(Project, b)
    assert Decimal(rows[a]["vendor_cost"]) == pa.cost_total and Decimal(rows[b]["vendor_cost"]) == pb.cost_total
    assert (
        Decimal(rows[a]["credits_charged"]) == pa.cost_total * 2 + VIDEO
    )  # the steps at 2x, plus the video's own price
    assert Decimal(rows[a]["margin"]) == pa.cost_total + VIDEO  # (2x cost + 1) at $1/credit, less the cost
    assert set(rows[a]["by_vendor"]) == {"mock", "renderer"} and rows[b]["interview"] is True
    s_ = r["summary"]
    assert (
        s_["videos"] == 1 and Decimal(s_["avg_vendor_cost"]) == pa.cost_total and Decimal(s_["markup"]) == 2
    )  # only finished videos
    csv = (await client.get("/v1/admin/cost-report.csv", headers=OPS)).text.splitlines()
    assert csv[0].startswith("project_id,workspace") and len(csv) == 3


async def test_settings_pause_stops_work_and_is_audited(client, workspace, maker):
    r = await client.patch("/v1/admin/settings", json={"paused": True, "pause_reason": "vendor incident"}, headers=OPS)
    assert r.json()["paused"] is True and r.json()["pause_reason"] == "vendor incident"
    pid = await make_final_ready(client)
    assert (await client.get(f"/v1/projects/{pid}", headers=OWNER)).json()["state"] == "limit_reached"
    assert (await client.get("/v1/admin/queue", headers=OPS)).json()["paused"] is True
    await client.patch("/v1/admin/settings", json={"paused": False}, headers=OPS)
    await client.post(f"/v1/projects/{pid}/retry", headers=OWNER)
    await get_queue().drain()
    assert (await client.get(f"/v1/projects/{pid}", headers=OWNER)).json()["state"] == "final_ready"
    log = (await client.get("/v1/admin/audit?action=settings", headers=OPS)).json()
    assert len(log) == 2 and log[0]["actor"] == "ops@example.com" and log[1]["detail"]["paused"] is True


async def test_failover_settings_validation(client, workspace):
    ok = await client.patch(
        "/v1/admin/settings",
        json={"avatar_primary": "heygen", "avatar_secondary": "synthesia", "avatar_failover": True},
        headers=OPS,
    )
    assert (
        ok.status_code == 200 and ok.json()["avatar_secondary"] == "synthesia" and ok.json()["avatar_failover"] is True
    )
    same = await client.patch("/v1/admin/settings", json={"avatar_primary": "synthesia"}, headers=OPS)
    assert same.status_code == 422  # primary may not equal the existing secondary
    assert (await client.patch("/v1/admin/settings", json={"avatar_secondary": "none"}, headers=OPS)).json()[
        "avatar_secondary"
    ] is None
    assert (await client.patch("/v1/admin/settings", json={"avatar_primary": "bogus"}, headers=OPS)).status_code == 422


@pytest.mark.parametrize("n", [1])
async def test_audit_log_is_append_only_and_ordered(client, workspace, n):
    await client.put("/v1/admin/vendor-budgets", json={"vendor": "heygen", "limit": "5"}, headers=OPS)
    await client.put("/v1/admin/vendor-budgets", json={"vendor": "heygen", "limit": "9"}, headers=OPS)
    log = (await client.get("/v1/admin/audit?action=vendor_budget", headers=OPS)).json()
    assert [x["detail"]["limit"] for x in log] == ["9", "5"]  # newest first
