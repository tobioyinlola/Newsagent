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
    }

    def action(intent, status):
        return {
            "id": "action-" + intent["id"],
            "payment_intent_id": intent["id"],
            "status": status,
            "currency": "USD",
            "amount": intent["amount"],
            "charge_amount": intent["amount"],
            "refunded_amount": 0,
            "account_id": "test-account",
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
        if path == "/payment-intents" and req.method == "GET":
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
        elif path == "/intent-actions":
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
