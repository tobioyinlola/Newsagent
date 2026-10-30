"""Authenticated card checkout. Plaintext PAN/CVV never enter this API."""

import base64
import json
from datetime import UTC, datetime
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import Principal, current_principal
from app.config import get_settings
from app.db import get_session
from app.integrations.billing.base import InvalidSignature
from app.integrations.billing.nuvion import NuvionBilling, NuvionError, PaymentMismatch
from app.models import Checkout
from app.services import payments
from app.services.ratelimit import client_ip, limit

router = APIRouter(tags=["billing"])


class CardBrowserInfo(BaseModel):
    language: str = Field(default="en", max_length=30)
    screen_width: str = Field(default="", max_length=10)
    screen_height: str = Field(default="", max_length=10)
    color_depth: str = Field(default="", max_length=10)
    timezone_offset: str = Field(default="", max_length=10)
    java_enabled: bool = False
    javascript_enabled: bool = True
    channel: Literal["browser"] = "browser"


class CardAddress(BaseModel):
    address_line_one: str = Field(min_length=1, max_length=200)
    city: str = Field(min_length=1, max_length=100)
    state: str = Field(min_length=1, max_length=100)
    country: str = Field(pattern=r"^[A-Z]{2}$")
    zip: str = Field(default="", max_length=30)


class CardConfirmation(BaseModel):
    model_config = ConfigDict(extra="forbid")
    encrypted_data: str = Field(min_length=100, max_length=4096, repr=False)
    first_name: str = Field(min_length=1, max_length=100)
    last_name: str = Field(min_length=1, max_length=100)
    billing_address: CardAddress
    browser_info: CardBrowserInfo

    @field_validator("encrypted_data")
    @classmethod
    def ciphertext(cls, value: str) -> str:
        try:
            raw = base64.b64decode(value, validate=True)
            if not 256 <= len(raw) <= 1024:
                raise ValueError("Invalid encrypted card data")
        except Exception as e:
            raise ValueError("Invalid encrypted card data") from e
        return value


async def owned(db: AsyncSession, id: str, p: Principal) -> Checkout:
    co = await db.get(Checkout, id)
    if co is None or co.workspace_id != p.workspace.id or co.provider != "nuvion":
        raise HTTPException(404, "Payment not found")
    return co


def active_provider(co: Checkout | None = None) -> NuvionBilling:
    try:
        return payments.provider(co)
    except NuvionError as e:
        raise HTTPException(503, str(e)) from e


def output(co: Checkout, intent: dict, provider: NuvionBilling) -> dict:
    state = "completed" if co.paid_at else intent.get("status", "processing")
    if co.confirmation_started_at and state == "requires_action":
        state = "confirming"
    return {
        "can_retry_confirmation": not co.confirmation_started_at
        and co.status == "pending"
        and state == "requires_action",
        "payment_error": (co.payment_context or {}).get("last_payment_error"),
        "checkout_id": co.id,
        "amount_usd": str(co.amount_usd),
        "credits": str(co.credits),
        "currency": provider.currency,
        "amount": str(provider.amount(co)),
        "ngn_per_usd": co.payment_context.get("ngn_per_usd"),
        "status": co.status,
        "provider_status": state,
        "public_key": provider.public_key,
        "sandbox": provider.base_url == "https://api.nuvion.dev",
        "next_action_url": None if co.paid_at else provider.redirect_url(intent),
    }


@router.get("/v1/billing/checkouts")
async def history(p: Principal = Depends(current_principal), db: AsyncSession = Depends(get_session)) -> list[dict]:
    rows = (
        await db.execute(
            select(Checkout)
            .where(Checkout.workspace_id == p.workspace.id, Checkout.provider.in_(["nuvion", "nuvion_bank"]))
            .order_by(Checkout.created_at.desc())
            .limit(50)
        )
    ).scalars()
    return [
        {
            "id": co.id,
            "amount_usd": str(co.amount_usd),
            "currency": co.payment_context.get("currency", "USD"),
            "amount": co.payment_context.get("amount_ngn", str(co.amount_usd)),
            "payment_method": "bank_transfer" if co.provider == "nuvion_bank" else "card",
            "credits": str(co.credits),
            "status": co.status,
            "created_at": co.created_at,
        }
        for co in rows
    ]


@router.get("/v1/billing/card/{id}", dependencies=[Depends(limit("card-status", 120, 600))])
async def status(id: str, p: Principal = Depends(current_principal), db: AsyncSession = Depends(get_session)) -> dict:
    co = await owned(db, id, p)
    provider = active_provider(co)
    try:
        intent, _ = await payments.reconcile(db, co, provider, verify=True)
        return output(co, intent, provider)
    except PaymentMismatch as e:
        raise HTTPException(409, str(e)) from e
    except NuvionError as e:
        await payments.record_error(db, co, e, "payment_status")
        raise HTTPException(503, str(e)) from e


@router.get("/v1/billing/bank/{id}", dependencies=[Depends(limit("bank-status", 120, 600))])
async def bank_status(
    id: str, p: Principal = Depends(current_principal), db: AsyncSession = Depends(get_session)
) -> dict:
    from app.services.bank_payments import reconcile_bank, reference

    co = await db.get(Checkout, id)
    if co is None or co.workspace_id != p.workspace.id or co.provider != "nuvion_bank":
        raise HTTPException(404, "Payment not found")
    try:
        await reconcile_bank(db, co, active_provider(co))
    except PaymentMismatch as e:
        raise HTTPException(409, str(e)) from e
    except NuvionError as e:
        await payments.record_error(db, co, e, "payment_status")
        raise HTTPException(503, str(e)) from e
    return {
        "checkout_id": co.id,
        "amount_usd": str(co.amount_usd),
        "amount_ngn": co.payment_context["amount_ngn"],
        "ngn_per_usd": co.payment_context["ngn_per_usd"],
        "credits": str(co.credits),
        "status": co.status,
        "claim": (co.payment_context or {}).get("bank_claim"),
        "reference": reference(co),
        "bank": co.payment_context["bank"],
    }


@router.post("/v1/billing/card/{id}/confirm", dependencies=[Depends(limit("card-confirm", 20, 3600))])
async def confirm(
    id: str,
    body: CardConfirmation,
    request: Request,
    p: Principal = Depends(current_principal),
    db: AsyncSession = Depends(get_session),
) -> dict:
    co = await owned(db, id, p)
    provider = active_provider(co)
    if p.workspace.suspended:
        raise HTTPException(403, "This workspace is suspended")
    try:
        intent, _ = await payments.reconcile(db, co, provider)
        if co.status != "pending" or intent.get("status") != "requires_action" or co.confirmation_started_at:
            return output(co, intent, provider)
        claimed = (
            await db.execute(
                update(Checkout)
                .where(Checkout.id == id, Checkout.status == "pending", Checkout.confirmation_started_at.is_(None))
                .values(confirmation_started_at=datetime.now(UTC))
                .returning(Checkout.id)
            )
        ).scalar_one_or_none()
        await db.commit()  # A retry cannot submit a second confirmation after a timeout or process crash.
        if claimed is None:
            await db.refresh(co)
            intent, _ = await payments.reconcile(db, co, provider)
            return output(co, intent, provider)
        browser = {
            **body.browser_info.model_dump(),
            "accept_header": request.headers.get("accept", "")[:500],
            "user_agent": request.headers.get("user-agent", "")[:500],
            "ip_address": client_ip(request),
        }
        try:
            await provider.call(
                "POST",
                "/intent-actions",
                body={
                    "payment_intent_id": co.provider_ref,
                    "entity_id": provider.entity_id,
                    "intent_action": {
                        "action": "confirm",
                        "category": "collections",
                        "payment_type": "card-acq",
                        "payment_type_data": {
                            "data": body.encrypted_data,
                            "auth_model": "3ds_required",
                            "billing_address": body.billing_address.model_dump(),
                            "browser_info": browser,
                        },
                        "customer": {
                            "first_name": body.first_name.strip(),
                            "last_name": body.last_name.strip(),
                            "email": p.user.email,
                        },
                        "return_url": f"{get_settings().app_base_url}/billing/card/{co.id}",
                    },
                },
            )
        except NuvionError as error:
            await payments.record_error(db, co, error, "card_confirmation")
            if error.definite_rejection:
                try:
                    current = await provider.retrieve(co.provider_ref or intent["id"])
                    provider.check(current, co)
                    await payments.recover_confirmation(db, co, provider, current, rejected=True)
                except NuvionError:
                    pass
            raise

        intent, _ = await payments.reconcile(db, co, provider)
        return output(co, intent, provider)
    except PaymentMismatch as e:
        raise HTTPException(409, str(e)) from e
    except NuvionError as e:
        raise HTTPException(503, str(e)) from e


@router.post("/v1/billing/card/{id}/cancel")
async def cancel(id: str, p: Principal = Depends(current_principal), db: AsyncSession = Depends(get_session)) -> dict:
    co = await owned(db, id, p)
    provider = active_provider(co)
    try:
        intent, _ = await payments.reconcile(db, co, provider)
        if intent.get("status") == "requires_action":
            await provider.call(
                "PATCH",
                f"/payment-intents/{co.provider_ref}",
                body={"action": "cancel", "entity_id": provider.entity_id},
            )
            intent, _ = await payments.reconcile(db, co, provider)
        return output(co, intent, provider)
    except NuvionError as e:
        raise HTTPException(503, str(e)) from e


@router.post("/v1/webhooks/nuvion", dependencies=[Depends(limit("nuvion-webhook", 1200, 60))])
async def webhook(request: Request, db: AsyncSession = Depends(get_session)) -> dict:
    body = await request.body()
    try:
        probe = json.loads(body)
    except (ValueError, TypeError):
        raise HTTPException(400, "Malformed event") from None
    # Nuvion checks endpoint reachability before its generated signing secret can be installed.
    # This acknowledgement never processes payments, reads a wallet or grants credits.
    if isinstance(probe, dict) and probe.get("event") == "webhook.health":
        return {"status": "ok"}
    provider = active_provider()
    try:
        event = provider.signed_event({k.lower(): v for k, v in request.headers.items()}, body)
    except InvalidSignature:
        raise HTTPException(401, "Invalid signature") from None
    except (ValueError, KeyError, TypeError):
        raise HTTPException(400, "Malformed event") from None
    if not isinstance(event, dict):
        raise HTTPException(400, "Malformed event")
    if event.get("event") == "inflows.completed":
        from app.services.bank_payments import process_inflow

        try:
            result = await process_inflow(db, event.get("data"))
            payments.log.info("Nuvion webhook processed: event=inflows.completed result=%s", result)
            return {"result": result}
        except PaymentMismatch:
            # A real but unmatched transfer needs review, not repeated delivery/endpoint blacklisting.
            return {"result": "requires_review"}
        except NuvionError as e:
            raise HTTPException(503, str(e)) from e
    if event.get("event") not in {"payment_intent.completed", "payment_intent.failed", "payment_intent.cancelled"}:
        return {"result": "ignored"}
    data = event.get("data")
    if not isinstance(data, dict) or not isinstance(data.get("id"), str) or not isinstance(data.get("reference"), str):
        raise HTTPException(400, "Malformed event")
    co = await db.get(Checkout, data["reference"])
    if co is None or co.provider != "nuvion":
        return {"result": "unknown_checkout"}
    if co.provider_ref and co.provider_ref != data["id"]:
        raise HTTPException(409, "Payment reference mismatch")
    provider = active_provider(co)
    try:
        # The event is only a wake-up signal. Never trust its amount, status or return URL.
        _, result = await payments.reconcile(db, co, provider)
    except PaymentMismatch as e:
        raise HTTPException(409, str(e)) from e
    except NuvionError as e:
        raise HTTPException(503, str(e)) from e
    payments.log.info("Nuvion card webhook processed: checkout=%s result=%s", co.id, result)
    return {"result": result}
