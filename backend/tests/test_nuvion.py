import asyncio
import base64
import copy
import hashlib
import hmac
import json
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import httpx
import pytest
from cryptography.hazmat.primitives import serialization
from cryptography.hazmat.primitives.asymmetric import rsa
from sqlalchemy import select

from app.config import get_settings
from app.integrations import registry
from app.integrations.billing.nuvion import NuvionBilling
from app.models import Checkout, CreditTransaction, User, Workspace
from app.services import ledger, payments
from tests.conftest import OWNER


@pytest.fixture(scope="module")
def public_key():
    return (
        rsa.generate_private_key(public_exponent=65537, key_size=2048)
        .public_key()
        .public_bytes(serialization.Encoding.PEM, serialization.PublicFormat.SubjectPublicKeyInfo)
        .decode()
    )


@pytest.fixture
async def acquiring(maker, monkeypatch, public_key):
    settings = get_settings()
    for key, value in {
        "billing_provider": "nuvion",
        "nuvion_api_key": "test-only-key",
        "nuvion_api_url": "https://api.nuvion.dev",
        "nuvion_account_id": "test-account",
        "nuvion_entity_id": "test-entity",
        "nuvion_public_key": public_key,
        "nuvion_webhook_secret": "test-only-webhook-signing-secret",
    }.items():
        monkeypatch.setattr(settings, key, value)
    state = {
        "intents": {},
        "calls": [],
        "mode": "3ds",
        "confirmations": 0,
        "verify_calls": 0,
        "mismatch": None,
        "timeout": False,
        "lookup_exists": False,
        "transfers": {},
    }

    def action(intent, status):
        return {
            "id": "action-" + intent["id"],
            "payment_intent_id": intent["id"],
            "status": status,
            "currency": intent["currency"],
            "amount": intent["amount"],
            "charge_amount": intent["amount"],
            "refunded_amount": 0,
            "account_id": intent["account_id"],
            "entity_id": "test-entity",
            "reference": intent["reference"],
            "action": "confirm",
            "category": "collections",
            "payment_type": "card-acq",
            **(
                {"next_action": {"url": "https://app.nuvion.dev/sessions/test-3ds"}}
                if status == "pending_user_action"
                else {}
            ),
        }

    async def handler(req):
        state["calls"].append((req.method, req.url.path, json.loads(req.content) if req.content else None))
        path = req.url.path
        if path == "/accounts/test-ngn-account":
            data = {
                "account": {
                    "id": "test-ngn-account",
                    "entity_id": "test-entity",
                    "currency": "NGN",
                    "display_name": "Test merchant",
                },
                "account_details": [
                    {
                        "account_id": "test-ngn-account",
                        "entity_id": "test-entity",
                        "currency": "NGN",
                        "status": "active",
                        "account_number": "0000000000",
                        "issuer": {"name": "Test bank"},
                        "config": {"inflow_enabled": True},
                    }
                ],
            }
        elif path == "/transfers":
            data = {"data": list(state["transfers"].values()), "meta": {"pagination": {"has_next": False}}}
        elif path.startswith("/transfers/"):
            data = state["transfers"][path.split("/")[-1]]
        elif path == "/payment-intents" and req.method == "GET":
            items = [i for i in state["intents"].values() if i["reference"] == req.url.params["reference"]]
            data = {"items": copy.deepcopy(items)}
        elif path == "/payment-intents" and req.method == "POST":
            body = json.loads(req.content)
            if any(i["reference"] == body["reference"] for i in state["intents"].values()):
                return httpx.Response(409)
            data = {
                **body,
                "id": f"intent-{len(state['intents']) + 1}",
                "status": "requires_action",
                "intent_action": None,
            }
            state["intents"][data["id"]] = data
        elif path == "/intent-actions" and req.method == "GET":
            data = {
                "items": [
                    copy.deepcopy(i["intent_action"])
                    for i in state["intents"].values()
                    if i["id"] == req.url.params["payment_intent_id"] and i.get("intent_action")
                ]
            }
        elif path == "/intent-actions":
            if state.get("reject_code"):
                return httpx.Response(
                    400,
                    headers={"x-request-id": "test-request-id"},
                    json={
                        "status": "error",
                        "type": state["reject_code"],
                        "message": "SENSITIVE RAW PROCESSOR BODY MUST NOT BE LOGGED",
                    },
                )
            state["confirmations"] += 1
            body = json.loads(req.content)
            intent = state["intents"][body["payment_intent_id"]]
            assert body["intent_action"]["payment_type_data"]["auth_model"] == "3ds_required"
            assert "card_number" not in body["intent_action"]["payment_type_data"]
            if state["timeout"]:
                raise httpx.ReadTimeout("test timeout", request=req)
            intent["status"] = (
                "completed" if state["mode"] == "paid" else "failed" if state["mode"] == "declined" else "processing"
            )
            intent["intent_action"] = action(
                intent,
                "completed"
                if state["mode"] == "paid"
                else "failed"
                if state["mode"] == "declined"
                else "pending_user_action",
            )
            data = intent["intent_action"]
        elif path.startswith("/intent-verifications/"):
            state["verify_calls"] += 1
            intent = next(
                i for i in state["intents"].values() if i.get("intent_action", {}).get("id") == path.split("/")[-1]
            )
            if state["mode"] == "verify-paid":
                intent["status"] = "completed"
                intent["intent_action"] = action(intent, "completed")
            data = intent["intent_action"]
        elif path.startswith("/payment-intents/"):
            intent = state["intents"][path.split("/")[-1]]
            if req.method == "PATCH":
                assert json.loads(req.content)["action"] == "cancel"
                intent["status"] = "cancelled"
            data = copy.deepcopy(intent)
            if state["mismatch"]:
                key, value = state["mismatch"]
                data[key] = value
        else:
            raise AssertionError((req.method, path))
        return httpx.Response(200, json={"status": "success", "data": copy.deepcopy(data)})

    client = httpx.AsyncClient(base_url="https://api.nuvion.dev", transport=httpx.MockTransport(handler))
    provider = NuvionBilling(client)
    registry.override(billing=provider, nuvion_billing=provider)
    state["action"] = action
    yield state
    await client.aclose()


def confirmation():
    return {
        "encrypted_data": base64.b64encode(b"x" * 256).decode(),
        "first_name": "Ada",
        "last_name": "Obi",
        "billing_address": {
            "address_line_one": "1 Main Street",
            "city": "Lagos",
            "state": "Lagos",
            "country": "NG",
            "zip": "100001",
        },
        "browser_info": {"language": "en-NG", "screen_width": "390", "screen_height": "844"},
    }


async def start(client):
    r = await client.post("/v1/billing/checkout", headers=OWNER, json={"amount_usd": "10"})
    assert r.status_code == 200, r.text
    id = r.json()["checkout_id"]
    assert r.json()["url"].endswith(f"/billing/card/{id}")
    r = await client.get(f"/v1/billing/card/{id}", headers=OWNER)
    assert r.status_code == 200, r.text
    return id


def signed(intent, *, timestamp=None, event="payment_intent.completed", bad=False):
    timestamp = timestamp or datetime.now(UTC).isoformat()
    body = json.dumps({"event": event, "data": intent}).encode()
    sig = hmac.new(
        b"wrong" if bad else b"test-only-webhook-signing-secret", timestamp.encode() + b"." + body, hashlib.sha256
    ).hexdigest()
    return body, {
        "x-nuvion-event-timestamp": timestamp,
        "x-nuvion-event-signature": sig,
        "x-nuvion-event-id": "test-event",
    }


async def balance(maker, workspace):
    async with maker() as db:
        ws = await db.get(Workspace, workspace)
        assert await ledger.ledger_sum(db, workspace) == ws.credit_balance
        return ws.credit_balance


async def test_create_intent_in_usd_cents_and_reuse(client, workspace, acquiring):
    id = await start(client)
    for _ in range(2):
        assert (await client.get(f"/v1/billing/card/{id}", headers=OWNER)).status_code == 200
    calls = [body for method, path, body in acquiring["calls"] if method == "POST" and path == "/payment-intents"]
    assert len(calls) == 1 and calls[0]["amount"] == 1000 and calls[0]["currency"] == "USD"
    assert calls[0]["reference"] == id


async def test_3ds_and_verified_return_credit_only_once(client, workspace, acquiring, maker):
    id = await start(client)
    r = await client.post(f"/v1/billing/card/{id}/confirm", headers=OWNER, json=confirmation())
    assert r.status_code == 200, r.text
    assert r.json()["next_action_url"] == "https://app.nuvion.dev/sessions/test-3ds"
    assert await balance(maker, workspace) == 10
    # Query params from a redirect are not payment evidence.
    assert (await client.get(f"/v1/billing/card/{id}?status=completed&amount=1000", headers=OWNER)).json()[
        "status"
    ] == "pending"
    intent = next(iter(acquiring["intents"].values()))
    intent["status"] = "completed"
    intent["intent_action"] = acquiring["action"](intent, "completed")
    body, headers = signed(intent)
    results = await asyncio.gather(
        client.post("/v1/webhooks/nuvion", content=body, headers=headers),
        client.get(f"/v1/billing/card/{id}", headers=OWNER),
    )
    assert all(r.status_code == 200 for r in results), [r.text for r in results]
    assert await balance(maker, workspace) == Decimal("13.70")
    for _ in range(2):
        assert (await client.post("/v1/webhooks/nuvion", content=body, headers=headers)).status_code == 200
    assert await balance(maker, workspace) == Decimal("13.70")
    async with maker() as db:
        txs = (
            (await db.execute(select(CreditTransaction).where(CreditTransaction.ref == f"checkout:{id}")))
            .scalars()
            .all()
        )
        assert len(txs) == 1
        assert "encrypted_data" not in (await db.get(Checkout, id)).payment_context


async def test_immediate_paid_card_settles_verified_result(client, workspace, acquiring, maker):
    acquiring["mode"] = "paid"
    id = await start(client)
    result = await client.post(f"/v1/billing/card/{id}/confirm", headers=OWNER, json=confirmation())
    assert result.json()["status"] == "paid"
    assert await balance(maker, workspace) == Decimal("13.70")


async def test_decline_never_adds_credits(client, workspace, acquiring, maker):
    acquiring["mode"] = "declined"
    id = await start(client)
    r = await client.post(f"/v1/billing/card/{id}/confirm", headers=OWNER, json=confirmation())
    assert r.json()["status"] == "failed"
    assert await balance(maker, workspace) == 10
    await client.post(f"/v1/billing/card/{id}/confirm", headers=OWNER, json=confirmation())
    assert acquiring["confirmations"] == 1


async def test_double_confirm_and_network_timeout_do_not_recharge(client, workspace, acquiring):
    id = await start(client)
    acquiring["timeout"] = True
    r = await client.post(f"/v1/billing/card/{id}/confirm", headers=OWNER, json=confirmation())
    assert r.status_code == 503
    assert (await client.get(f"/v1/billing/card/{id}", headers=OWNER)).json()["provider_status"] == "confirming"
    r = await client.post(f"/v1/billing/card/{id}/confirm", headers=OWNER, json=confirmation())
    assert r.status_code == 200 and acquiring["confirmations"] == 1
    assert (await client.post(f"/v1/billing/card/{id}/cancel", headers=OWNER)).json()["status"] == "expired"


@pytest.mark.parametrize(
    "field,value",
    [
        ("currency", "NGN"),
        ("amount", 1),
        ("amount", None),
        ("account_id", "other-account"),
        ("entity_id", "other-entity"),
        ("reference", "other-checkout"),
    ],
)
async def test_verification_rejects_mismatches(client, workspace, acquiring, maker, field, value):
    id = await start(client)
    acquiring["mode"] = "paid"
    # Confirm creates a completed intent, then the online read is tampered by the test.
    acquiring["mismatch"] = (field, value)
    r = await client.post(f"/v1/billing/card/{id}/confirm", headers=OWNER, json=confirmation())
    assert r.status_code == 409
    assert await balance(maker, workspace) == 10


@pytest.mark.parametrize("variation", ["wrong", "missing", "stale", "future"])
async def test_invalid_webhook_signatures_never_credit(client, workspace, acquiring, maker, variation):
    await start(client)
    intent = next(iter(acquiring["intents"].values()))
    time = datetime.now(UTC) + timedelta(minutes=-10 if variation == "stale" else 10 if variation == "future" else 0)
    body, headers = signed(intent, timestamp=time.isoformat(), bad=variation == "wrong")
    if variation == "missing":
        headers = {}
    assert (await client.post("/v1/webhooks/nuvion", content=body, headers=headers)).status_code == 401
    assert await balance(maker, workspace) == 10


async def test_signed_completed_event_must_match_online_status(client, workspace, acquiring, maker):
    id = await start(client)
    intent = next(iter(acquiring["intents"].values()))
    fake = {**intent, "status": "completed"}
    body, headers = signed(fake)
    r = await client.post("/v1/webhooks/nuvion", content=body, headers=headers)
    assert r.json()["result"] == "pending"
    assert await balance(maker, workspace) == 10
    # The legacy endpoint cannot bypass online verification either.
    assert (await client.post("/v1/webhooks/billing", content=body, headers=headers)).json()["result"] == "pending"
    assert (await client.get(f"/v1/billing/card/{id}", headers=OWNER)).json()["status"] == "pending"


async def test_no_missing_webhook_lost_credit_and_verified_action_backoff(client, workspace, acquiring, maker):
    id = await start(client)
    await client.post(f"/v1/billing/card/{id}/confirm", headers=OWNER, json=confirmation())
    acquiring["mode"] = "verify-paid"
    async with maker() as db:
        co = await db.get(Checkout, id)
        co.last_verified_at = datetime.now(UTC) - timedelta(seconds=20)
        await db.commit()
    assert await payments.reconcile_pending() == 1
    assert await payments.reconcile_pending() == 0
    assert await balance(maker, workspace) == Decimal("13.70")
    assert acquiring["verify_calls"] == 1


async def test_cross_workspace_and_plaintext_requests_rejected(client, workspace, acquiring, maker):
    id = await start(client)
    async with maker() as db:
        other = Workspace(name="Other")
        db.add(other)
        await db.flush()
        db.add(User(email="other@example.com", workspace_id=other.id))
        await db.commit()
    headers = {"Authorization": "Bearer dev:other@example.com"}
    assert (await client.get(f"/v1/billing/card/{id}", headers=headers)).status_code == 404
    assert (
        await client.post(f"/v1/billing/card/{id}/confirm", headers=headers, json=confirmation())
    ).status_code == 404
    assert (await client.get("/v1/billing/checkouts", headers=headers)).json() == []
    raw = {**confirmation(), "card_number": "4111111111111111", "cvv": "123"}
    assert (await client.post(f"/v1/billing/card/{id}/confirm", headers=OWNER, json=raw)).status_code == 422
    assert acquiring["confirmations"] == 0


async def test_payment_can_finish_after_manual_checkout_pause(client, workspace, acquiring, maker, monkeypatch):
    id = await start(client)
    acquiring["mode"] = "paid"
    monkeypatch.setattr(get_settings(), "billing_provider", "manual")
    assert (await client.post("/v1/billing/checkout", headers=OWNER, json={"amount_usd": "10"})).status_code == 409
    assert (await client.post(f"/v1/billing/card/{id}/confirm", headers=OWNER, json=confirmation())).json()[
        "status"
    ] == "paid"
    assert await balance(maker, workspace) == Decimal("13.70")


@pytest.mark.parametrize(
    "field,value",
    [
        ("status", "pending"),
        ("charge_amount", 999),
        ("refunded_amount", 100),
        ("currency", "CAD"),
        ("payment_intent_id", "foreign-intent"),
    ],
)
async def test_nested_charge_must_also_be_completed_and_match(client, workspace, acquiring, maker, field, value):
    await start(client)
    intent = next(iter(acquiring["intents"].values()))
    intent["status"] = "completed"
    intent["intent_action"] = acquiring["action"](intent, "completed")
    intent["intent_action"][field] = value
    body, headers = signed(intent)
    assert (await client.post("/v1/webhooks/nuvion", content=body, headers=headers)).status_code == 409
    assert await balance(maker, workspace) == 10


async def test_untrusted_authentication_redirect_is_not_returned(client, workspace, acquiring):
    id = await start(client)
    intent = next(iter(acquiring["intents"].values()))
    intent["status"] = "processing"
    intent["intent_action"] = acquiring["action"](intent, "pending_user_action")
    intent["intent_action"]["next_action"]["url"] = "https://app.nuvion.dev.attacker.example/session"
    result = await client.get(f"/v1/billing/card/{id}", headers=OWNER)
    assert result.status_code == 503 and "attacker" not in result.text


async def test_webhook_health_bootstraps_without_payment_settings(client, workspace, maker, monkeypatch):
    monkeypatch.setattr(get_settings(), "nuvion_api_key", "")
    monkeypatch.setattr(get_settings(), "nuvion_webhook_secret", "")
    response = await client.post("/v1/webhooks/nuvion", json={"event": "webhook.health", "data": {}})
    assert response.status_code == 200 and response.json() == {"status": "ok"}
    assert await balance(maker, workspace) == 10
    financial = await client.post("/v1/webhooks/nuvion", json={"event": "payment_intent.completed", "data": {}})
    assert financial.status_code == 503
    assert await balance(maker, workspace) == 10


@pytest.fixture
async def naira(acquiring, monkeypatch):
    settings = get_settings()
    monkeypatch.setattr(settings, "nuvion_ngn_account_id", "test-ngn-account")
    monkeypatch.setattr(settings, "nuvion_ngn_card_enabled", True)
    monkeypatch.setattr(settings, "nuvion_ngn_bank_enabled", True)
    monkeypatch.setattr(settings, "ngn_per_usd", Decimal("1400"))
    usd = registry.get_nuvion_billing()
    registry.override(nuvion_ngn_billing=NuvionBilling(usd.client, currency="NGN"))
    return acquiring


async def ngn_checkout(client, method="card", rate="1400"):
    return await client.post(
        "/v1/billing/checkout",
        headers=OWNER,
        json={"amount_usd": "10", "currency": "NGN", "payment_method": method, "ngn_per_usd": rate},
    )


async def bank_transfer(client, maker, state):
    response = await ngn_checkout(client, "bank_transfer")
    assert response.status_code == 200, response.text
    id = response.json()["checkout_id"]
    async with maker() as db:
        co = await db.get(Checkout, id)
        created = int(payments.utc(co.created_at).timestamp() * 1000) + 1000
    transfer = {
        "id": "transfer-test",
        "account_id": "test-ngn-account",
        "entity_id": "test-entity",
        "currency": "NGN",
        "amount": 1400000,
        "status": "successful",
        "type": "inflow",
        "payment_type": "bank-transfer",
        "narration": "CF" + id,
        "created": created,
    }
    state["transfers"][transfer["id"]] = transfer
    return id, transfer


async def test_ngn_quote_and_stale_rate(client, workspace, naira, monkeypatch):
    methods = (await client.get("/v1/billing/payment-methods", headers=OWNER)).json()
    assert methods == {"ngn_per_usd": "1400", "usd_card": True, "ngn_card": True, "ngn_bank_transfer": True}
    options = (await client.get("/v1/billing/options", headers=OWNER)).json()
    assert Decimal(next(o for o in options if Decimal(o["amount_usd"]) == 10)["amount_ngn"]) == 14000
    assert (await ngn_checkout(client, rate="1300")).status_code == 409
    assert (
        await client.post("/v1/billing/checkout", headers=OWNER, json={"amount_usd": "10", "currency": "NGN"})
    ).status_code == 409
    monkeypatch.setattr(get_settings(), "nuvion_ngn_card_enabled", False)
    assert (await ngn_checkout(client)).status_code == 409
    assert not naira["intents"]


async def test_ngn_card_amount_and_snapshot_settlement(client, workspace, naira, maker, monkeypatch):
    response = await ngn_checkout(client)
    assert response.status_code == 200, response.text
    id = response.json()["checkout_id"]
    response = await client.get(f"/v1/billing/card/{id}", headers=OWNER)
    assert response.json()["currency"] == "NGN"
    assert Decimal(response.json()["amount"]) == 14000
    intent = next(iter(naira["intents"].values()))
    assert intent["amount"] == 1400000 and intent["account_id"] == "test-ngn-account"
    monkeypatch.setattr(get_settings(), "ngn_per_usd", Decimal("1600"))
    naira["mode"] = "paid"
    response = await client.post(f"/v1/billing/card/{id}/confirm", headers=OWNER, json=confirmation())
    assert response.status_code == 200, response.text
    assert response.json()["status"] == "paid" and Decimal(response.json()["amount"]) == 14000
    assert await balance(maker, workspace) == Decimal("13.70")
    body, headers = signed(intent)
    assert (await client.post("/v1/webhooks/nuvion", content=body, headers=headers)).status_code == 200
    assert await balance(maker, workspace) == Decimal("13.70")


async def test_ngn_card_rejects_usd_amount_disguised_as_naira(client, workspace, naira, maker):
    id = (await ngn_checkout(client)).json()["checkout_id"]
    assert (await client.get(f"/v1/billing/card/{id}", headers=OWNER)).status_code == 200
    intent = next(iter(naira["intents"].values()))
    intent["amount"] = 1000
    intent["status"] = "completed"
    intent["intent_action"] = naira["action"](intent, "completed")
    body, headers = signed(intent)
    assert (await client.post("/v1/webhooks/nuvion", content=body, headers=headers)).status_code == 409
    assert await balance(maker, workspace) == 10


async def test_bank_transfer_online_verification_and_idempotency(client, workspace, naira, maker, monkeypatch):
    id, transfer = await bank_transfer(client, maker, naira)
    monkeypatch.setattr(get_settings(), "ngn_per_usd", Decimal("1600"))
    body, headers = signed(transfer, event="inflows.completed")
    for _ in range(2):
        r = await client.post("/v1/webhooks/nuvion", content=body, headers=headers)
        assert r.status_code == 200, r.text
    status = await client.get(f"/v1/billing/bank/{id}", headers=OWNER)
    assert status.json()["status"] == "paid"
    assert Decimal(status.json()["amount_ngn"]) == 14000
    assert await balance(maker, workspace) == Decimal("13.70")
    history = (await client.get("/v1/billing/checkouts", headers=OWNER)).json()
    assert history[0]["currency"] == "NGN" and history[0]["payment_method"] == "bank_transfer"


@pytest.mark.parametrize(
    ("field", "value"),
    [
        ("amount", 1000),
        ("amount", 1400001),
        ("currency", "USD"),
        ("account_id", "another-account"),
        ("entity_id", "another-entity"),
        ("status", "pending"),
        ("type", "outflow"),
        ("payment_type", "card-acq"),
        ("narration", "CFno-match"),
        ("created", 1),
    ],
)
async def test_bank_never_trusts_signed_event_over_provider_state(client, workspace, naira, maker, field, value):
    id, transfer = await bank_transfer(client, maker, naira)
    body, headers = signed(copy.deepcopy(transfer), event="inflows.completed")
    transfer[field] = value
    response = await client.post("/v1/webhooks/nuvion", content=body, headers=headers)
    assert response.status_code == 200, response.text
    assert await balance(maker, workspace) == 10
    async with maker() as db:
        assert (await db.get(Checkout, id)).status == "pending"


async def test_bank_reconciliation_recovers_missing_webhook(client, workspace, naira, maker):
    id, _ = await bank_transfer(client, maker, naira)
    assert await payments.reconcile_pending() == 1
    assert await payments.reconcile_pending() == 0
    assert await balance(maker, workspace) == Decimal("13.70")
    assert (await client.get(f"/v1/billing/card/{id}", headers=OWNER)).status_code == 404


async def test_bank_ownership_and_forged_return_do_not_credit(client, workspace, naira, maker):
    response = await ngn_checkout(client, "bank_transfer")
    id = response.json()["checkout_id"]
    async with maker() as db:
        other = Workspace(name="Other", credit_balance=0)
        db.add(other)
        await db.flush()
        db.add(User(email="other@acme.test", workspace_id=other.id))
        await db.commit()
    assert (
        await client.get(f"/v1/billing/bank/{id}", headers={"Authorization": "Bearer dev:other@acme.test"})
    ).status_code == 404
    status = await client.get(f"/v1/billing/bank/{id}?status=successful&amount=1400000", headers=OWNER)
    assert status.json()["status"] == "pending"
    assert await balance(maker, workspace) == 10


@pytest.mark.parametrize("currency,expected_minor", [("USD", 100), ("NGN", 140000)])
async def test_one_dollar_card_package_verifies_and_credits_once(
    client, workspace, naira, maker, currency, expected_minor
):
    response = await client.post(
        "/v1/billing/checkout",
        headers=OWNER,
        json={"amount_usd": "1", "currency": currency, "payment_method": "card", "ngn_per_usd": "1400"},
    )
    assert response.status_code == 200, response.text
    id = response.json()["checkout_id"]
    status = await client.get(f"/v1/billing/card/{id}", headers=OWNER)
    assert status.status_code == 200, status.text
    assert Decimal(status.json()["credits"]) == Decimal("0.37")
    assert Decimal(status.json()["amount"]) == (Decimal("1") if currency == "USD" else Decimal("1400"))
    intent = next(iter(naira["intents"].values()))
    assert intent["amount"] == expected_minor
    assert await balance(maker, workspace) == 10
    naira["mode"] = "paid"
    response = await client.post(f"/v1/billing/card/{id}/confirm", headers=OWNER, json=confirmation())
    assert response.status_code == 200 and response.json()["status"] == "paid", response.text
    body, headers = signed(intent)
    for _ in range(2):
        assert (await client.post("/v1/webhooks/nuvion", content=body, headers=headers)).status_code == 200
    assert await balance(maker, workspace) == Decimal("10.37")


async def test_one_dollar_naira_bank_transfer_verifies_amount_and_credits_once(client, workspace, naira, maker):
    response = await client.post(
        "/v1/billing/checkout",
        headers=OWNER,
        json={"amount_usd": "1", "currency": "NGN", "payment_method": "bank_transfer", "ngn_per_usd": "1400"},
    )
    assert response.status_code == 200, response.text
    id = response.json()["checkout_id"]
    async with maker() as db:
        co = await db.get(Checkout, id)
        created = int(payments.utc(co.created_at).timestamp() * 1000) + 1000
        assert co.credits == Decimal("0.37")
    transfer = {
        "id": "one-dollar-transfer",
        "account_id": "test-ngn-account",
        "entity_id": "test-entity",
        "currency": "NGN",
        "amount": 140000,
        "status": "successful",
        "type": "inflow",
        "payment_type": "bank-transfer",
        "narration": "CF" + id,
        "created": created,
    }
    naira["transfers"][transfer["id"]] = transfer
    body, headers = signed(transfer, event="inflows.completed")
    for _ in range(2):
        result = await client.post("/v1/webhooks/nuvion", content=body, headers=headers)
        assert result.status_code == 200, result.text
    status = (await client.get(f"/v1/billing/bank/{id}", headers=OWNER)).json()
    assert status["status"] == "paid" and Decimal(status["amount_ngn"]) == 1400
    assert await balance(maker, workspace) == Decimal("10.37")


async def test_rejected_card_request_can_retry_without_storing_card_or_provider_body(
    client, workspace, acquiring, maker, caplog
):
    id = await start(client)
    acquiring["reject_code"] = "error_acquiring_decryption_failed"
    r = await client.post(f"/v1/billing/card/{id}/confirm", headers=OWNER, json=confirmation())
    assert r.status_code == 503
    assert "encryption" in r.json()["detail"]
    current = (await client.get(f"/v1/billing/card/{id}", headers=OWNER)).json()
    assert current["can_retry_confirmation"] and current["provider_status"] == "requires_action"
    assert current["payment_error"]["code"] == "error_acquiring_decryption_failed"
    assert current["payment_error"]["request_id"] == "test-request-id"
    assert "SENSITIVE RAW PROCESSOR" not in caplog.text
    assert "encrypted_data" not in str(current["payment_error"])
    async with maker() as db:
        assert (await db.get(Checkout, id)).confirmation_started_at is None
    acquiring["reject_code"] = None
    acquiring["mode"] = "paid"
    assert (await client.post(f"/v1/billing/card/{id}/confirm", headers=OWNER, json=confirmation())).json()[
        "status"
    ] == "paid"
    assert await balance(maker, workspace) == Decimal("13.70")


async def test_ambiguous_timeout_recovers_only_after_delay_and_no_actions(client, workspace, acquiring, maker):
    id = await start(client)
    acquiring["timeout"] = True
    assert (await client.post(f"/v1/billing/card/{id}/confirm", headers=OWNER, json=confirmation())).status_code == 503
    current = (await client.get(f"/v1/billing/card/{id}", headers=OWNER)).json()
    assert not current["can_retry_confirmation"] and current["provider_status"] == "confirming"
    async with maker() as db:
        co = await db.get(Checkout, id)
        co.confirmation_started_at = datetime.now(UTC) - timedelta(minutes=3)
        await db.commit()
    current = (await client.get(f"/v1/billing/card/{id}", headers=OWNER)).json()
    assert current["can_retry_confirmation"] and current["provider_status"] == "requires_action"
    assert acquiring["confirmations"] == 1
    assert await balance(maker, workspace) == 10


async def test_pending_3ds_action_never_reopens_card_submission(client, workspace, acquiring, maker):
    id = await start(client)
    assert (await client.post(f"/v1/billing/card/{id}/confirm", headers=OWNER, json=confirmation())).status_code == 200
    intent = next(iter(acquiring["intents"].values()))
    intent["status"] = "requires_action"
    async with maker() as db:
        co = await db.get(Checkout, id)
        co.confirmation_started_at = datetime.now(UTC) - timedelta(minutes=3)
        await db.commit()
    current = (await client.get(f"/v1/billing/card/{id}", headers=OWNER)).json()
    assert not current["can_retry_confirmation"]
    assert acquiring["confirmations"] == 1


async def test_unmatched_receipt_claim_admin_matching_and_duplicate_callback(client, workspace, naira, maker):
    from app.models import AuditLog, BankReceipt
    from tests.conftest import OPS

    id, transfer = await bank_transfer(client, maker, naira)
    transfer["narration"] = "Bank replaced the description"
    transfer["unique_reference"] = "100004261030154115175873657637"
    body, headers = signed(transfer, event="inflows.completed")
    r = await client.post("/v1/webhooks/nuvion", content=body, headers=headers)
    assert r.json()["result"] == "unmatched_reference"
    assert await balance(maker, workspace) == 10
    assert (await client.get("/v1/admin/payment-reconciliation", headers=OWNER)).status_code == 403
    claim = await client.post(
        f"/v1/billing/bank/{id}/claim", headers=OWNER, json={"reference": transfer["unique_reference"]}
    )
    assert claim.status_code == 200 and claim.json()["status"] == "pending_review", claim.text
    assert await balance(maker, workspace) == 10
    assert (await client.get(f"/v1/billing/bank/{id}", headers=OWNER)).json()["claim"]["status"] == "pending_review"
    report = (await client.get("/v1/admin/payment-reconciliation", headers=OPS)).json()
    receipt = report["receipts"][0]
    assert receipt["status"] == "unmatched"
    match = {
        "checkout_id": id,
        "ownership_confirmed": True,
        "reason": "Verified bank receipt and payer ownership for this purchase.",
    }
    path = f"/v1/admin/payment-reconciliation/receipts/{receipt['id']}/match"
    assert (await client.post(path, headers=OWNER, json=match)).status_code == 403
    assert (await client.post(path, headers=OPS, json={**match, "ownership_confirmed": False})).status_code == 422
    for _ in range(2):
        r = await client.post(path, headers=OPS, json=match)
        assert r.status_code == 200 and r.json()["status"] == "paid", r.text
    assert await balance(maker, workspace) == Decimal("13.70")
    r = await client.post("/v1/webhooks/nuvion", content=body, headers=headers)
    assert r.json()["result"] == "duplicate"
    assert await balance(maker, workspace) == Decimal("13.70")
    async with maker() as db:
        assert (await db.execute(select(BankReceipt))).scalar_one().checkout_id == id
        audits = (
            (await db.execute(select(AuditLog).where(AuditLog.action == "payment.bank_manually_matched")))
            .scalars()
            .all()
        )
        assert len(audits) == 1 and audits[0].actor == "ops@example.com"
        assert await ledger.ledger_sum(db, workspace) == Decimal("13.70")


async def test_receipt_cannot_credit_two_orders_or_wrong_amount(client, workspace, naira, maker):
    from tests.conftest import OPS

    id, transfer = await bank_transfer(client, maker, naira)
    # Create a second valid purchase before the inflow timestamp.
    second = (await ngn_checkout(client, "bank_transfer")).json()["checkout_id"]
    transfer["created"] = int(datetime.now(UTC).timestamp() * 1000) + 1000
    transfer["narration"] = "Missing checkout narration"
    transfer["unique_reference"] = "bank-receipt-unique-reference"
    assert (await client.post("/v1/admin/payment-reconciliation/sync", headers=OPS)).status_code == 200
    report = (await client.get("/v1/admin/payment-reconciliation", headers=OPS)).json()
    path = f"/v1/admin/payment-reconciliation/receipts/{report['receipts'][0]['id']}/match"
    body = {
        "checkout_id": id,
        "ownership_confirmed": True,
        "reason": "Verified payer and receipt against the selected purchase.",
    }
    transfer["amount"] += 1
    assert (await client.post(path, headers=OPS, json=body)).status_code == 409
    assert await balance(maker, workspace) == 10
    transfer["amount"] -= 1
    assert (await client.post(path, headers=OPS, json=body)).status_code == 200
    r = await client.post(path, headers=OPS, json={**body, "checkout_id": second})
    assert r.status_code == 409, r.text
    assert await balance(maker, workspace) == Decimal("13.70")


async def test_bank_claim_is_scoped_to_customer_and_requires_exact_reference(client, workspace, naira, maker):
    id, transfer = await bank_transfer(client, maker, naira)
    transfer["narration"] = "Bank removed the narration"
    transfer["unique_reference"] = "bank-transaction-reference"
    assert (
        await client.post(f"/v1/billing/bank/{id}/claim", headers=OWNER, json={"reference": "wrong-reference"})
    ).status_code == 409
    async with maker() as db:
        ws = Workspace(name="Other payer")
        db.add(ws)
        await db.flush()
        db.add(User(email="payer-other@example.com", workspace_id=ws.id))
        await db.commit()
    other = {"Authorization": "Bearer dev:payer-other@example.com"}
    assert (
        await client.post(
            f"/v1/billing/bank/{id}/claim", headers=other, json={"reference": transfer["unique_reference"]}
        )
    ).status_code == 404
    assert await balance(maker, workspace) == 10


async def test_parallel_receipt_matches_can_only_fund_one_purchase(client, workspace, naira, maker):
    import asyncio

    from tests.conftest import OPS

    first, transfer = await bank_transfer(client, maker, naira)
    second = (await ngn_checkout(client, "bank_transfer")).json()["checkout_id"]
    transfer["created"] = int(datetime.now(UTC).timestamp() * 1000) + 1000
    transfer["narration"] = "Narration replaced by bank"
    assert (await client.post("/v1/admin/payment-reconciliation/sync", headers=OPS)).status_code == 200
    report = (await client.get("/v1/admin/payment-reconciliation", headers=OPS)).json()
    path = f"/v1/admin/payment-reconciliation/receipts/{report['receipts'][0]['id']}/match"
    body = {"ownership_confirmed": True, "reason": "Verified payer ownership with the supplied bank receipt."}
    assert (
        await client.post(path, headers=OPS, json={**body, "checkout_id": first, "reason": " " * 12})
    ).status_code == 422
    results = await asyncio.gather(
        client.post(path, headers=OPS, json={**body, "checkout_id": first}),
        client.post(path, headers=OPS, json={**body, "checkout_id": second}),
    )
    assert sorted(r.status_code for r in results) == [200, 409]
    assert await balance(maker, workspace) == Decimal("13.70")


async def test_one_dollar_bank_receipt_manual_match_grants_exact_credit(client, workspace, naira, maker):
    from tests.conftest import OPS

    r = await client.post(
        "/v1/billing/checkout",
        headers=OWNER,
        json={"amount_usd": "1", "currency": "NGN", "payment_method": "bank_transfer", "ngn_per_usd": "1400"},
    )
    id = r.json()["checkout_id"]
    transfer = {
        "id": "one-dollar-test-transfer",
        "account_id": "test-ngn-account",
        "entity_id": "test-entity",
        "currency": "NGN",
        "amount": 140000,
        "status": "successful",
        "type": "inflow",
        "payment_type": "bank-transfer",
        "narration": "Bank changed narration",
        "created": int(datetime.now(UTC).timestamp() * 1000) + 1000,
    }
    naira["transfers"][transfer["id"]] = transfer
    assert (await client.post("/v1/admin/payment-reconciliation/sync", headers=OPS)).status_code == 200
    report = (await client.get("/v1/admin/payment-reconciliation", headers=OPS)).json()
    path = f"/v1/admin/payment-reconciliation/receipts/{report['receipts'][0]['id']}/match"
    body = {
        "checkout_id": id,
        "ownership_confirmed": True,
        "reason": "Verified payer and the one dollar purchase receipt.",
    }
    for _ in range(2):
        r = await client.post(path, headers=OPS, json=body)
        assert r.status_code == 200 and Decimal(r.json()["credits"]) == Decimal("0.37"), r.text
    assert await balance(maker, workspace) == Decimal("10.37")


async def test_unknown_action_list_cannot_authorize_retry(acquiring, monkeypatch):
    billing = registry.get_nuvion_billing()

    async def unknown_response(*args, **kwargs):
        return {"unexpected_shape": []}

    monkeypatch.setattr(billing, "call", unknown_response)
    assert await billing.has_actions({"id": "test-intent", "intent_action": None}) is True


@pytest.mark.parametrize(("currency", "method"), [("USD", "card"), ("NGN", "card"), ("NGN", "bank_transfer")])
async def test_custom_credit_purchase_is_verified_and_settles_exact_quantity(
    client, workspace, naira, maker, currency, method
):
    quote = (await client.post("/v1/billing/custom-quote", headers=OWNER, json={"credits": "220"})).json()
    body = {
        "amount_usd": quote["amount_usd"],
        "custom_credits": quote["credits"],
        "custom_quote_version": quote["quote_version"],
        "currency": currency,
        "payment_method": method,
    }
    if currency == "NGN":
        body["ngn_per_usd"] = quote["ngn_per_usd"]
    response = await client.post("/v1/billing/checkout", headers=OWNER, json=body)
    assert response.status_code == 200, response.text
    id = response.json()["checkout_id"]
    if method == "bank_transfer":
        transfer = {
            "id": "custom-credit-transfer",
            "account_id": "test-ngn-account",
            "entity_id": "test-entity",
            "currency": "NGN",
            "amount": 83160000,
            "type": "inflow",
            "payment_type": "bank-transfer",
            "status": "successful",
            "narration": "CF" + id,
            "created": int(datetime.now(UTC).timestamp() * 1000) + 1000,
        }
        naira["transfers"][transfer["id"]] = transfer
        content, headers = signed(transfer, event="inflows.completed")
        for _ in range(2):
            r = await client.post("/v1/webhooks/nuvion", content=content, headers=headers)
            assert r.status_code == 200, r.text
    else:
        naira["mode"] = "paid"
        assert (await client.get(f"/v1/billing/card/{id}", headers=OWNER)).status_code == 200
        r = await client.post(f"/v1/billing/card/{id}/confirm", headers=OWNER, json=confirmation())
        assert r.status_code == 200 and r.json()["status"] == "paid", r.text
        assert (await client.get(f"/v1/billing/card/{id}", headers=OWNER)).json()["status"] == "paid"
    assert await balance(maker, workspace) == Decimal("230")
    async with maker() as db:
        co = await db.get(Checkout, id)
        assert co.credits == 220 and co.amount_usd == 594
        if currency == "NGN":
            assert Decimal(co.payment_context["amount_ngn"]) == 831600
        assert await ledger.ledger_sum(db, workspace) == Decimal("230")


async def test_transfer_mode_blocks_new_card_charges_but_settles_old_completed_payments(
    client, workspace, acquiring, maker, monkeypatch
):
    id = await start(client)
    monkeypatch.setattr(get_settings(), "bank_transfer_review_enabled", True)
    rejected = await client.post(f"/v1/billing/card/{id}/confirm", headers=OWNER, json=confirmation())
    assert rejected.status_code == 409
    assert acquiring["confirmations"] == 0
    status = (await client.get(f"/v1/billing/card/{id}", headers=OWNER)).json()
    assert status["card_payments_enabled"] is False
    assert status["can_retry_confirmation"] is False
    # A charge that already completed at the provider must not lose its credits during rollout.
    intent = next(iter(acquiring["intents"].values()))
    intent["status"] = "completed"
    intent["intent_action"] = acquiring["action"](intent, "completed")
    body, headers = signed(intent)
    for _ in range(2):
        response = await client.post("/v1/webhooks/nuvion", content=body, headers=headers)
        assert response.status_code == 200, response.text
    assert await balance(maker, workspace) == Decimal("13.70")
