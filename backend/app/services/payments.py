"""One server-verified settlement path for webhooks, return pages and scheduled reconciliation."""

import logging
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import func, or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import session_maker
from app.integrations import registry
from app.integrations.billing.base import PaymentEvent
from app.integrations.billing.nuvion import NuvionBilling, NuvionError, configuration_problems
from app.models import Checkout, User
from app.services.notifications import send_email

log = logging.getLogger("payments")


def provider(checkout: Checkout | None = None, *, currency: str = "USD") -> NuvionBilling:
    if configuration_problems(get_settings()):
        raise NuvionError("Card payments are not available yet. Please contact support.")
    if checkout:
        currency = (checkout.payment_context or {}).get("currency", "USD")
    if currency == "NGN" and not get_settings().nuvion_ngn_account_id:
        raise NuvionError("Naira payments are not available yet. Please choose USD.")
    item = registry.get_nuvion_ngn_billing() if currency == "NGN" else registry.get_nuvion_billing()
    if not isinstance(item, NuvionBilling):
        raise NuvionError("Card payments are not enabled. Please contact support.")
    return item


def utc(value: datetime) -> datetime:
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


def money_line(checkout: Checkout) -> str:
    """The amount the customer actually paid, in the currency they paid in."""
    ctx = checkout.payment_context or {}
    if ctx.get("currency") == "NGN" and (ctx.get("amount") or ctx.get("amount_ngn")):
        return f"₦{Decimal(str(ctx.get('amount') or ctx.get('amount_ngn'))):,.2f}"
    return f"${Decimal(checkout.amount_usd):,.2f}"


async def credit_email(db: AsyncSession, checkout: Checkout):
    """The payment confirmation with its invoice, sent to the workspace's people once the credits are in."""
    from app.models import Workspace
    from app.services import email_templates as templates

    workspace = await db.get(Workspace, checkout.workspace_id)
    paid = utc(checkout.paid_at) if checkout.paid_at else datetime.now(UTC)
    method = "Card (Stripe)" if checkout.provider == "stripe" else "Card"
    subject, html, text = templates.payment_receipt(
        invoice_no="CF-" + checkout.id[:8].upper(),
        paid_on=f"{paid.day} {paid:%b %Y}",
        billed_to=workspace.name if workspace else "Your workspace",
        amount=money_line(checkout),
        credits=f"{Decimal(checkout.credits):,.2f}",
        balance=f"{Decimal(workspace.credit_balance):,.2f}" if workspace else "",
        method=method,
        reference=checkout.provider_ref or checkout.id,
        sign_in_url=f"{get_settings().app_base_url}/login",
    )
    for email in (await db.execute(select(User.email).where(User.workspace_id == checkout.workspace_id))).scalars():
        await send_email(email, subject, text, html)


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
                amount_usd=checkout.amount_usd,
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
    if result == "pending":
        await recover_confirmation(db, checkout, billing, intent)
    return intent, result


async def reconcile_pending() -> int:
    from app.routes.stripe_payments import reconcile_pending as reconcile_stripe

    stripe_count = await reconcile_stripe()
    if configuration_problems(get_settings()):
        return stripe_count
    count = stripe_count
    async with session_maker()() as db:
        checkouts = (
            (
                await db.execute(
                    select(Checkout)
                    .where(
                        Checkout.provider.in_(["nuvion", "nuvion_bank"]),
                        Checkout.status == "pending",
                        or_(Checkout.provider == "nuvion_bank", Checkout.confirmation_started_at.is_not(None)),
                    )
                    .order_by(func.coalesce(Checkout.last_verified_at, Checkout.created_at), Checkout.created_at)
                    .limit(100)
                )
            )
            .scalars()
            .all()
        )
        for checkout in checkouts:
            try:
                if checkout.provider == "nuvion_bank":
                    from app.services.bank_payments import reconcile_bank

                    result = await reconcile_bank(db, checkout, provider(checkout))
                elif checkout.confirmation_started_at:
                    _, result = await reconcile(db, checkout, provider(checkout), verify=True)
                else:
                    continue
                count += result == "granted"
            except NuvionError:
                await db.rollback()
                log.warning("Payment reconciliation deferred; no unverified credits granted")
    return count


async def record_error(db: AsyncSession, checkout: Checkout, error: NuvionError, stage: str) -> None:
    from app.services.audit import audit

    detail = {
        "stage": stage,
        "code": error.code,
        "http_status": error.http_status,
        "request_id": error.request_id,
        "message": str(error),
        "at": datetime.now(UTC).isoformat(),
    }
    checkout.payment_context = {**checkout.payment_context, "last_payment_error": detail}
    audit(db, "payment-service", "payment.provider_error", target_type="checkout", target_id=checkout.id, detail=detail)
    log.warning(
        "Payment provider error: checkout=%s stage=%s code=%s http_status=%s request_id=%s",
        checkout.id,
        stage,
        error.code,
        error.http_status,
        error.request_id,
    )
    await db.commit()


async def recover_confirmation(
    db: AsyncSession, checkout: Checkout, billing: NuvionBilling, intent: dict, *, rejected: bool = False
) -> bool:
    started = checkout.confirmation_started_at
    if not started or checkout.paid_at or checkout.status != "pending" or intent.get("status") != "requires_action":
        return False
    if not rejected and datetime.now(UTC) - utc(started) < timedelta(minutes=2):
        return False  # An ambiguous timeout is never immediately retried.
    try:
        if await billing.has_actions(intent):
            return False
    except NuvionError:
        return False
    changed = (
        await db.execute(
            update(Checkout)
            .where(
                Checkout.id == checkout.id,
                Checkout.confirmation_started_at == started,
                Checkout.paid_at.is_(None),
                Checkout.status == "pending",
            )
            .values(confirmation_started_at=None)
            .returning(Checkout.id)
        )
    ).scalar_one_or_none()
    if changed:
        from app.services.audit import audit

        audit(
            db,
            "payment-service",
            "payment.confirmation_recovered",
            target_type="checkout",
            target_id=checkout.id,
            detail={
                "provider_ref": checkout.provider_ref,
                "reason": "Provider confirms requires_action and no intent actions; user must re-enter and explicitly submit card details.",
            },
        )
        log.info("Payment confirmation recovered: checkout=%s", checkout.id)
    await db.commit()
    await db.refresh(checkout)
    return bool(changed)
