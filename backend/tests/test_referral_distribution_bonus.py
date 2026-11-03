# ruff: noqa: F811
"""The referral bonus: a business that signs up through a referral earns its referrer 1 credit (tested in test_referrals.py);
when that referred business first pays for a distribution, the referrer earns 4 more, once."""

from decimal import Decimal

import pytest
from sqlalchemy import select

from app.config import get_settings
from app.integrations import registry
from app.models import CreditTransaction, ReferralReward, User, Workspace
from app.routes import distribution as routes
from app.services import ledger
from tests.conftest import OWNER
from tests.test_distribution import distribution_data, draft  # noqa: F401  (distribution_data is a fixture)

REFERRER = {"Authorization": "Bearer dev:referrer@friend.test"}


@pytest.fixture
async def referrer(maker, workspace):
    """A second business whose link brought the paying workspace in (signup reward of 1 credit already given)."""
    async with maker() as db:
        ws = Workspace(name="Friendly Co", credit_balance=Decimal("0"))
        db.add(ws)
        await db.flush()
        user = User(email="referrer@friend.test", workspace_id=ws.id)
        db.add(user)
        await db.flush()
        await ledger.apply(db, ws, Decimal("1"), "grant", ref=f"referral:{workspace}", description="Referral reward")
        db.add(
            ReferralReward(
                referrer_user_id=user.id,
                referrer_workspace_id=ws.id,
                referred_user_id=None,
                referred_workspace_id=workspace,
                credits=Decimal("1"),
            )
        )
        await db.commit()
        return ws.id


async def wallet(maker, workspace_id):
    async with maker() as db:
        ws = await db.get(Workspace, workspace_id)
        assert await ledger.ledger_sum(db, workspace_id) == ws.credit_balance
        return ws.credit_balance


async def pay_for_distribution(client, data, monkeypatch, cost="3"):
    monkeypatch.setitem(routes.OUTLETS["1"], "credits", cost)
    monkeypatch.setitem(routes.OUTLETS["2"], "credits", "0")
    id = await draft(client, data)
    r = await client.post(f"/v1/distribution/{id}/submit", headers=OWNER)
    assert r.status_code == 200, r.text
    return id


def bonus_mail():
    return [m for m in registry.get_email().sent if m["subject"] == "You earned 4 bonus credits"]


async def test_the_referrer_earns_4_more_credits_when_the_referred_business_pays_for_distribution(
    client, distribution_data, maker, workspace, referrer, monkeypatch
):
    assert await wallet(maker, referrer) == Decimal("1")  # the signup reward only
    await pay_for_distribution(client, distribution_data, monkeypatch)
    assert await wallet(maker, referrer) == Decimal("5")  # +4
    mail = bonus_mail()
    assert len(mail) == 1 and mail[0]["to"] == "referrer@friend.test"
    assert "Owner Co" in mail[0]["text"] or "Acme" in mail[0]["text"]  # names the business that paid
    assert "on top of the credit you earned when they signed up" in mail[0]["text"]
    async with maker() as db:
        rows = (
            (await db.execute(select(CreditTransaction).where(CreditTransaction.ref == f"referral-bonus:{workspace}")))
            .scalars()
            .all()
        )
        assert len(rows) == 1 and rows[0].amount == Decimal("4") and rows[0].workspace_id == referrer


async def test_the_bonus_is_given_once_per_referred_business(client, distribution_data, maker, referrer, monkeypatch):
    await pay_for_distribution(client, distribution_data, monkeypatch)
    await pay_for_distribution(client, distribution_data, monkeypatch, cost="2")  # a second paid distribution
    assert await wallet(maker, referrer) == Decimal("5")  # still just +4 in total
    assert len(bonus_mail()) == 1


async def test_a_distribution_that_costs_nothing_does_not_earn_the_bonus(
    client, distribution_data, maker, referrer, monkeypatch
):
    await pay_for_distribution(client, distribution_data, monkeypatch, cost="0")
    assert await wallet(maker, referrer) == Decimal("1")
    assert not bonus_mail()
    await pay_for_distribution(client, distribution_data, monkeypatch, cost="3")  # a later paid one still does
    assert await wallet(maker, referrer) == Decimal("5")


async def test_a_business_that_was_not_referred_earns_nobody_a_bonus(
    client, distribution_data, maker, referrer, monkeypatch
):
    async with maker() as db:  # take away the referral link
        for row in (await db.execute(select(ReferralReward))).scalars():
            await db.delete(row)
        await db.commit()
    await pay_for_distribution(client, distribution_data, monkeypatch)
    assert await wallet(maker, referrer) == Decimal("1") and not bonus_mail()


async def test_no_bonus_for_a_suspended_referrer_or_when_the_bonus_is_set_to_zero(
    client, distribution_data, maker, referrer, monkeypatch
):
    monkeypatch.setattr(get_settings(), "referral_distribution_bonus_credits", "0")
    await pay_for_distribution(client, distribution_data, monkeypatch)
    assert await wallet(maker, referrer) == Decimal("1")
    monkeypatch.setattr(get_settings(), "referral_distribution_bonus_credits", "4")
    async with maker() as db:
        (await db.get(Workspace, referrer)).suspended = True
        await db.commit()
    await pay_for_distribution(client, distribution_data, monkeypatch, cost="2")
    assert await wallet(maker, referrer) == Decimal("1") and not bonus_mail()


async def test_the_referral_page_shows_the_bonus_and_counts_it_as_earned(
    client, distribution_data, maker, referrer, monkeypatch
):
    before = (await client.get("/v1/referrals", headers=REFERRER)).json()
    assert before["reward_credits"] == "1" and before["bonus_credits"] == "4"
    assert Decimal(before["earned_credits"]) == 1 and before["referrals"][0]["bonus_earned"] is False
    assert Decimal(before["referrals"][0]["credits"]) == 1
    await pay_for_distribution(client, distribution_data, monkeypatch)
    after = (await client.get("/v1/referrals", headers=REFERRER)).json()
    assert Decimal(after["earned_credits"]) == 5 and after["completed_referrals"] == 1
    assert after["referrals"][0]["bonus_earned"] is True and Decimal(after["referrals"][0]["credits"]) == 5
