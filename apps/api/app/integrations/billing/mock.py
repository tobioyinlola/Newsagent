"""Stand-in payment provider for local development and tests. Uses the same shape a real provider has:
a hosted checkout URL, and a webhook signed with HMAC-SHA256 over the raw body."""

import hashlib
import hmac
import json
from decimal import Decimal

from app.config import get_settings
from app.integrations.billing.base import BillingProvider, CheckoutSession, InvalidSignature, PaymentEvent

SIGNATURE_HEADER = "x-signature"


def sign(body: bytes, secret: str) -> str:
    return hmac.new(secret.encode(), body, hashlib.sha256).hexdigest()


class MockBilling(BillingProvider):
    name = "mock"

    def __init__(self, secret: str | None = None) -> None:
        self.secret = secret or get_settings().billing_webhook_secret or "dev-billing-secret"

    async def create_checkout(
        self, *, checkout_id: str, credits: Decimal, amount_usd: Decimal, description: str
    ) -> CheckoutSession:
        return CheckoutSession(
            url=f"{get_settings().app_base_url}/billing/pay/{checkout_id}", provider_ref=f"mock_{checkout_id}"
        )

    def parse_webhook(self, headers: dict[str, str], body: bytes) -> PaymentEvent:
        given = headers.get(SIGNATURE_HEADER, "")
        if not hmac.compare_digest(given, sign(body, self.secret)):  # constant-time compare
            raise InvalidSignature("bad signature")
        d = json.loads(body)
        return PaymentEvent(
            event_id=d["id"],
            checkout_id=d["checkout_id"],
            status=d["status"],
            amount_usd=Decimal(str(d["amount_usd"])) if d.get("amount_usd") is not None else None,
        )
