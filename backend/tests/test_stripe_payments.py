"""Stripe card payments: checkout, the signed webhook, the status check, and the minimum amount.
A fake Stripe API stands in for api.stripe.com; the signature code under test is the real one."""

import json
import time
from decimal import Decimal
from urllib.parse import parse_qs

import httpx
import pytest

from app.config import get_settings
from app.integrations import registry
from app.integrations.billing.stripe import StripeBilling, sign
from app.models import Checkout, Workspace
from tests.conftest import OWNER

WHSEC = "whsec_test_secret_for_unit_tests"


class FakeStripe:
    """Just enough of Stripe's Checkout Session API. `paid(id)` plays the customer finishing payment."""

    def __init__(self) -> None:
        self.sessions: dict[str, dict] = {}
        self.created: list[dict] = []
        self.expired: list[str] = []
        self.intents: dict[str, dict] = {}  # payment intents, for refund and dispute lookups

    def handler(self, request: httpx.Request) -> httpx.Response:
        path = request.url.path.removeprefix("/v1")
        if request.method == "POST" and path == "/checkout/sessions":
            form = {k: v[0] for k, v in parse_qs(request.content.decode()).items()}
            self.created.append(form)
            sid = f"cs_test_{len(self.created)}"
            self.sessions[sid] = {
                "id": sid,
                "url": f"https://checkout.stripe.test/c/pay/{sid}",
                "status": "open",
                "payment_status": "unpaid",
                "currency": "usd",
                "amount_total": int(form["line_items[0][price_data][unit_amount]"]),
                "client_reference_id": form["client_reference_id"],
            }
            return httpx.Response(200, json=self.sessions[sid])
        if request.method == "GET" and path.startswith("/payment_intents/"):
            return httpx.Response(200, json=self.intents.get(path.split("/")[2], {"id": "unknown", "metadata": {}}))
        sid = path.split("/")[3]
        if request.method == "GET":
            return httpx.Response(200, json=self.sessions[sid])
        if path.endswith("/expire"):
            self.expired.append(sid)
            self.sessions[sid]["status"] = "expired"
            return httpx.Response(200, json=self.sessions[sid])
        return httpx.Response(404, json={"error": {"message": "no such route"}})

    def paid(self, sid: str, **changes) -> None:
        self.sessions[sid].update({"status": "complete", "payment_status": "paid", **changes})


@pytest.fixture
def stripe(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "stripe_secret_key", "sk_test_unit")
    monkeypatch.setattr(s, "stripe_webhook_secret", WHSEC)
    fake = FakeStripe()
    client = httpx.AsyncClient(base_url="https://api.stripe.com/v1", transport=httpx.MockTransport(fake.handler))
    registry.override(stripe_billing=StripeBilling(client=client))
    return fake


async def buy(client, amount="10"):
    r = await client.post("/v1/billing/checkout", json={"amount_usd": amount, "payment_method": "card"}, headers=OWNER)
    assert r.status_code == 200, r.text
    return r.json()


def webhook_body(co: str, sid: str, kind="checkout.session.completed") -> bytes:
    return json.dumps(
        {"id": f"evt_{sid}", "type": kind, "data": {"object": {"id": sid, "client_reference_id": co}}}
    ).encode()


async def deliver(client, body: bytes, *, secret=WHSEC, timestamp=None):
    headers = {"stripe-signature": sign(body, secret, timestamp), "content-type": "application/json"}
    return await client.post("/v1/webhooks/stripe", content=body, headers=headers)


async def balance(maker, wid):
    async with maker() as s:
        return (await s.get(Workspace, wid)).credit_balance


async def test_checkout_sends_the_customer_to_stripe_for_exactly_the_amount(client, workspace, maker, stripe):
    out = await buy(client, "50")
    assert out["url"] == "https://checkout.stripe.test/c/pay/cs_test_1"
    sent = stripe.created[0]
    assert sent["line_items[0][price_data][unit_amount]"] == "5000"  # cents, the amount on offer and nothing else
    assert sent["line_items[0][price_data][currency]"] == "usd" and sent["mode"] == "payment"
    assert sent["client_reference_id"] == out["checkout_id"]
    assert "card" not in json.dumps(sent).lower().replace("cover founder", "")  # no card data passes through us
    async with maker() as s:
        co = await s.get(Checkout, out["checkout_id"])
        assert (co.provider, co.provider_ref, co.status) == ("stripe", "cs_test_1", "pending")
        assert (co.amount_usd, co.credits) == (Decimal("50"), Decimal("18.52"))


async def test_a_paid_webhook_adds_the_credits_automatically_and_only_once(client, workspace, maker, stripe):
    start = await balance(maker, workspace)
    out = await buy(client, "10")
    stripe.paid("cs_test_1")
    body = webhook_body(out["checkout_id"], "cs_test_1")
    assert (await deliver(client, body)).json() == {"result": "granted"}
    assert await balance(maker, workspace) == start + Decimal("3.70")
    assert (await deliver(client, body)).json() == {"result": "duplicate"}  # Stripe retries deliveries
    assert await balance(maker, workspace) == start + Decimal("3.70")
    async with maker() as s:
        co = await s.get(Checkout, out["checkout_id"])
        assert co.status == "paid" and co.paid_at is not None


async def test_the_webhook_must_be_signed_by_stripe_and_fresh(client, workspace, maker, stripe):
    start = await balance(maker, workspace)
    out = await buy(client)
    stripe.paid("cs_test_1")
    body = webhook_body(out["checkout_id"], "cs_test_1")
    assert (await deliver(client, body, secret="whsec_somebody_else")).status_code == 401
    bad = {"stripe-signature": sign(body, WHSEC), "content-type": "application/json"}
    assert (await client.post("/v1/webhooks/stripe", content=body + b" ", headers=bad)).status_code == 401
    assert (
        await deliver(client, body, timestamp=int(time.time()) - 3600)
    ).status_code == 401  # replay of an old delivery
    assert (await client.post("/v1/webhooks/stripe", content=body)).status_code == 401  # no signature at all
    assert await balance(maker, workspace) == start  # nothing was granted by any of them


async def test_nothing_is_granted_unless_stripe_itself_says_paid(client, workspace, maker, stripe):
    start = await balance(maker, workspace)
    out = await buy(client)
    # a signed "completed" event for a session Stripe still reports as unpaid (e.g. a forged or early event)
    assert (await deliver(client, webhook_body(out["checkout_id"], "cs_test_1"))).json() == {"result": "pending"}
    assert await balance(maker, workspace) == start


async def test_a_payment_for_the_wrong_amount_or_currency_grants_nothing(client, workspace, maker, stripe):
    start = await balance(maker, workspace)
    out = await buy(client, "100")
    stripe.paid("cs_test_1", amount_total=1000)  # $10 taken for a $100 checkout
    assert (await deliver(client, webhook_body(out["checkout_id"], "cs_test_1"))).json() == {
        "result": "amount_mismatch"
    }
    other = await buy(client, "10")
    stripe.paid("cs_test_2", currency="eur")
    assert (await deliver(client, webhook_body(other["checkout_id"], "cs_test_2"))).json() == {
        "result": "currency_mismatch"
    }
    assert await balance(maker, workspace) == start


async def test_the_return_page_settles_the_payment_even_when_the_webhook_is_late(client, workspace, maker, stripe):
    start = await balance(maker, workspace)
    out = await buy(client)
    first = (await client.get(f"/v1/billing/stripe/{out['checkout_id']}", headers=OWNER)).json()
    assert first["status"] == "pending" and Decimal(first["credit_balance"]) == start
    stripe.paid("cs_test_1")
    async with maker() as s:  # the status check is throttled; let the next one through
        co = await s.get(Checkout, out["checkout_id"])
        co.last_verified_at = None
        await s.commit()
    done = (await client.get(f"/v1/billing/stripe/{out['checkout_id']}", headers=OWNER)).json()
    assert done["status"] == "paid" and Decimal(done["credit_balance"]) == start + Decimal("3.70")
    assert await balance(maker, workspace) == start + Decimal("3.70")


async def test_the_scheduled_check_settles_payments_whose_webhook_never_came(client, workspace, maker, stripe):
    from app.services.payments import reconcile_pending

    start = await balance(maker, workspace)
    await buy(client)
    stripe.paid("cs_test_1")
    assert await reconcile_pending() == 1
    assert await balance(maker, workspace) == start + Decimal("3.70")
    assert await reconcile_pending() == 0


async def test_one_customer_cannot_read_anothers_payment(client, workspace, maker, stripe):
    out = await buy(client)
    other = {"Authorization": "Bearer dev:someone@else.test"}
    r = await client.get(f"/v1/billing/stripe/{out['checkout_id']}", headers=other)
    assert r.status_code in (401, 403, 404)


async def test_backing_out_closes_the_session_and_adds_nothing(client, workspace, maker, stripe):
    start = await balance(maker, workspace)
    out = await buy(client)
    r = (await client.post(f"/v1/billing/stripe/{out['checkout_id']}/cancel", headers=OWNER)).json()
    assert r["status"] == "expired" and stripe.expired == ["cs_test_1"]
    assert await balance(maker, workspace) == start


async def test_the_lowest_amount_is_10_dollars_and_1_dollar_is_for_the_sandbox_only(
    client, workspace, monkeypatch, stripe
):
    from app.services import credits

    s = get_settings()
    monkeypatch.setattr(s, "environment", "staging")  # outside local development, a Stripe test key is the sandbox
    assert Decimal("1") in [o.amount_usd for o in credits.purchase_options()]
    monkeypatch.setattr(s, "stripe_secret_key", "sk_live_unit")  # a live key: real money, nothing below $10
    assert min(o.amount_usd for o in credits.purchase_options()) == Decimal("10")
    assert credits.option_for(Decimal("1")) is None

    # and through the API (back in local mode so the dev sign-in works): a live deployment refuses and hides the $1
    monkeypatch.setattr(s, "environment", "local")
    monkeypatch.setattr(credits, "sandbox", lambda: False)
    amounts = [Decimal(o["amount_usd"]) for o in (await client.get("/v1/billing/options", headers=OWNER)).json()]
    assert min(amounts) == Decimal("10")
    refused = await client.post(
        "/v1/billing/checkout", json={"amount_usd": "1", "payment_method": "card"}, headers=OWNER
    )
    assert refused.status_code == 422


async def test_card_is_offered_while_bank_transfer_review_is_on(client, workspace, monkeypatch, stripe):
    monkeypatch.setattr(get_settings(), "bank_transfer_review_enabled", True)
    methods = (await client.get("/v1/billing/payment-methods", headers=OWNER)).json()
    assert methods["usd_card"] is True and methods["stripe"] is True and methods["sandbox"] is True
    assert methods["min_fund_usd"] == "10"


async def test_without_a_stripe_key_card_checkout_is_unchanged(client, workspace, monkeypatch):
    monkeypatch.setattr(get_settings(), "stripe_secret_key", "")
    assert (await client.get("/v1/billing/payment-methods", headers=OWNER)).json()["stripe"] is False
    assert (await client.post("/v1/webhooks/stripe", content=b"{}")).status_code == 404


async def test_a_paid_checkout_emails_a_receipt_with_the_invoice_and_a_working_sign_in_button(
    client, workspace, maker, stripe
):
    out = await buy(client, "10")
    stripe.paid("cs_test_1")
    assert (await deliver(client, webhook_body(out["checkout_id"], "cs_test_1"))).json() == {"result": "granted"}
    sent = [m for m in registry.get_email().sent if m["subject"].startswith("Payment received")]
    assert len(sent) == 2  # the owner and the operator account both belong to this workspace
    mail = next(m for m in sent if m["to"] == "owner@acme.test")
    invoice = "CF-" + out["checkout_id"][:8].upper()
    assert mail["subject"] == f"Payment received: $10.00 for 3.70 credits (invoice {invoice})"
    for words in (
        "You've paid $10.00 for 3.70 credits",
        f"Invoice number: {invoice}",
        "Billed to: Acme",
        "Amount paid: $10.00",
        "Credits added: 3.70",
        "New balance: 13.70 credits",
        "Payment method: Card (Stripe)",
        "Payment reference: cs_test_1",
        "sign in to Cover Founder to start creating your videos",
        "Email coverfounder@gmail.com and quote the invoice number",
    ):
        assert words.lower() in mail["text"].lower(), words
    login = f"{get_settings().app_base_url}/login"
    assert f"Sign in to start creating: {login}" in mail["text"]  # the plain-text twin carries the link too
    assert f'href="{login}"' in mail["html"] and "Sign in to start creating" in mail["html"]  # the button
    assert invoice in mail["html"] and "$10.00" in mail["html"]


async def test_a_repeated_webhook_does_not_send_a_second_receipt(client, workspace, maker, stripe):
    out = await buy(client, "10")
    stripe.paid("cs_test_1")
    body = webhook_body(out["checkout_id"], "cs_test_1")
    await deliver(client, body)
    await deliver(client, body)
    assert (
        len([m for m in registry.get_email().sent if m["subject"].startswith("Payment received")]) == 2
    )  # once per person


async def test_with_bank_transfer_switched_off_customers_are_only_offered_card(client, workspace, monkeypatch, stripe):
    monkeypatch.setattr(get_settings(), "bank_transfer_review_enabled", True)
    monkeypatch.setattr(get_settings(), "bank_transfer_enabled", False)
    methods = (await client.get("/v1/billing/payment-methods", headers=OWNER)).json()
    assert (
        methods["bank_transfer"] is False
        and methods["usd_bank_transfer"] is False
        and methods["ngn_bank_transfer"] is False
    )
    assert methods["usd_card"] is True and methods["stripe"] is True
    # the card checkout goes straight to Stripe, as before
    out = await buy(client, "10")
    assert out["url"].startswith("https://checkout.stripe.test/")
    # and bank transfer is refused if someone asks for it anyway, in either currency
    for body in (
        {"amount_usd": "10", "currency": "USD", "payment_method": "bank_transfer"},
        {
            "amount_usd": "10",
            "currency": "NGN",
            "payment_method": "bank_transfer",
            "ngn_per_usd": str(get_settings().ngn_per_usd),
        },
    ):
        refused = await client.post("/v1/billing/checkout", json=body, headers=OWNER)
        assert refused.status_code == 409 and "pay by card" in refused.json()["detail"]


async def test_bank_transfer_is_on_by_default_and_comes_back_when_switched_on(client, workspace, monkeypatch, stripe):
    monkeypatch.setattr(get_settings(), "bank_transfer_review_enabled", True)
    assert get_settings().bank_transfer_enabled is True  # the shipped default: nothing changes until it is switched off
    assert (await client.get("/v1/billing/payment-methods", headers=OWNER)).json()["bank_transfer"] is True
    monkeypatch.setattr(get_settings(), "bank_transfer_enabled", False)
    assert (await client.get("/v1/billing/payment-methods", headers=OWNER)).json()["bank_transfer"] is False
    monkeypatch.setattr(get_settings(), "bank_transfer_enabled", True)  # brought back with the switch alone
    assert (await client.get("/v1/billing/payment-methods", headers=OWNER)).json()["bank_transfer"] is True
