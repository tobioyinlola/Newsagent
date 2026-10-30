"""Authenticated receipt claims and finance-only, online-verified reconciliation."""

from datetime import timedelta
from decimal import Decimal
from typing import Literal

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field, field_validator
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import Principal, current_principal, require
from app.db import get_session
from app.integrations.billing.nuvion import NuvionError, PaymentMismatch
from app.models import BankReceipt, Checkout, Workspace
from app.models.base import utcnow
from app.services import bank_payments, payments
from app.services.audit import audit
from app.services.ratelimit import limit

router = APIRouter(tags=["payment-reconciliation"])


class ReceiptClaim(BaseModel):
    reference: str = Field(min_length=10, max_length=200, pattern=r"^[A-Za-z0-9_-]+$")


class ReceiptMatch(BaseModel):
    checkout_id: str = Field(pattern=r"^[0-9a-f]{32}$")
    ownership_confirmed: Literal[True]
    reason: str = Field(min_length=10, max_length=1000)

    @field_validator("reason", mode="before")
    @classmethod
    def trim_reason(cls, value):
        return value.strip() if isinstance(value, str) else value


def provider_error(error):
    return HTTPException(409 if isinstance(error, PaymentMismatch) else 503, str(error))


@router.post("/v1/billing/bank/{id}/claim", dependencies=[Depends(limit("bank-claim", 10, 3600))])
async def claim(
    id: str, body: ReceiptClaim, p: Principal = Depends(current_principal), db: AsyncSession = Depends(get_session)
):
    co = await db.get(Checkout, id)
    if co is None or co.workspace_id != p.workspace.id or co.provider != "nuvion_bank":
        raise HTTPException(404, "Payment not found")
    if co.paid_at:
        return {"status": "paid"}
    try:
        receipt = await bank_payments.find_claim(db, co, body.reference.strip(), payments.provider(co))
    except NuvionError as error:
        raise provider_error(error) from error
    claim = {
        "reference": body.reference,
        "transfer_id": receipt.transfer_id,
        "status": "pending_review",
        "requested_at": utcnow().isoformat(),
    }
    co.payment_context = {**co.payment_context, "bank_claim": claim}
    audit(
        db,
        p.user.email,
        "payment.bank_claim_submitted",
        target_type="checkout",
        target_id=co.id,
        detail={"transfer_id": receipt.transfer_id},
    )
    await db.commit()
    return {
        "status": "pending_review",
        "message": "Your bank transfer was verified and sent to the team for matching. Do not send another payment.",
    }


@router.get("/v1/admin/payment-reconciliation")
async def overview(_: Principal = Depends(require("finance.view")), db: AsyncSession = Depends(get_session)):
    receipts = (
        (await db.execute(select(BankReceipt).order_by(BankReceipt.created_at.desc()).limit(100))).scalars().all()
    )
    rows = (
        await db.execute(
            select(Checkout, Workspace.name)
            .join(Workspace)
            .where(Checkout.provider.in_(["nuvion", "nuvion_bank"]), Workspace.deleted_at.is_(None))
            .order_by(Checkout.created_at.desc())
            .limit(200)
        )
    ).all()
    return {
        "receipts": [
            {
                "id": r.id,
                "transfer_id": r.transfer_id,
                "amount_ngn": str(Decimal(r.data["amount"]) / 100),
                "reference": r.data.get("unique_reference", ""),
                "narration": r.data.get("narration", ""),
                "status": r.status,
                "checkout_id": r.checkout_id,
                "matched_by": r.matched_by,
                "matched_at": r.matched_at,
            }
            for r in receipts
        ],
        "checkouts": [
            {
                "id": c.id,
                "company": name,
                "workspace_id": c.workspace_id,
                "provider": c.provider,
                "status": c.status,
                "currency": c.payment_context.get("currency", "USD"),
                "amount": c.payment_context.get("amount_ngn", str(c.amount_usd)),
                "credits": str(c.credits),
                "created_at": c.created_at,
                "claim": c.payment_context.get("bank_claim"),
                "error": c.payment_context.get("last_payment_error"),
                "confirmation_started_at": c.confirmation_started_at,
            }
            for c, name in rows
        ],
    }


@router.post("/v1/admin/payment-reconciliation/sync", dependencies=[Depends(limit("bank-receipt-sync", 10, 600))])
async def sync(operator: Principal = Depends(require("finance.manage")), db: AsyncSession = Depends(get_session)):
    billing = payments.provider(currency="NGN")
    params = {
        "entity_id": billing.entity_id,
        "account_id": billing.account_id,
        "currency": "NGN",
        "type": "inflow",
        "payment_type": "bank-transfer",
        "status": "successful",
        "date_from": (utcnow() - timedelta(days=30)).isoformat(),
        "limit": 25,
    }
    count = 0
    try:
        for _ in range(2):
            page = await billing.call("GET", "/transfers", params=params)
            for item in page.get("data", []):
                # Retrieve each receipt before it is presented as a verified payment.
                transfer = await billing.call(
                    "GET", f"/transfers/{item['id']}", params={"entity_id": billing.entity_id}
                )
                if transfer.get("id") != item["id"]:
                    raise PaymentMismatch("Transfer ID mismatch")
                await bank_payments.remember_receipt(db, transfer, billing)
                count += 1
            pagination = page.get("meta", {}).get("pagination", {})
            if not pagination.get("has_next") or not pagination.get("next_cursor"):
                break
            params["cursor"] = pagination["next_cursor"]
    except NuvionError as error:
        raise provider_error(error) from error
    return {"verified_receipts": count}


@router.post("/v1/admin/payment-reconciliation/receipts/{id}/match")
async def match(
    id: str,
    body: ReceiptMatch,
    p: Principal = Depends(require("finance.manage")),
    db: AsyncSession = Depends(get_session),
):
    receipt = await db.get(BankReceipt, id)
    co = await db.get(Checkout, body.checkout_id)
    if receipt is None or co is None or co.provider != "nuvion_bank":
        raise HTTPException(404, "Bank receipt or purchase not found")
    ws = await db.get(Workspace, co.workspace_id)
    if ws is None or ws.deleted_at:
        raise HTTPException(409, "The purchase workspace is no longer available")
    billing = payments.provider(co)
    if receipt.api_url != billing.base_url:
        raise HTTPException(409, "The receipt belongs to a different payment environment")
    try:
        transfer = await billing.call(
            "GET", f"/transfers/{receipt.transfer_id}", params={"entity_id": billing.entity_id}
        )
        if transfer.get("id") != receipt.transfer_id:
            raise PaymentMismatch("Transfer ID mismatch")
        result = await bank_payments.settle_transfer(
            db, co, transfer, billing, actor=p.user.email, reason=body.reason.strip()
        )
    except NuvionError as error:
        raise provider_error(error) from error
    if result not in {"granted", "duplicate"}:
        raise HTTPException(409, "This purchase already has another transfer. Review it before applying an adjustment.")
    return {"result": result, "checkout_id": co.id, "credits": str(co.credits), "status": co.status}


@router.post("/v1/admin/payment-reconciliation/checkouts/{id}/recheck")
async def recheck(
    id: str, operator: Principal = Depends(require("finance.manage")), db: AsyncSession = Depends(get_session)
):
    co = await db.get(Checkout, id)
    if co is None or co.provider not in {"nuvion", "nuvion_bank"}:
        raise HTTPException(404, "Payment not found")
    try:
        if co.provider == "nuvion_bank":
            result = await bank_payments.reconcile_bank(db, co, payments.provider(co))
        else:
            _, result = await payments.reconcile(db, co, payments.provider(co), verify=True)
    except NuvionError as error:
        await payments.record_error(db, co, error, "admin_recheck")
        raise provider_error(error) from error
    return {"result": result, "status": co.status}
