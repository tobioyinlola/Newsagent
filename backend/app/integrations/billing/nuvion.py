"""Nuvion USD acquiring adapter. Never accepts or stores plaintext card details."""

import hashlib
import hmac
import json
import re
from datetime import UTC, datetime
from decimal import Decimal
from urllib.parse import urlsplit

import httpx
from cryptography.hazmat.primitives.asymmetric.rsa import RSAPublicKey
from cryptography.hazmat.primitives.serialization import load_pem_public_key

from app.config import get_settings
from app.integrations.billing.base import BillingProvider, CheckoutSession, InvalidSignature, PaymentEvent


class NuvionError(Exception):
    pass


class PaymentMismatch(NuvionError):
    pass


def configuration_problems(settings) -> list[str]:
    errors = []
    for name in (
        "nuvion_api_key",
        "nuvion_account_id",
        "nuvion_entity_id",
        "nuvion_public_key",
        "nuvion_webhook_secret",
    ):
        if not getattr(settings, name):
            errors.append(name.upper() + " is required for Nuvion payments")
    if settings.nuvion_webhook_secret and len(settings.nuvion_webhook_secret) < 24:
        errors.append("NUVION_WEBHOOK_SECRET must be at least 24 characters")
    if settings.nuvion_api_url.rstrip("/") not in {"https://api.nuvion.dev", "https://api.nuvion.co"}:
        errors.append("NUVION_API_URL must be the official sandbox or production API URL")
    if settings.environment == "production" and settings.nuvion_api_url.rstrip("/") != "https://api.nuvion.co":
        errors.append("Production payments require the production Nuvion API")
    if settings.nuvion_public_key:
        try:
            key = load_pem_public_key(settings.nuvion_public_key.replace("\\n", "\n").encode())
            if not isinstance(key, RSAPublicKey) or key.key_size < 2048:
                raise ValueError("invalid key")
        except (ValueError, TypeError):
            errors.append("NUVION_PUBLIC_KEY must be an RSA public PEM key of at least 2048 bits")
    return errors


class NuvionBilling(BillingProvider):
    name = "nuvion"

    def __init__(self, client: httpx.AsyncClient | None = None):
        s = get_settings()
        self.base_url = s.nuvion_api_url.rstrip("/")
        self.account_id, self.entity_id = s.nuvion_account_id, s.nuvion_entity_id
        self.secret = s.nuvion_webhook_secret
        self.public_key = s.nuvion_public_key.replace("\\n", "\n")
        self.client = client or httpx.AsyncClient(
            base_url=self.base_url,
            headers={"Authorization": f"Bearer {s.nuvion_api_key}"},
            timeout=20,
            follow_redirects=False,
        )

    @property
    def context(self) -> dict:
        return {"account_id": self.account_id, "entity_id": self.entity_id, "api_url": self.base_url}

    async def create_checkout(
        self, *, checkout_id: str, credits: Decimal, amount_usd: Decimal, description: str
    ) -> CheckoutSession:
        # Remote creation happens after this local checkout has committed, using its ID as the unique reference.
        return CheckoutSession(url=f"{get_settings().app_base_url}/billing/card/{checkout_id}", provider_ref="")

    async def call(self, method: str, path: str, *, body: dict | None = None, params: dict | None = None) -> dict:
        try:
            response = await self.client.request(method, path, json=body, params=params)
        except httpx.HTTPError as e:
            raise NuvionError(
                "Payment provider is temporarily unavailable. Check your payment status before trying again."
            ) from e
        if response.status_code == 409:
            return {"_conflict": True}
        if response.status_code >= 400:
            # Never echo processor response bodies, which can contain sensitive payment data.
            raise NuvionError(
                "The payment provider could not complete this request. Please check payment status or contact support."
            )
        try:
            result = response.json()
            if result.get("status") != "success" or not isinstance(result.get("data"), dict):
                raise ValueError("invalid response")
            return result["data"]
        except (ValueError, AttributeError) as e:
            raise NuvionError("Payment provider returned an invalid response. Please check payment status.") from e

    def check(self, intent: dict, checkout, *, require_bound: bool = True) -> None:
        expected = checkout.payment_context or self.context
        amount = intent.get("amount")
        if (
            expected != self.context
            or intent.get("account_id") != expected["account_id"]
            or intent.get("entity_id") != expected["entity_id"]
            or intent.get("currency") != "USD"
            or isinstance(amount, bool)
            or not isinstance(amount, int)
            or Decimal(amount) != checkout.amount_usd * 100
            or intent.get("reference") != checkout.id
            or not intent.get("id")
            or (require_bound and intent.get("id") != checkout.provider_ref)
        ):
            raise PaymentMismatch(
                "The payment details do not match this checkout. Contact support; no credits were added."
            )
        action = intent.get("intent_action")
        if intent.get("status") == "completed" and (
            not isinstance(action, dict)
            or action.get("status") != "completed"
            or action.get("payment_intent_id") != intent["id"]
            or action.get("currency") != "USD"
            or action.get("amount") != amount
            or action.get("account_id") != expected["account_id"]
            or action.get("entity_id") != expected["entity_id"]
            or action.get("reference") != checkout.id
            or action.get("category") != "collections"
            or action.get("payment_type") != "card-acq"
            or action.get("action") != "confirm"
            or action.get("charge_amount") != amount
            or action.get("refunded_amount", 0) != 0
        ):
            raise PaymentMismatch(
                "The completed charge does not match this purchase. Contact support; no credits were added."
            )

    async def ensure_intent(self, checkout) -> dict:
        if checkout.provider_ref:
            intent = await self.retrieve(checkout.provider_ref)
            self.check(intent, checkout)
            return intent
        found = await self.call(
            "GET",
            "/payment-intents",
            params={"reference": checkout.id, "account_id": self.account_id, "entity_id": self.entity_id},
        )
        items = found.get("items", [])
        if len(items) > 1:
            raise PaymentMismatch("Multiple payments match this checkout. Contact support.")
        if items:
            intent = await self.retrieve(items[0]["id"])
        else:
            intent = await self.call(
                "POST",
                "/payment-intents",
                body={
                    "currency": "USD",
                    "amount": int(checkout.amount_usd * 100),
                    "account_id": self.account_id,
                    "entity_id": self.entity_id,
                    "reference": checkout.id,
                    "description": f"Cover Founder: {checkout.credits} credits",
                },
            )
            if intent.get("_conflict"):
                found = await self.call(
                    "GET",
                    "/payment-intents",
                    params={"reference": checkout.id, "account_id": self.account_id, "entity_id": self.entity_id},
                )
                if len(found.get("items", [])) != 1:
                    raise NuvionError("The payment is being prepared. Please check its status again.")
                intent = await self.retrieve(found["items"][0]["id"])
        self.check(intent, checkout, require_bound=False)
        return intent

    async def retrieve(self, id: str) -> dict:
        return await self.call("GET", f"/payment-intents/{id}", params={"entity_id": self.entity_id})

    async def verify(self, intent: dict) -> dict:
        action = intent.get("intent_action") or {}
        if intent.get("status") == "processing" and action.get("id"):
            await self.call("POST", f"/intent-verifications/{action['id']}", body={"entity_id": self.entity_id})
            return await self.retrieve(intent["id"])
        return intent

    def redirect_url(self, intent: dict) -> str | None:
        action = intent.get("intent_action") or {}
        url = (action.get("next_action") or {}).get("url")
        if action.get("status") != "pending_user_action" or not url:
            return None
        parsed = urlsplit(url)
        if (
            parsed.scheme != "https"
            or parsed.hostname not in {"app.nuvion.co", "app.nuvion.dev"}
            or parsed.username
            or parsed.port not in {None, 443}
        ):
            raise NuvionError("The authentication redirect was invalid. Contact support.")
        return url

    def signed_event(self, headers: dict[str, str], body: bytes) -> dict:
        timestamp = headers.get("x-nuvion-event-timestamp", "")
        signature = headers.get("x-nuvion-event-signature", "")
        try:
            instant = datetime.fromisoformat(timestamp.replace("Z", "+00:00"))
            age = (datetime.now(UTC) - instant).total_seconds()
        except (ValueError, TypeError) as e:
            raise InvalidSignature("Invalid timestamp") from e
        if not self.secret or not re.fullmatch(r"[0-9a-f]{64}", signature) or not headers.get("x-nuvion-event-id") or age > 300 or age < -60:
            raise InvalidSignature("Invalid signature")
        expected = hmac.new(self.secret.encode(), timestamp.encode() + b"." + body, hashlib.sha256).hexdigest()
        if not hmac.compare_digest(signature, expected):
            raise InvalidSignature("Invalid signature")
        return json.loads(body)

    def parse_webhook(self, headers: dict[str, str], body: bytes) -> PaymentEvent:
        # Signature alone is never sufficient for a wallet grant: the route retrieves the current intent online.
        raise InvalidSignature("Nuvion payments require online verification")
