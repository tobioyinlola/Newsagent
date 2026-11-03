"""Stripe card payments: start a hosted checkout, the signed webhook, and the status check the return page polls.

One rule decides whether credits are added: Stripe itself says the session is paid (a verified webhook, or our own
server-to-Stripe lookup) AND the amount, currency and checkout id match our row. The browser return page proves nothing."""

import logging
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import Principal, current_principal
from app.config import get_settings
from app.db import get_session
from app.integrations import registry
from app.integrations.billing.base import InvalidSignature, PaymentEvent
from app.integrations.billing.stripe import StripeBilling, StripeError, session_amount_usd
from app.models import Checkout, Workspace
from app.services import stripe_reversals as reversals
from app.services.ratelimit import limit

router = APIRouter(tags=["billing"])
log = logging.getLogger("payments")

PROVIDER = "stripe"


def billing() -> StripeBilling:
    item = registry.get_stripe_billing()
    if item is None:
        raise HTTPException(503, "Card payments are not available yet. Please contact support.")
    return item


async def start(db: AsyncSession, p: Principal, *, credits: Decimal, amount_usd: Decimal) -> tuple[Checkout, str]:
    """Create our checkout row and the Stripe session; returns the row and the page to send the customer to."""
    s = get_settings()
    co = Checkout(workspace_id=p.workspace.id, credits=credits, amount_usd=amount_usd, provider=PROVIDER)
    db.add(co)
    await db.flush()
    try:
        session = await billing().create_session(
            checkout_id=co.id,
            amount_usd=amount_usd,
            credits=credits,
            description=f"Cover Founder credits ({credits} credits)",
            email=p.user.email,
            return_base=s.app_base_url,
        )
    except StripeError as e:
        await db.rollback()
        raise HTTPException(503, str(e)) from e
    co.provider_ref = session["id"]
    co.payment_context = {"currency": "USD", "amount": str(amount_usd), "sandbox": billing().sandbox}
    await db.commit()
    return co, session["url"]


async def apply(db: AsyncSession, co: Checkout, session: dict) -> str:
    """Settle `co` from a Stripe session object that came from Stripe (verified webhook or direct lookup)."""
    from app.routes.billing import handle_payment_event
    from app.services.payments import credit_email

    if co.paid_at:
        return "duplicate"
    if co.provider_ref and session.get("id") != co.provider_ref:
        return "reference_mismatch"
    status, paid = session.get("status"), session.get("payment_status")
    if status == "complete" and paid in {"paid", "no_payment_required"}:
        amount = session_amount_usd(session)
        if amount is None:
            return "currency_mismatch"  # never grant for a session that was not charged in USD
        result = await handle_payment_event(
            db,
            PaymentEvent(event_id=f"stripe:{session['id']}", checkout_id=co.id, status="paid", amount_usd=amount),
        )
        await db.commit()
        if result == "granted":
            await credit_email(db, co)
            log.info("Stripe payment granted: checkout=%s", co.id)
        elif result == "amount_mismatch":
            log.error("Stripe amount mismatch, nothing granted: checkout=%s", co.id)
        return result
    if status == "expired" and co.status == "pending":
        await db.execute(
            update(Checkout).where(Checkout.id == co.id, Checkout.paid_at.is_(None)).values(status="expired")
        )
        await db.commit()
        await db.refresh(co)
        return "expired"
    return "pending"


def out(co: Checkout, workspace: Workspace | None = None) -> dict:
    return {
        "checkout_id": co.id,
        "amount_usd": str(co.amount_usd),
        "credits": str(co.credits),
        "status": co.status,
        "sandbox": bool((co.payment_context or {}).get("sandbox")),
        "credit_balance": str(workspace.credit_balance) if workspace is not None else None,
    }


@router.get("/v1/billing/stripe/{id}", dependencies=[Depends(limit("stripe-status", 120, 600))])
async def status(id: str, p: Principal = Depends(current_principal), db: AsyncSession = Depends(get_session)) -> dict:
    co = await db.get(Checkout, id)
    if co is None or co.workspace_id != p.workspace.id or co.provider != PROVIDER:
        raise HTTPException(404, "Payment not found")
    if co.status == "pending" and co.provider_ref:
        last = co.last_verified_at
        if last is not None and last.tzinfo is None:
            last = last.replace(tzinfo=UTC)
        if last is None or datetime.now(UTC) - last > timedelta(seconds=3):
            co.last_verified_at = datetime.now(UTC)
            await db.commit()
            try:
                await apply(db, co, await billing().retrieve(co.provider_ref))  # ask Stripe; never trust the browser
            except StripeError as e:
                log.warning("Stripe status lookup failed: checkout=%s %s", co.id, e)
    await db.refresh(co)
    await db.refresh(p.workspace)
    return out(co, p.workspace)


@router.post("/v1/billing/stripe/{id}/cancel")
async def cancel(id: str, p: Principal = Depends(current_principal), db: AsyncSession = Depends(get_session)) -> dict:
    """The customer backed out on Stripe's page. Closes an unpaid session so it can't be paid later by accident."""
    co = await db.get(Checkout, id)
    if co is None or co.workspace_id != p.workspace.id or co.provider != PROVIDER:
        raise HTTPException(404, "Payment not found")
    if co.status == "pending" and co.provider_ref:
        try:
            await apply(db, co, await billing().retrieve(co.provider_ref))  # it may already be paid: settle that first
            if co.status == "pending":
                await billing().expire(co.provider_ref)
                await apply(db, co, await billing().retrieve(co.provider_ref))
        except StripeError as e:
            log.warning("Stripe cancel failed: checkout=%s %s", co.id, e)
    await db.refresh(co)
    await db.refresh(p.workspace)
    return out(co, p.workspace)


@router.post("/v1/webhooks/stripe", dependencies=[Depends(limit("stripe-webhook", 1200, 60))])
async def webhook(request: Request, db: AsyncSession = Depends(get_session)) -> dict:
    body = await request.body()  # the signature is over the RAW body, so read it before parsing
    if registry.get_stripe_billing() is None:
        raise HTTPException(404)
    try:
        event = billing().verify_webhook({k.lower(): v for k, v in request.headers.items()}, body)
    except InvalidSignature:
        raise HTTPException(401, "Invalid signature") from None
    except (ValueError, KeyError, TypeError):
        raise HTTPException(400, "Malformed event") from None
    kind = event.get("type", "")
    if kind in reversals.EVENTS:  # a refund or a chargeback: money going back, not a checkout being paid
        obj = (event.get("data") or {}).get("object")
        if not isinstance(obj, dict):
            raise HTTPException(400, "Malformed event")
        try:
            result = await reversals.handle(db, billing(), kind, obj)
        except StripeError as e:
            raise HTTPException(503, str(e)) from e  # Stripe retries the delivery
        log.info("Stripe webhook processed: type=%s result=%s", kind, result)
        return {"result": result}
    if kind not in {
        "checkout.session.completed",
        "checkout.session.async_payment_succeeded",
        "checkout.session.async_payment_failed",
        "checkout.session.expired",
    }:
        return {"result": "ignored"}
    session = (event.get("data") or {}).get("object")
    ref = (session or {}).get("client_reference_id") if isinstance(session, dict) else None
    if not isinstance(session, dict) or not isinstance(ref, str) or not isinstance(session.get("id"), str):
        raise HTTPException(400, "Malformed event")
    co = await db.get(Checkout, ref)
    if co is None or co.provider != PROVIDER:
        return {"result": "unknown_checkout"}
    if kind == "checkout.session.async_payment_failed":
        if co.status == "pending":
            co.status = "failed"
            await db.commit()
        return {"result": "failed"}
    # The event is a signal. Settle from the session Stripe reports now, not from a stale copy inside the event.
    try:
        session = await billing().retrieve(session["id"])
    except StripeError as e:
        raise HTTPException(503, str(e)) from e  # Stripe retries the delivery
    result = await apply(db, co, session)
    log.info("Stripe webhook processed: type=%s checkout=%s result=%s", kind, co.id, result)
    return {"result": result}


async def reconcile_pending() -> int:
    """Scheduled: settle Stripe checkouts whose webhook never arrived (and expire abandoned ones)."""
    from sqlalchemy import select

    from app.db import session_maker

    if registry.get_stripe_billing() is None:
        return 0
    count = 0
    async with session_maker()() as db:
        rows = (
            (
                await db.execute(
                    select(Checkout)
                    .where(
                        Checkout.provider == PROVIDER,
                        Checkout.status == "pending",
                        Checkout.created_at > datetime.now(UTC) - timedelta(days=2),
                    )
                    .order_by(Checkout.created_at)
                    .limit(100)
                )
            )
            .scalars()
            .all()
        )
        for co in rows:
            if not co.provider_ref:
                continue
            try:
                count += await apply(db, co, await billing().retrieve(co.provider_ref)) == "granted"
            except StripeError:
                await db.rollback()
                log.warning("Stripe reconciliation deferred: checkout=%s", co.id)
    return count
