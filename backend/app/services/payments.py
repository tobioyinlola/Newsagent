"""One server-verified settlement path for webhooks, return pages and scheduled reconciliation."""

import logging
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import session_maker
from app.integrations import registry
from app.integrations.billing.base import PaymentEvent
from app.integrations.billing.nuvion import NuvionBilling, NuvionError, configuration_problems
from app.models import Checkout, User
from app.services.notifications import send_email

log = logging.getLogger("payments")


def provider() -> NuvionBilling:
    if configuration_problems(get_settings()):
        raise NuvionError("Card payments are not available yet. Please contact support.")
    item = registry.get_nuvion_billing()
    if not isinstance(item, NuvionBilling):
        raise NuvionError("Card payments are not enabled. Please contact support.")
    return item


def utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


async def credit_email(db: AsyncSession, checkout: Checkout):
    for email in (await db.execute(select(User.email).where(User.workspace_id == checkout.workspace_id))).scalars():
        await send_email(
            email,
            "Credits added",
            f"We've added {checkout.credits} credits to your workspace. Thank you!",
            link=("View your balance", f"{get_settings().app_base_url}/billing"),
        )


async def reconcile(
    db: AsyncSession, checkout: Checkout, billing: NuvionBilling, *, verify: bool = False
) -> tuple[dict, str]:
    if checkout.paid_at:
        return {"status": "completed"}, "duplicate"
    intent = await billing.ensure_intent(checkout)
    if not checkout.provider_ref:
        checkout.provider_ref = intent["id"]
        await db.commit()  # Bind the provider ID before any confirmation can be attempted.
    if verify and (
        checkout.last_verified_at is None or datetime.now(UTC) - utc(checkout.last_verified_at) > timedelta(seconds=15)
    ):
        checkout.last_verified_at = datetime.now(UTC)
        await db.commit()
        intent = await billing.verify(intent)
    billing.check(intent, checkout)
    result = "pending"
    if intent.get("status") == "completed":
        from app.routes.billing import handle_payment_event

        result = await handle_payment_event(
            db,
            PaymentEvent(
                event_id=f"nuvion:{intent['id']}",
                checkout_id=checkout.id,
                status="paid",
                amount_usd=Decimal(intent["amount"]) / 100,
            ),
        )
        await db.commit()
        if result == "granted":
            await credit_email(db, checkout)
    elif intent.get("status") in {"failed", "cancelled"}:
        if checkout.paid_at is None:
            await db.execute(
                update(Checkout)
                .where(Checkout.id == checkout.id, Checkout.paid_at.is_(None))
                .values(status="failed" if intent["status"] == "failed" else "expired")
            )
            await db.commit()
            await db.refresh(checkout)
    return intent, result


async def reconcile_pending() -> int:
    if configuration_problems(get_settings()):
        return 0
    billing = provider()
    count = 0
    async with session_maker()() as db:
        checkouts = (
            (
                await db.execute(
                    select(Checkout)
                    .where(
                        Checkout.provider == "nuvion",
                        Checkout.status == "pending",
                        Checkout.confirmation_started_at.is_not(None),
                    )
                    .order_by(Checkout.created_at)
                    .limit(100)
                )
            )
            .scalars()
            .all()
        )
        for checkout in checkouts:
            try:
                _, result = await reconcile(db, checkout, billing, verify=True)
                count += result == "granted"
            except NuvionError:
                await db.rollback()
                log.warning("Payment reconciliation deferred; no unverified credits granted")
    return count
