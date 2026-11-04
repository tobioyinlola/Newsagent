"""Referrals: whenever a business that came through a referral buys credits, the business that referred it is credited 5% of them."""

from decimal import Decimal

import pytest
from sqlalchemy import select

from app.config import get_settings
from app.integrations import registry
from app.integrations.billing.base import PaymentEvent
from app.models import Checkout, CreditTransaction, User, Workspace
from app.routes.billing import handle_payment_event
from app.services.payments import credit_email
from tests.test_auth_flow import last_code  # noqa: F401
from tests.test_referrals import balance, begin, link


async def referred_business(client, maker, email="buyer@example.com"):
    """A new business that signed up through the owner's referral link. Returns its workspace id."""
    code = (await link(client))["code"]
    verify = await begin(client, email, code)
    assert (await client.post("/v1/auth/signup/verify", json=verify)).status_code == 200
    async with maker() as db:
        return (await db.execute(select(User.workspace_id).where(User.email == email))).scalar_one()


async def buy(maker, workspace_id: str, credits: str, usd: str, event: str | None = None) -> tuple[str, str]:
    """A card payment that Stripe confirmed, as the platform sees it. Returns (checkout id, result)."""
    async with maker() as db:
        co = Checkout(workspace_id=workspace_id, credits=Decimal(credits), amount_usd=Decimal(usd), provider="stripe")
        db.add(co)
        await db.flush()
        result = await handle_payment_event(
            db,
            PaymentEvent(event_id=event or f"evt-{co.id}", checkout_id=co.id, status="paid", amount_usd=Decimal(usd)),
        )
        await db.commit()
        return co.id, result


async def test_the_referrer_earns_five_percent_of_every_purchase(client, workspace, maker):
    start = await balance(maker, workspace)
    referred = await referred_business(client, maker)
    assert await balance(maker, workspace) == start  # signing up pays nothing: the reward comes from purchases
    assert get_settings().referral_purchase_percent == "5"

    _, result = await buy(maker, referred, "18.52", "50.00")  # a $50 purchase
    assert result == "granted"
    assert await balance(maker, workspace) == start + Decimal("0.93")  # 5% of 18.52 credits

    await buy(maker, referred, "10", "27")  # and the next one, and the one after
    await buy(maker, referred, "3.70", "10")
    assert await balance(maker, workspace) == start + Decimal("0.93") + Decimal("0.50") + Decimal("0.19")

    report = await link(client)
    assert report["percent"] == "5" and Decimal(report["earned_credits"]) == Decimal("1.62")
    assert report["referrals"][0]["business"] == "Referred Business" and Decimal(
        report["referrals"][0]["credits"]
    ) == Decimal("1.62")
    assert "email" not in report["referrals"][0]
    async with maker() as db:
        assert (
            await db.execute(select(Workspace.credit_balance).where(Workspace.id == referred))
        ).scalar_one() == Decimal(
            "33.22"
        )  # the free signup credit plus everything the buyer paid for: nothing is taken from them


async def test_one_purchase_is_never_rewarded_twice(client, workspace, maker):
    referred = await referred_business(client, maker)
    co_id, _ = await buy(maker, referred, "10", "27", event="evt-once")
    after = await balance(maker, workspace)
    async with maker() as db:  # the payment provider delivers the same event again
        again = await handle_payment_event(
            db, PaymentEvent(event_id="evt-once", checkout_id=co_id, status="paid", amount_usd=Decimal("27"))
        )
        await db.commit()
    assert again == "duplicate"
    assert await balance(maker, workspace) == after
    async with maker() as db:
        rows = (
            (await db.execute(select(CreditTransaction).where(CreditTransaction.ref == f"referral-purchase:{co_id}")))
            .scalars()
            .all()
        )
        assert len(rows) == 1 and rows[0].amount == Decimal("0.50")


async def test_nobody_is_rewarded_when_the_buyer_was_not_referred_or_the_referrer_is_gone(client, workspace, maker):
    before = await balance(maker, workspace)
    await buy(maker, workspace, "10", "27")  # the owner buys for themselves: nothing goes to anyone else
    assert await balance(maker, workspace) == before + 10
    referred = await referred_business(client, maker, "gone@example.com")
    async with maker() as db:
        (await db.get(Workspace, workspace)).suspended = True  # a suspended referrer earns nothing
        await db.commit()
    mid = await balance(maker, workspace)
    await buy(maker, referred, "10", "27")
    assert await balance(maker, workspace) == mid


async def test_the_rate_is_a_setting(client, workspace, maker, monkeypatch):
    monkeypatch.setattr(get_settings(), "referral_purchase_percent", "10")
    referred = await referred_business(client, maker)
    before = await balance(maker, workspace)
    await buy(maker, referred, "18.52", "50")
    assert await balance(maker, workspace) == before + Decimal("1.85")
    monkeypatch.setattr(get_settings(), "referral_purchase_percent", "0")
    await buy(maker, referred, "18.52", "50")
    assert await balance(maker, workspace) == before + Decimal("1.85")


@pytest.mark.parametrize("credits", ["0.09"])
async def test_a_tiny_purchase_that_rounds_to_nothing_pays_nothing(client, workspace, maker, credits):
    referred = await referred_business(client, maker)
    before = await balance(maker, workspace)
    await buy(maker, referred, credits, "0.27")  # 5% of 0.09 is under half a cent
    assert await balance(maker, workspace) == before


async def test_the_referrer_is_told_what_they_earned(client, workspace, maker):
    referred = await referred_business(client, maker)
    registry.get_email().sent.clear()
    co_id, _ = await buy(maker, referred, "18.52", "50")
    async with maker() as db:
        await credit_email(db, await db.get(Checkout, co_id))
    mail = [m for m in registry.get_email().sent if m["subject"] == "You earned 0.93 credits"]
    assert len(mail) == 1 and mail[0]["to"] == "owner@acme.test" and "5% of their purchase" in mail[0]["text"]
    assert any(
        "Purchased" in (m["subject"] + m["text"])
        or "receipt" in m["subject"].lower()
        or "credits" in m["subject"].lower()
        for m in registry.get_email().sent
        if m["to"] == "buyer@example.com"
    )
