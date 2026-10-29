import shutil
import subprocess
from decimal import Decimal

import pytest
from fastapi import HTTPException
from starlette.requests import Request

from app.config import get_settings
from app.integrations import registry
from app.models import Asset, Workspace
from app.services import ratelimit
from tests.conftest import OPS, OWNER
from tests.helpers import make_final_ready


def req(headers=None, host="10.0.0.1"):
    return Request(
        {
            "type": "http",
            "headers": [(k.lower().encode(), v.encode()) for k, v in (headers or {}).items()],
            "client": (host, 1234),
        }
    )


def test_client_ip_ignores_forwarded_header_unless_trusted(monkeypatch):
    r = req({"x-forwarded-for": "203.0.113.9, 10.1.1.1"})
    assert ratelimit.client_ip(r) == "10.0.0.1"
    monkeypatch.setattr(get_settings(), "trust_proxy_headers", True)
    assert ratelimit.client_ip(r) == "203.0.113.9"


async def test_memory_limit_blocks_then_isolates_users():
    ratelimit.reset()
    dep = ratelimit.limit("t", 2, 60)
    a, b = req({"authorization": "Bearer a"}, "1.1.1.1"), req({"authorization": "Bearer b"}, "2.2.2.2")
    await dep(a)
    await dep(a)
    with pytest.raises(HTTPException) as e:
        await dep(a)
    assert e.value.status_code == 429
    await dep(b)  # different user and IP unaffected


@pytest.mark.skipif(not shutil.which("redis-server"), reason="redis-server not installed")
async def test_redis_limiter_matches_memory_semantics(monkeypatch):
    port = 6391
    proc = subprocess.Popen(["redis-server", "--port", str(port), "--save", ""], stdout=subprocess.DEVNULL)
    try:
        s = get_settings()
        monkeypatch.setattr(s, "rate_limit_backend", "redis")
        monkeypatch.setattr(s, "redis_url", f"redis://localhost:{port}/0")
        monkeypatch.setattr(ratelimit, "_redis", None)
        import asyncio

        for _ in range(20):
            try:
                if await ratelimit._redis_hit("probe", 1000, 5):
                    break
            except Exception:
                await asyncio.sleep(0.1)
        assert [await ratelimit.hit("k", 2, 60) for _ in range(3)] == [True, True, False]
        assert await ratelimit.hit("other", 2, 60) is True
    finally:
        ratelimit._redis = None
        proc.terminate()


async def test_redis_outage_fails_open(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "rate_limit_backend", "redis")
    monkeypatch.setattr(s, "redis_url", "redis://localhost:1/0")
    monkeypatch.setattr(ratelimit, "_redis", None)
    assert await ratelimit.hit("x", 1, 60) is True
    monkeypatch.setattr(ratelimit, "_redis", None)


async def test_budget_alert_emails_operators(client, workspace, maker, monkeypatch):
    from sqlalchemy import select

    from app.models import VendorBudget

    async with maker() as s:  # push the renderer budget close to its limit so a normal render crosses 80%
        vb = (await s.execute(select(VendorBudget).where(VendorBudget.vendor == "renderer"))).scalar_one()
        vb.limit = Decimal("0.5")
        vb.spent = Decimal("0.35")
        await s.commit()
    await make_final_ready(client)
    import asyncio

    await asyncio.sleep(0.05)
    subjects = [m["subject"] for m in registry.get_email().sent]
    assert any(x.startswith("Budget alert: renderer") for x in subjects)
    assert sum(x.startswith("Budget alert") for x in subjects) == 1  # once, not on every step


async def test_owner_can_delete_finished_project_and_files(client, workspace, maker):
    from sqlalchemy import select

    pid = await make_final_ready(client)
    async with maker() as s:
        keys = [a.storage_key for a in (await s.execute(select(Asset).where(Asset.project_id == pid))).scalars()]
    assert keys and all([await registry.get_storage().exists(k) for k in keys if "anchor" not in k])
    token = (await client.post(f"/v1/projects/{pid}/share", headers=OWNER)).json()["url"].rsplit("/s/", 1)[1]
    assert (await client.delete(f"/v1/projects/{pid}", headers=OWNER)).status_code == 405  # customers can't delete
    assert (await client.delete(f"/v1/admin/projects/{pid}", headers=OPS)).status_code == 200
    assert (await client.get(f"/v1/projects/{pid}", headers=OWNER)).status_code == 404
    assert (await client.get(f"/v1/share/{token}")).status_code == 404
    assert not any([await registry.get_storage().exists(k) for k in keys if "anchor" not in k])
    async with maker() as s:
        assert (await s.execute(select(Asset).where(Asset.project_id == pid))).first() is None
        assert await s.get(Workspace, workspace)  # workspace untouched


async def test_cannot_delete_in_flight_project(client, workspace, maker):
    from app.models import Project, User

    async with maker() as s:
        s.add(User(email="x@example.com", workspace_id=(await s.get(Workspace, workspace)).id))
        await s.commit()
    r = await client.post("/v1/projects", json={"brief_text": "x" * 30}, headers=OWNER)
    pid = r.json()["id"]
    async with maker() as s:
        (await s.get(Project, pid)).state = "rendering_anchor"
        await s.commit()
    assert (await client.delete(f"/v1/admin/projects/{pid}", headers=OPS)).status_code == 409
