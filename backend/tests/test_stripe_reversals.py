# ruff: noqa: F811
"""Refunds and chargebacks on Stripe card payments. A fake Stripe stands in for the API; the webhook signature code is the real one.
Rules under test: a refund takes back only the credits still in the wallet (never below zero, the rest is written off and the
team is told); a chargeback holds the credits at once and returns them if it is won; repeats change nothing twice; the ledger
always sums to the balance; the back office stops counting the money."""

import json
from decimal import Decimal

from app.integrations import registry
from app.models import Checkout, Workspace
from app.services import ledger
from tests.conftest import OPS, OWNER
from tests.test_stripe_payments import balance, buy, deliver, stripe, webhook_body  # noqa: F401  (stripe is a fixture)

CREDITS = Decimal("3.70")  # what a $10 payment buys


async def paid(client, stripe, amount="10", pi="pi_1"):
    out = await buy(client, amount)
    sid = f"cs_test_{len(stripe.created)}"
    stripe.paid(sid, payment_intent=pi)
    assert (await deliver(client, webhook_body(out["checkout_id"], sid))).json() == {"result": "granted"}
    stripe.intents[pi] = {"id": pi, "metadata": {"checkout_id": out["checkout_id"]}}
    return out["checkout_id"]


def refund_event(pi="pi_1", *, refunded=1000, amount=1000, eid="evt_r"):
    obj = {"id": "ch_1", "amount": amount, "currency": "usd", "amount_refunded": refunded, "payment_intent": pi}
    return json.dumps({"id": eid, "type": "charge.refunded", "data": {"object": obj}}).encode()


def dispute_event(kind, pi="pi_1", *, dispute="dp_1", status="needs_response", amount=1000):
    obj = {
        "id": dispute,
        "amount": amount,
        "currency": "usd",
        "payment_intent": pi,
        "status": status,
        "reason": "fraudulent",
    }
    return json.dumps(
        {"id": f"evt_{kind}{dispute}", "type": f"charge.dispute.{kind}", "data": {"object": obj}}
    ).encode()


async def result(client, body):
    r = await deliver(client, body)
    assert r.status_code == 200, r.text
    return r.json()["result"]


async def state(maker, workspace, co):
    async with maker() as s:
        row = await s.get(Checkout, co)
        total = await ledger.ledger_sum(s, workspace)
        ws = await s.get(Workspace, workspace)
        assert total == ws.credit_balance  # the ledger always sums to the balance
        return row.status, ws.credit_balance, dict(row.payment_context)


def sent(prefix):
    return [m for m in registry.get_email().sent if m["subject"].startswith(prefix)]


async def test_a_full_refund_takes_the_credits_back_and_tells_the_customer(client, workspace, maker, stripe):
    co = await paid(client, stripe)
    assert await balance(maker, workspace) == Decimal("10") + CREDITS
    assert await result(client, refund_event()) == "refunded"
    status, bal, ctx = await state(maker, workspace, co)
    assert (status, bal) == ("refunded", Decimal("10"))
    assert ctx["credits_removed"] == "3.70" and ctx["credits_unrecovered"] == "0.00"
    mail = next(m for m in sent("Refund processed") if m["to"] == "owner@acme.test")
    assert mail["subject"] == f"Refund processed: $10.00 (invoice CF-{co[:8].upper()})"
    assert "3.70 credits were taken off your wallet" in mail["text"] and "balance is now 10.00 credits" in mail["text"]
    assert not sent("Refund issued")  # nothing was spent, so no alert for the team


async def test_a_repeated_or_older_refund_event_changes_nothing(client, workspace, maker, stripe):
    await paid(client, stripe)
    assert await result(client, refund_event(refunded=400, eid="evt_a")) == "refunded"  # $4 of $10
    after_first = await balance(maker, workspace)
    assert after_first == Decimal("10") + CREDITS - Decimal("1.48")
    assert await result(client, refund_event(refunded=400, eid="evt_a")) == "duplicate"  # Stripe retries deliveries
    assert await result(client, refund_event(refunded=1000, eid="evt_b")) == "refunded"  # the rest, as a second refund
    assert await result(client, refund_event(refunded=400, eid="evt_c")) == "duplicate"  # an old event arriving late
    assert await balance(maker, workspace) == Decimal("10")  # exactly the 3.70, no more
    assert len(sent("Refund processed")) == 4  # two refunds, two people each (never a third)


async def test_a_partial_refund_takes_back_a_share_and_the_payment_shows_partly_refunded(
    client, workspace, maker, stripe
):
    co = await paid(client, stripe)
    assert await result(client, refund_event(refunded=250)) == "refunded"  # a quarter
    status, bal, ctx = await state(maker, workspace, co)
    assert (
        status == "partially_refunded"
        and ctx["refunded_usd"] == "2.5"
        and bal == Decimal("10") + CREDITS - Decimal("0.93")
    )
    revenue = (await client.get("/v1/admin/payments", headers=OPS)).json()["total_usd"]
    assert Decimal(str(revenue)) == Decimal("7.5")  # the back office counts what was kept


async def test_credits_already_spent_are_written_off_and_the_team_is_told(client, workspace, maker, stripe):
    co = await paid(client, stripe)
    async with maker() as s:  # the customer spends nearly everything on videos
        ws = await s.get(Workspace, workspace)
        await ledger.apply(s, ws, -(ws.credit_balance - Decimal("1")), "usage", description="videos", ref="spent")
        await s.commit()
    assert await result(client, refund_event()) == "refunded"
    status, bal, ctx = await state(maker, workspace, co)
    assert (status, bal) == ("refunded", Decimal("0"))  # never below zero
    assert ctx["credits_removed"] == "1.00" and ctx["credits_unrecovered"] == "2.70"
    alert = sent("Refund issued, 2.70 credits already spent")
    assert alert and "wrote off the rest" in alert[0]["text"] and "Acme" in alert[0]["text"]


async def test_a_chargeback_holds_the_credits_and_a_win_gives_them_back(client, workspace, maker, stripe):
    co = await paid(client, stripe)
    assert await result(client, dispute_event("created")) == "disputed"
    status, bal, _ = await state(maker, workspace, co)
    assert (status, bal) == ("disputed", Decimal("10"))
    assert await result(client, dispute_event("created")) == "duplicate"  # no second hold
    assert sent("Chargeback opened")
    assert (await client.get("/v1/admin/payments", headers=OPS)).json()["total_usd"] in (
        0,
        "0",
        "0.00",
        0.0,
    )  # not income while disputed
    assert await result(client, dispute_event("closed", status="won")) == "dispute_won"
    status, bal, ctx = await state(maker, workspace, co)
    assert (status, bal, ctx["dispute_status"]) == ("paid", Decimal("10") + CREDITS, "won")
    assert await result(client, dispute_event("closed", status="won")) == "duplicate"
    assert sent("Chargeback won")


async def test_a_lost_chargeback_keeps_the_credits_removed(client, workspace, maker, stripe):
    co = await paid(client, stripe)
    await result(client, dispute_event("created"))
    assert await result(client, dispute_event("closed", status="lost")) == "dispute_lost"
    status, bal, _ = await state(maker, workspace, co)
    assert (status, bal) == ("charged_back", Decimal("10"))
    assert sent("Chargeback lost")


async def test_a_dispute_closed_before_we_saw_it_open_is_still_handled(client, workspace, maker, stripe):
    co = await paid(client, stripe)
    assert await result(client, dispute_event("closed", status="lost")) == "dispute_lost"
    status, bal, _ = await state(maker, workspace, co)
    assert (status, bal) == ("charged_back", Decimal("10"))


async def test_a_chargeback_cannot_take_more_than_the_wallet_holds(client, workspace, maker, stripe):
    co = await paid(client, stripe)
    async with maker() as s:
        ws = await s.get(Workspace, workspace)
        await ledger.apply(s, ws, -(ws.credit_balance - Decimal("1")), "usage", description="videos", ref="spent")
        await s.commit()
    await result(client, dispute_event("created"))
    status, bal, ctx = await state(maker, workspace, co)
    assert (status, bal, ctx["dispute_credits_held"], ctx["dispute_credits_unrecovered"]) == (
        "disputed",
        Decimal("0"),
        "1.00",
        "2.70",
    )
    await result(client, dispute_event("closed", status="won"))
    assert (await state(maker, workspace, co))[1] == Decimal("1.00")  # only what was actually held comes back


async def test_events_for_payments_that_are_not_ours_or_not_paid_are_ignored(client, workspace, maker, stripe):
    start = await balance(maker, workspace)
    stripe.intents["pi_x"] = {"id": "pi_x", "metadata": {}}  # a payment made outside this app
    assert await result(client, refund_event("pi_x")) == "unknown_payment"
    out = await buy(client)  # a checkout nobody paid
    stripe.intents["pi_y"] = {"id": "pi_y", "metadata": {"checkout_id": out["checkout_id"]}}
    assert await result(client, refund_event("pi_y")) == "unknown_payment"
    assert await result(client, dispute_event("created", "pi_y")) == "unknown_payment"
    assert await balance(maker, workspace) == start


async def test_a_refund_that_does_not_match_the_payment_changes_nothing(client, workspace, maker, stripe):
    await paid(client, stripe)
    before = await balance(maker, workspace)
    assert (
        await result(client, refund_event(amount=5000, refunded=5000)) == "amount_mismatch"
    )  # a different charge amount
    assert await balance(maker, workspace) == before


async def test_refund_and_dispute_events_must_be_signed(client, workspace, maker, stripe):
    await paid(client, stripe)
    before = await balance(maker, workspace)
    assert (await client.post("/v1/webhooks/stripe", content=refund_event())).status_code == 401
    assert (await deliver(client, refund_event(), secret="whsec_somebody_else")).status_code == 401
    assert await balance(maker, workspace) == before


async def test_a_refunded_payment_page_says_so_and_is_not_mistaken_for_a_failed_one(client, workspace, maker, stripe):
    co = await paid(client, stripe)
    await result(client, refund_event())
    page = (await client.get(f"/v1/billing/stripe/{co}", headers=OWNER)).json()
    assert page["status"] == "refunded"
    history = (await client.get("/v1/billing/checkouts", headers=OWNER)).json()
    assert [c["status"] for c in history if c["id"] == co] == ["refunded"]
