from abc import ABC, abstractmethod
from dataclasses import dataclass
from decimal import Decimal


class InvalidSignature(Exception):
    pass


@dataclass
class CheckoutSession:
    url: str
    provider_ref: str


@dataclass
class PaymentEvent:
    event_id: str  # provider's unique id for this delivery; used for idempotency
    checkout_id: str  # OUR checkout id, round-tripped through the provider
    status: str  # paid | failed | expired
    amount_usd: Decimal | None = None


class BillingProvider(ABC):
    """Payments are a vendor decision (Stripe, Paystack, Flutterwave...). The app only needs these two calls."""

    name: str

    @abstractmethod
    async def create_checkout(
        self, *, checkout_id: str, credits: Decimal, amount_usd: Decimal, description: str
    ) -> CheckoutSession: ...

    @abstractmethod
    def parse_webhook(self, headers: dict[str, str], body: bytes) -> PaymentEvent:
        """Verify the provider's signature over the RAW body and return the event. Raise InvalidSignature."""
