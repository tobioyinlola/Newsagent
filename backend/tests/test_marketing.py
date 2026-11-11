"""Marketing email foundations: the guards, the unsubscribe link, and the kill switch."""

from datetime import timedelta

import pytest
from sqlalchemy import select

from app.config import get_settings
from app.integrations import registry
from app.models import MarketingSend, User
from app.models.base import utcnow
from app.services import marketing
from tests.conftest import OPS, OWNER


@pytest.fixture
def on(monkeypatch):
    monkeypatch.setattr(get_settings(), "marketing_email", "on")


async def _owner(maker) -> User:
    async with maker() as s:
        return (await s.execute(select(User).where(User.email == "owner@acme.test"))).scalar_one()


async def _send(maker, user, **kw):
    async with maker() as s:
        u = await s.get(User, user.id)
        out = await marketing.send(s, u, kw.pop("subject", "Make your first video"), "Hello", **kw)
        await s.commit()
        return out


def _mail():
    return [m for m in registry.get_email().sent if m["to"] == "owner@acme.test"]


async def test_nothing_sends_while_the_engine_is_off(maker, workspace):
    u = await _owner(maker)
    assert await _send(maker, u) == "skipped:engine_off"
    assert _mail() == []


async def test_a_send_carries_the_unsubscribe_link_and_headers(maker, workspace, on):
    u = await _owner(maker)
    assert await _send(maker, u) == "sent"
    (m,) = _mail()
    assert "/v1/unsubscribe/" in m["headers"]["List-Unsubscribe"]
    assert m["headers"]["List-Unsubscribe-Post"] == "List-Unsubscribe=One-Click"
    assert "Unsubscribe" in m["html"] and "/v1/unsubscribe/" in m["text"]


async def test_dry_run_logs_but_sends_nothing(maker, workspace, monkeypatch):
    monkeypatch.setattr(get_settings(), "marketing_email", "dry_run")
    u = await _owner(maker)
    assert await _send(maker, u) == "dry_run"
    assert _mail() == []


async def test_unsubscribe_link_stops_marketing_but_the_page_asks_first(client, maker, workspace, on):
    u = await _owner(maker)
    await _send(maker, u)
    token = _mail()[0]["headers"]["List-Unsubscribe"].strip("<>").rsplit("/", 1)[1]
    page = await client.get(f"/v1/unsubscribe/{token}")  # a mail scanner opening the link must not unsubscribe anyone
    assert page.status_code == 200 and "Unsubscribe" in page.text
    assert await _send(maker, u, subject="Second") == "skipped:too_soon"  # still subscribed, only held by the gap
    assert (await client.post(f"/v1/unsubscribe/{token}")).status_code == 200
    async with maker() as s:  # lift the gap so only the opt-out can be the reason
        for r in (await s.execute(select(MarketingSend))).scalars():
            r.created_at = utcnow() - timedelta(days=30)
        await s.commit()
    assert await _send(maker, u, subject="Third") == "skipped:opted_out"
    assert len(_mail()) == 1
    assert (await client.get("/v1/unsubscribe/nope")).status_code == 404


async def test_one_click_post_from_a_mail_app_unsubscribes(client, maker, workspace, on):
    u = await _owner(maker)
    await _send(maker, u)
    token = _mail()[0]["headers"]["List-Unsubscribe"].strip("<>").rsplit("/", 1)[1]
    r = await client.post(f"/v1/unsubscribe/{token}", content="List-Unsubscribe=One-Click")
    assert r.status_code == 200
    async with maker() as s:
        from app.models import MarketingPref

        assert (await s.get(MarketingPref, u.id)).source == "one_click"


async def test_frequency_cap_and_idempotency(maker, workspace, on):
    u = await _owner(maker)
    assert await _send(maker, u, idempotency_key="wf1:step1:u") == "sent"
    assert await _send(maker, u, idempotency_key="wf1:step1:u") == "skipped:already_sent"
    assert await _send(maker, u, idempotency_key="wf1:step2:u") == "skipped:too_soon"
    assert len(_mail()) == 1


async def test_suppressed_paused_and_capped(maker, workspace, on):
    u = await _owner(maker)
    async with maker() as s:
        await marketing.save_config(s, "ops@example.com", marketing.MarketingConfig(paused=True, min_gap_days=0))
        await s.commit()
    assert await _send(maker, u) == "skipped:paused"
    async with maker() as s:
        await marketing.save_config(s, "ops@example.com", marketing.MarketingConfig(min_gap_days=0, daily_cap=1))
        await marketing.suppress(s, "Owner@Acme.test", "hard bounce")
        await s.commit()
    assert await _send(maker, u) == "skipped:suppressed"
    async with maker() as s:
        await s.delete(await s.get(marketing.MarketingSuppression, "owner@acme.test"))
        await s.commit()
    assert await _send(maker, u) == "sent"
    assert await _send(maker, u) == "skipped:daily_cap"


async def test_a_failing_provider_is_logged_not_raised(maker, workspace, on):
    class Boom:
        async def send(self, *a, **k):
            raise RuntimeError("down")

    u = await _owner(maker)
    assert await _send(maker, u, provider=Boom()) == "failed"
    async with maker() as s:
        assert (await s.execute(select(MarketingSend))).scalar_one().status == "failed"


async def test_only_marketing_permissions_open_the_switches(client, workspace):
    assert (await client.get("/v1/admin/marketing/status", headers=OPS)).status_code == 200
    assert (await client.get("/v1/admin/marketing/status", headers=OWNER)).status_code in (401, 403)
    r = await client.put(
        "/v1/admin/marketing/config", json={"paused": True, "min_gap_days": 3, "daily_cap": 10}, headers=OPS
    )
    assert r.status_code == 200
    s = (await client.get("/v1/admin/marketing/status", headers=OPS)).json()
    assert s["config"]["paused"] is True and s["engine"] == "off"
