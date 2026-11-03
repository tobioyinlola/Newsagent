"""Refunds and chargebacks on Stripe card payments: what happens to the wallet when money goes back.

You refund (or fight a dispute) in the Stripe dashboard; Stripe tells our webhook; this module does the rest.
Rules (decided with the owner):
  - Refund: take back the credits the refund represents, but only what is still in the wallet. The balance never goes below
    zero. Credits already spent are written off and an alert tells the team how many.
  - Chargeback: hold the credits at once (again never below zero). Won: give them back. Lost: they stay removed.
Everything goes through `ledger.apply`, so a repeated or out-of-order webhook changes nothing twice, and the ledger still sums
to the balance. Amounts and ids are never taken from the event alone: we read the payment from Stripe and require it to be
one of our own paid Stripe checkouts."""

import logging
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.integrations.billing.stripe import StripeBilling, cents
from app.models import Checkout, User, Workspace
from app.services import email_templates as templates
from app.services import ledger
from app.services.audit import audit
from app.services.notifications import notify_operators, send_email

log = logging.getLogger("payments")
CENT = Decimal("0.01")
ZERO = Decimal("0")
LIVE = {"paid", "partially_refunded"}  # statuses a refund or a dispute may change


def invoice_no(co: Checkout) -> str:
    return "CF-" + co.id[:8].upper()


def _q(x: Decimal) -> Decimal:
    return Decimal(x).quantize(CENT, rounding=ROUND_HALF_UP)


def _d(ctx: dict, key: str) -> Decimal:
    return Decimal(str(ctx.get(key, "0")))


def _credits_for(co: Checkout, part_cents: int) -> Decimal:
    """The credits that `part_cents` of this payment bought (never more than the whole purchase)."""
    paid = cents(co.amount_usd)
    return _q(min(Decimal(co.credits), Decimal(co.credits) * part_cents / paid))


async def _checkout_for(db: AsyncSession, billing: StripeBilling, obj: dict) -> Checkout | None:
    """Our paid Stripe checkout that this charge or dispute belongs to, or None (the event is then ignored)."""
    intent_id = obj.get("payment_intent")
    if not isinstance(intent_id, str):
        return None
    intent = await billing.retrieve_payment_intent(intent_id)
    checkout_id = (intent.get("metadata") or {}).get("checkout_id")
    if not isinstance(checkout_id, str):
        return None
    co = (await db.execute(select(Checkout).where(Checkout.id == checkout_id).with_for_update())).scalar_one_or_none()
    if co is None or co.provider != "stripe" or co.paid_at is None:
        return None
    return co


async def _workspace(db: AsyncSession, co: Checkout) -> Workspace:
    return (
        await db.execute(
            select(Workspace)
            .where(Workspace.id == co.workspace_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).scalar_one()


def _available(ws: Workspace) -> Decimal:
    return _q(max(Decimal(ws.credit_balance or 0), ZERO))


async def _people(db: AsyncSession, co: Checkout) -> list[str]:
    return list((await db.execute(select(User.email).where(User.workspace_id == co.workspace_id))).scalars())


async def _alert(db: AsyncSession, co: Checkout, ws: Workspace, subject: str, lines: str) -> None:
    await notify_operators(
        subject,
        f"{lines}\n\nCustomer: {ws.name}\nInvoice: {invoice_no(co)}\nCheckout: {co.id}\n"
        f"Payment: ${Decimal(co.amount_usd):,.2f} for {Decimal(co.credits):,.2f} credits\n"
        f"Wallet balance now: {Decimal(ws.credit_balance):,.2f} credits\n"
        f"Open the payment in Stripe: {co.provider_ref}",
    )


async def on_refund(db: AsyncSession, billing: StripeBilling, charge: dict) -> str:
    """`charge.refunded`: the charge's refunded total is cumulative, so each event is compared with what we already did."""
    co = await _checkout_for(db, billing, charge)
    if co is None:
        return "unknown_payment"
    paid_cents = cents(co.amount_usd)
    if str(charge.get("currency", "")).lower() != "usd" or int(charge.get("amount", -1)) != paid_cents:
        log.error("Stripe refund does not match the checkout, ignored: checkout=%s", co.id)
        return "amount_mismatch"
    refunded_cents = min(int(charge.get("amount_refunded", 0)), paid_cents)
    ctx = dict(co.payment_context or {})
    due = _credits_for(co, refunded_cents)  # credits all refunds so far represent
    delta = due - _d(ctx, "credits_handled")
    if delta <= 0:
        return "duplicate"  # a repeat, or an older event arriving after a newer one
    ws = await _workspace(db, co)
    take = min(delta, _available(ws))
    written_off = delta - take
    if take > 0:
        tx = await ledger.apply(
            db,
            ws,
            -take,
            "refund",
            ref=f"refund:{co.id}:{refunded_cents}",
            description=f"Refund of ${Decimal(refunded_cents) / 100:,.2f} ({invoice_no(co)})",
        )
        if tx is None:
            return "duplicate"
    ctx.update(
        refunded_usd=str(Decimal(refunded_cents) / 100),
        credits_handled=str(due),
        credits_removed=str(_d(ctx, "credits_removed") + take),
        credits_unrecovered=str(_d(ctx, "credits_unrecovered") + written_off),
    )
    co.payment_context = ctx
    if co.status in LIVE:
        co.status = "refunded" if refunded_cents >= paid_cents else "partially_refunded"
    audit(
        db,
        "stripe-webhook",
        "payment.refunded",
        target_type="checkout",
        target_id=co.id,
        detail={
            "refunded_cents": refunded_cents,
            "credits_removed": str(take),
            "credits_written_off": str(written_off),
        },
    )
    await db.commit()
    log.info("Stripe refund applied: checkout=%s removed=%s written_off=%s", co.id, take, written_off)
    subject, html, text = templates.refund_notice(
        invoice_no=invoice_no(co),
        refunded=f"${Decimal(refunded_cents) / 100:,.2f}",
        credits_removed=f"{take:,.2f}",
        balance=f"{Decimal(ws.credit_balance):,.2f}",
        full=refunded_cents >= paid_cents,
        sign_in_url=f"{get_settings().app_base_url}/billing",
    )
    for email in await _people(db, co):
        await send_email(email, subject, text, html)
    if written_off > 0:
        await _alert(
            db,
            co,
            ws,
            f"Refund issued, {written_off:,.2f} credits already spent ({ws.name})",
            f"A refund of ${Decimal(refunded_cents) / 100:,.2f} was issued in Stripe, but the customer had already spent "
            f"{written_off:,.2f} credits of it. We took back {take:,.2f} and wrote off the rest.",
        )
    return "refunded"


async def _hold(db: AsyncSession, co: Checkout, ws: Workspace, dispute: dict) -> tuple[Decimal, Decimal] | None:
    """Take the disputed credits out of the wallet (what is left of them). Returns (held, not_recoverable) or None if repeated."""
    ctx = dict(co.payment_context or {})
    if ctx.get("dispute_id") == dispute["id"]:
        return None
    disputed = _credits_for(co, min(int(dispute.get("amount", 0)), cents(co.amount_usd)))
    want = max(disputed - _d(ctx, "credits_handled"), ZERO)  # credits a refund already took back are not taken twice
    take = min(want, _available(ws))
    if take > 0:
        tx = await ledger.apply(
            db,
            ws,
            -take,
            "chargeback",
            ref=f"chargeback:{dispute['id']}",
            description=f"Chargeback on payment {invoice_no(co)} (credits held)",
        )
        if tx is None:
            return None
    ctx.update(
        dispute_id=dispute["id"],
        dispute_status="open",
        dispute_credits_held=str(take),
        dispute_credits_unrecovered=str(want - take),
    )
    co.payment_context = ctx
    if co.status in LIVE:
        co.status = "disputed"
    return take, want - take


async def on_dispute_opened(db: AsyncSession, billing: StripeBilling, dispute: dict) -> str:
    co = await _checkout_for(db, billing, dispute)
    if co is None:
        return "unknown_payment"
    if str(dispute.get("currency", "")).lower() != "usd" or not isinstance(dispute.get("id"), str):
        return "amount_mismatch"
    ws = await _workspace(db, co)
    done = await _hold(db, co, ws, dispute)
    if done is None:
        return "duplicate"
    held, short = done
    audit(
        db,
        "stripe-webhook",
        "payment.disputed",
        target_type="checkout",
        target_id=co.id,
        detail={"dispute": dispute["id"], "reason": dispute.get("reason"), "credits_held": str(held)},
    )
    await db.commit()
    log.info("Stripe dispute opened: checkout=%s held=%s", co.id, held)
    await _alert(
        db,
        co,
        ws,
        f"Chargeback opened ({ws.name})",
        f"The customer's bank opened a dispute ({dispute.get('reason', 'reason not given')}) for "
        f"${Decimal(int(dispute.get('amount', 0))) / 100:,.2f}. We are holding {held:,.2f} credits"
        + (f" ({short:,.2f} were already spent and could not be held)" if short > 0 else "")
        + ". Respond with your evidence in the Stripe dashboard before the deadline.",
    )
    return "disputed"


async def on_dispute_closed(db: AsyncSession, billing: StripeBilling, dispute: dict) -> str:
    co = await _checkout_for(db, billing, dispute)
    if co is None:
        return "unknown_payment"
    outcome = dispute.get("status")
    if outcome not in {"won", "lost", "warning_closed"} or not isinstance(dispute.get("id"), str):
        return "ignored"
    ws = await _workspace(db, co)
    ctx = dict(co.payment_context or {})
    if ctx.get("dispute_id") != dispute["id"]:
        await _hold(db, co, ws, dispute)  # the "opened" event never reached us: hold first, then close it out
        ctx = dict(co.payment_context or {})
    if ctx.get("dispute_status") in {"won", "lost"}:
        return "duplicate"
    held = _d(ctx, "dispute_credits_held")
    if outcome in {"won", "warning_closed"}:
        if held > 0:
            await ledger.apply(
                db,
                ws,
                held,
                "chargeback_reversal",
                ref=f"chargeback_won:{dispute['id']}",
                description=f"Chargeback won, credits returned ({invoice_no(co)})",
            )
        ctx.update(dispute_status="won")
        co.payment_context = ctx
        if co.status == "disputed":
            co.status = "partially_refunded" if _d(ctx, "credits_handled") > 0 else "paid"
        result, subject = "won", f"Chargeback won ({ws.name})"
        body = (
            f"The dispute was decided in your favour. {held:,.2f} held credits were returned to the customer's wallet."
        )
    else:
        ctx.update(dispute_status="lost")
        co.payment_context = ctx
        if co.status in LIVE | {"disputed"}:
            co.status = "charged_back"
        result, subject = "lost", f"Chargeback lost ({ws.name})"
        body = (
            f"The dispute was decided against you. The {held:,.2f} held credits stay removed from the wallet. "
            "Stripe also charges its dispute fee to you."
        )
    audit(
        db,
        "stripe-webhook",
        f"payment.dispute_{result}",
        target_type="checkout",
        target_id=co.id,
        detail={"dispute": dispute["id"], "credits_held": str(held)},
    )
    await db.commit()
    log.info("Stripe dispute closed: checkout=%s result=%s", co.id, result)
    await _alert(db, co, ws, subject, body)
    return f"dispute_{result}"


async def handle(db: AsyncSession, billing: StripeBilling, kind: str, obj: dict) -> str:
    if kind == "charge.refunded":
        return await on_refund(db, billing, obj)
    if kind == "charge.dispute.created":
        return await on_dispute_opened(db, billing, obj)
    return await on_dispute_closed(db, billing, obj)


EVENTS = {"charge.refunded", "charge.dispute.created", "charge.dispute.closed"}
