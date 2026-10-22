from decimal import Decimal

from sqlalchemy import select

from app.integrations import registry
from app.integrations.avatar.mock import MockAvatarProvider
from app.models import Asset, CreditTransaction, VendorBudget, Workspace
from app.services import ledger
from app.services.ledger import ledger_sum
from tests.conftest import OPS, OWNER
from tests.helpers import make_awaiting_founder, make_final_ready


class Down(MockAvatarProvider):
    async def generate(self, req):
        raise RuntimeError("heygen is down")


async def enable_failover(client, primary="heygen", secondary="synthesia"):
    r = await client.patch(
        "/v1/admin/settings",
        json={"avatar_primary": primary, "avatar_secondary": secondary, "avatar_failover": True},
        headers=OPS,
    )
    assert r.status_code == 200, r.text


async def test_default_chain_is_the_single_configured_provider(client, workspace, maker):
    pid = await make_final_ready(client)
    async with maker() as s:
        vendors = {
            t.vendor
            for t in (await s.execute(select(CreditTransaction).where(CreditTransaction.project_id == pid))).scalars()
        }
    assert vendors == {"mock", "renderer"}


async def test_primary_outage_fails_over_and_bills_the_secondary_only(client, workspace, maker):
    await enable_failover(client)
    registry.override(
        **{
            "avatar:heygen": Down(name="heygen"),
            "avatar:synthesia": MockAvatarProvider(name="synthesia", green_screen=True),
        }
    )
    registry.get_email().sent.clear()
    pid = await make_final_ready(client)
    assert (await client.get(f"/v1/projects/{pid}", headers=OWNER)).json()["state"] == "final_ready"
    async with maker() as s:
        rows = (await s.execute(select(CreditTransaction).where(CreditTransaction.project_id == pid))).scalars().all()
        paid = {t.vendor for t in rows if t.kind == "usage"}
        net_heygen = sum((t.vendor_cost or 0) for t in rows if t.vendor == "heygen")
        assert "synthesia" in paid and net_heygen == 0  # heygen's hold was released: failing over costs nothing extra
        assert await ledger_sum(s, workspace) == (await s.get(Workspace, workspace)).credit_balance
    assert any(
        m["subject"] == "Avatar failover: heygen failed" and m["to"] == "ops@example.com"
        for m in registry.get_email().sent
    )


async def test_green_screen_output_is_keyed_to_transparent_and_the_raw_copy_removed(client, workspace, maker):
    await enable_failover(client, primary="synthesia", secondary="none")
    await client.patch("/v1/admin/settings", json={"avatar_failover": False}, headers=OPS)
    registry.override(**{"avatar:synthesia": MockAvatarProvider(name="synthesia", green_screen=True)})
    pid = await make_final_ready(client)
    renderer = registry.get_renderer()
    assert len(renderer.keyed) == 1
    src, out_key = renderer.keyed[0]
    assert out_key == f"projects/{pid}/anchor.webm" and ".src.mp4" in src
    storage = registry.get_storage()
    assert await storage.exists(out_key) and not await storage.exists(f"{out_key}.src.mp4")
    async with maker() as s:
        assert (
            await s.execute(select(Asset).where(Asset.project_id == pid, Asset.type == "anchor"))
        ).scalar_one().storage_key == out_key


async def test_primary_budget_exhausted_uses_the_secondary(client, workspace, maker):
    await enable_failover(client)
    registry.override(
        **{"avatar:heygen": MockAvatarProvider(name="heygen"), "avatar:synthesia": MockAvatarProvider(name="synthesia")}
    )
    async with maker() as s:
        vb = (await s.execute(select(VendorBudget).where(VendorBudget.vendor == "heygen"))).scalar_one()
        vb.limit = Decimal("0")
        await ledger.apply(s, (await s.get(Workspace, workspace)), Decimal("0.01"), "adjustment")
        from app.services.spend_guard import ensure_vendor_budget

        await ensure_vendor_budget(s, "synthesia", Decimal("100"))
        await s.commit()
    pid = await make_final_ready(client)
    assert (await client.get(f"/v1/projects/{pid}", headers=OWNER)).json()["state"] == "final_ready"
    async with maker() as s:
        used = {
            t.vendor
            for t in (
                await s.execute(
                    select(CreditTransaction).where(
                        CreditTransaction.project_id == pid, CreditTransaction.kind == "usage"
                    )
                )
            ).scalars()
        }
    assert "synthesia" in used and "heygen" not in used


async def test_both_providers_down_fails_cleanly_with_nothing_charged(client, workspace, maker):
    await enable_failover(client)
    registry.override(**{"avatar:heygen": Down(name="heygen"), "avatar:synthesia": Down(name="synthesia")})
    pid = await make_final_ready(client)
    p = (await client.get(f"/v1/projects/{pid}", headers=OWNER)).json()
    assert p["state"] == "failed" and p["failure_retryable"] is True
    async with maker() as s:
        assert (await s.get(Workspace, workspace)).credit_balance == Decimal("10")
        assert await ledger_sum(s, workspace) == Decimal("10")


async def test_failover_off_means_the_secondary_is_never_used(client, workspace, maker):
    await client.patch(
        "/v1/admin/settings",
        json={"avatar_primary": "heygen", "avatar_secondary": "synthesia", "avatar_failover": False},
        headers=OPS,
    )
    syn = MockAvatarProvider(name="synthesia")
    registry.override(**{"avatar:heygen": Down(name="heygen"), "avatar:synthesia": syn})
    pid = await make_final_ready(client)
    assert (await client.get(f"/v1/projects/{pid}", headers=OWNER)).json()["state"] == "failed"


async def test_failover_applies_to_interview_clips_too(client, workspace, maker):
    await enable_failover(client)
    registry.override(
        **{"avatar:heygen": Down(name="heygen"), "avatar:synthesia": MockAvatarProvider(name="synthesia")}
    )
    pid = await make_awaiting_founder(client)
    assert (await client.get(f"/v1/projects/{pid}", headers=OWNER)).json()["state"] == "awaiting_founder"
    async with maker() as s:
        types = {a.type for a in (await s.execute(select(Asset).where(Asset.project_id == pid))).scalars()}
    assert {"anchor", "anchor_outro", "question_clip"} <= types


async def test_synthesia_adapter_request_shape(monkeypatch):
    import httpx

    from app.integrations.avatar.base import AvatarRequest
    from app.integrations.avatar.synthesia import SynthesiaProvider

    seen = {}

    def handler(req: httpx.Request) -> httpx.Response:
        if req.method == "POST":
            seen["body"] = req.read()
            return httpx.Response(201, json={"id": "v1", "status": "in_progress"})
        return httpx.Response(200, json={"status": "complete", "download": "https://cdn/x.mp4", "duration": 30})

    async def no_sleep(_):
        return None

    monkeypatch.setattr("app.integrations.avatar.synthesia.asyncio.sleep", no_sleep)
    p = SynthesiaProvider(
        httpx.AsyncClient(base_url="https://api.synthesia.io", transport=httpx.MockTransport(handler))
    )
    out = await p.generate(AvatarRequest(script_text="Hello from Accra", voice_accent="ghanaian"))
    assert b'"green_screen"' in seen["body"] and b"Hello from Accra" in seen["body"]
    assert out.needs_chroma_key and out.video_url == "https://cdn/x.mp4" and out.duration_s == 30 and out.cost > 0
