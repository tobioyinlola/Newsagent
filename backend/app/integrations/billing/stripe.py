"""Stripe Checkout adapter (hosted payment page). Card details never reach this API: the customer pays on Stripe's page.

Credits are granted only from a signature-verified webhook or from a server-to-Stripe lookup, never from the browser return.
No SDK: three plain HTTPS calls and one HMAC check, so there is nothing extra to keep up to date."""

import hashlib
import hmac
import time
from decimal import Decimal

import httpx

from app.config import get_settings
from app.integrations.billing.base import InvalidSignature

API = "https://api.stripe.com/v1"
TOLERANCE_S = 300  # webhook timestamps older than this are refused (replay protection)


class StripeError(Exception):
    def __init__(self, message: str, *, code: str = "provider_unavailable", http_status: int | None = None):
        super().__init__(message)
        self.code, self.http_status = code, http_status


def enabled(settings=None) -> bool:
    return bool((settings or get_settings()).stripe_secret_key)


def sandbox(settings=None) -> bool:
    """True with a test key (sk_test_...), the Stripe sandbox. Nothing is charged for real."""
    return (settings or get_settings()).stripe_secret_key.startswith(("sk_test_", "rk_test_"))


def configuration_problems(settings) -> list[str]:
    if not settings.stripe_secret_key:
        return []
    out = []
    if not settings.stripe_secret_key.startswith(("sk_test_", "sk_live_", "rk_test_", "rk_live_")):
        out.append("STRIPE_SECRET_KEY must be a Stripe secret or restricted key (sk_test_..., sk_live_...)")
    if not settings.stripe_webhook_secret.startswith("whsec_"):
        out.append("STRIPE_WEBHOOK_SECRET is required with Stripe and must start with whsec_")
    if not settings.is_local and settings.stripe_api_url.rstrip("/") != API:
        out.append("STRIPE_API_URL must be Stripe's own API outside local development")
    if settings.environment == "production" and sandbox(settings):
        out.append("Production payments need a live Stripe key (sk_live_...), not a test key")
    return out


def sign(body: bytes, secret: str, timestamp: int | None = None) -> str:
    """The Stripe-Signature header value for `body`. Used by tests and local tools to play Stripe's part."""
    t = int(timestamp if timestamp is not None else time.time())
    digest = hmac.new(secret.encode(), f"{t}.".encode() + body, hashlib.sha256).hexdigest()
    return f"t={t},v1={digest}"


def cents(amount_usd: Decimal) -> int:
    return int((Decimal(amount_usd) * 100).to_integral_value())


def session_amount_usd(session: dict) -> Decimal | None:
    """What Stripe actually took, in dollars, or None when the session has no amount or is not in USD."""
    if str(session.get("currency", "")).lower() != "usd" or session.get("amount_total") is None:
        return None
    return Decimal(int(session["amount_total"])) / 100


class StripeBilling:
    name = "stripe"

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        s = get_settings()
        self.secret = s.stripe_webhook_secret
        self.sandbox = sandbox(s)
        self.client = client or httpx.AsyncClient(
            base_url=s.stripe_api_url.rstrip("/"),
            headers={"Authorization": f"Bearer {s.stripe_secret_key}", "Stripe-Version": "2024-06-20"},
            timeout=httpx.Timeout(20.0, connect=5.0),
        )

    async def _call(
        self, method: str, path: str, *, data: dict | None = None, idempotency_key: str | None = None
    ) -> dict:
        headers = {"Idempotency-Key": idempotency_key} if idempotency_key else {}
        try:
            r = await self.client.request(method, path, data=data, headers=headers)
        except httpx.HTTPError as e:
            raise StripeError("Card payments are temporarily unavailable. Please try again.") from e
        try:
            body = r.json()
        except ValueError:
            body = {}
        if r.status_code >= 400:
            err = body.get("error", {}) if isinstance(body, dict) else {}
            raise StripeError(
                err.get("message") or "Card payments are temporarily unavailable. Please try again.",
                code=err.get("code") or "provider_error",
                http_status=r.status_code,
            )
        return body

    async def create_session(
        self,
        *,
        checkout_id: str,
        amount_usd: Decimal,
        credits: Decimal,
        description: str,
        email: str | None,
        return_base: str,
    ) -> dict:
        """A hosted Checkout Session for exactly `amount_usd`. Our checkout id rides along so the webhook can find its row."""
        data = {
            "mode": "payment",
            "client_reference_id": checkout_id,
            "metadata[checkout_id]": checkout_id,
            "metadata[credits]": str(credits),
            "payment_intent_data[metadata][checkout_id]": checkout_id,
            "line_items[0][quantity]": "1",
            "line_items[0][price_data][currency]": "usd",
            "line_items[0][price_data][unit_amount]": str(cents(amount_usd)),
            "line_items[0][price_data][product_data][name]": description,
            "success_url": f"{return_base}/billing/stripe/{checkout_id}?paid=1",
            "cancel_url": f"{return_base}/billing/stripe/{checkout_id}?cancelled=1",
            "expires_at": str(int(time.time()) + 3600),
        }
        if email:
            data["customer_email"] = email
        return await self._call("POST", "/checkout/sessions", data=data, idempotency_key=f"checkout-{checkout_id}")

    async def retrieve(self, session_id: str) -> dict:
        return await self._call("GET", f"/checkout/sessions/{session_id}")

    async def retrieve_payment_intent(self, intent_id: str) -> dict:
        """The payment behind a charge or dispute; its metadata carries our checkout id (set when the checkout was created)."""
        return await self._call("GET", f"/payment_intents/{intent_id}")

    async def expire(self, session_id: str) -> dict:
        return await self._call("POST", f"/checkout/sessions/{session_id}/expire")

    def verify_webhook(self, headers: dict[str, str], body: bytes, *, now: float | None = None) -> dict:
        """Check the Stripe-Signature header over the RAW body and return the parsed event. Raises InvalidSignature."""
        import json

        header = headers.get("stripe-signature", "")
        parts = [p.split("=", 1) for p in header.split(",") if "=" in p]
        stamps = [v for k, v in parts if k == "t"]
        sigs = [v for k, v in parts if k == "v1"]
        if not self.secret or len(stamps) != 1 or not sigs or not stamps[0].isdigit():
            raise InvalidSignature("missing or malformed signature")
        expected = hmac.new(self.secret.encode(), f"{stamps[0]}.".encode() + body, hashlib.sha256).hexdigest()
        if not any(hmac.compare_digest(expected, s) for s in sigs):  # constant-time compare
            raise InvalidSignature("bad signature")
        if abs((now if now is not None else time.time()) - int(stamps[0])) > TOLERANCE_S:
            raise InvalidSignature("signature timestamp outside tolerance")
        event = json.loads(body)
        if not isinstance(event, dict):
            raise ValueError("malformed event")
        return event
