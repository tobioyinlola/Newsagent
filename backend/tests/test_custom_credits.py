from decimal import Decimal

import pytest
from sqlalchemy import func, select

from app.config import get_settings
from app.models import Checkout, Workspace
from app.services import ledger
from tests.conftest import OWNER
from tests.test_billing import event


async def quote(client, credits="220"):
    r = await client.post("/v1/billing/custom-quote", headers=OWNER, json={"credits": credits})
    assert r.status_code == 200, r.text
    return r.json()


def body(q, **extra):
    return {
        "amount_usd": q["amount_usd"],
        "custom_credits": q["credits"],
        "custom_quote_version": q["quote_version"],
        **extra,
    }


async def test_custom_quote_price_and_paid_credit_settlement_once(client, workspace, maker):
    q = await quote(client)
    assert Decimal(q["credits"]) == 220 and Decimal(q["amount_usd"]) == 594
    assert Decimal(q["amount_ngn"]) == Decimal("831600")
    r = await client.post("/v1/billing/checkout", headers=OWNER, json=body(q))
    assert r.status_code == 200, r.text
    id = r.json()["checkout_id"]
    async with maker() as db:
        co = await db.get(Checkout, id)
        assert co.amount_usd == 594 and co.credits == 220
        assert (await db.get(Workspace, workspace)).credit_balance == 10
    content, headers = event(id, amount="594")
    for _ in range(2):
        assert (await client.post("/v1/webhooks/billing", content=content, headers=headers)).status_code == 200
    async with maker() as db:
        assert (await db.get(Workspace, workspace)).credit_balance == 230
        assert await ledger.ledger_sum(db, workspace) == 230


@pytest.mark.parametrize("credits", ["0", "-1", "3.70", "1", "NaN", "Infinity", "220.001", "1000000000000"])
async def test_invalid_custom_quantities_never_create_checkout(client, workspace, maker, credits):
    r = await client.post("/v1/billing/custom-quote", headers=OWNER, json={"credits": credits})
    assert r.status_code == 422, r.text
    async with maker() as db:
        assert (await db.execute(select(func.count(Checkout.id)))).scalar_one() == 0


async def test_smallest_custom_quantity_meets_ten_dollar_minimum(client, workspace):
    q = await quote(client, "3.71")
    assert Decimal(q["amount_usd"]) == Decimal("10.02")
    assert (await client.post("/v1/billing/checkout", headers=OWNER, json=body(q))).status_code == 200
    # Keep the owner's existing $1 preset; the $10 minimum is for custom quantities.
    assert (await client.post("/v1/billing/checkout", headers=OWNER, json={"amount_usd": "1"})).status_code == 200


async def test_stale_and_tampered_custom_prices_must_be_reviewed(client, workspace, maker, monkeypatch):
    q = await quote(client)
    for overrides in [{"amount_usd": "1"}, {"custom_credits": "221"}, {"custom_quote_version": "wrong"}]:
        r = await client.post("/v1/billing/checkout", headers=OWNER, json={**body(q), **overrides})
        assert r.status_code == 409, r.text
    monkeypatch.setattr(get_settings(), "usd_per_credit", "3.00")
    assert (await client.post("/v1/billing/checkout", headers=OWNER, json=body(q))).status_code == 409
    q = await quote(client)
    assert Decimal(q["amount_usd"]) == 660
    assert (await client.post("/v1/billing/checkout", headers=OWNER, json=body(q))).status_code == 200


async def test_custom_quotes_require_a_session(client, workspace):
    assert (await client.post("/v1/billing/custom-quote", json={"credits": "220"})).status_code == 401
