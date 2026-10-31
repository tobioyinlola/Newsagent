"""Private transfer receipts and explicitly authorized finance approval."""

import hashlib
import re
from pathlib import PurePath
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException
from pydantic import BaseModel, ConfigDict, Field, field_validator
from sqlalchemy import case, func, or_, select, update
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import Principal, current_principal, require
from app.db import get_session
from app.integrations import registry
from app.integrations.billing.base import PaymentEvent
from app.integrations.storage.base import ObjectTooLarge
from app.models import BankReceipt, Checkout, PaymentProof, SystemSetting, TransferMail, TransferReview, Workspace
from app.models.base import new_id, utcnow
from app.services import transfer_reviews as svc
from app.services import uploads
from app.services.audit import audit
from app.services.ratelimit import limit

router = APIRouter(tags=["bank-transfer-review"])


class ReceiptUpload(BaseModel):
    content_type: Literal["image/png", "image/jpeg", "application/pdf"]
    filename: str = Field(min_length=1, max_length=200)
    size_bytes: int = Field(gt=0, le=svc.MAX_RECEIPT_BYTES)


class ProofId(BaseModel):
    proof_id: str = Field(pattern=r"^[0-9a-f]{32}$")


class SubmitProof(ProofId):
    sender_reference: str = Field(default="", max_length=200)


class Approval(ProofId):
    model_config = ConfigDict(str_strip_whitespace=True)
    revision: int = Field(ge=1)
    funds_confirmed: Literal[True]
    payment_reference: str = Field(min_length=6, max_length=100, pattern=r"^[A-Za-z0-9 /_.:-]+$")
    reason: str = Field(min_length=10, max_length=1000)

    @field_validator("payment_reference")
    @classmethod
    def canonical(cls, value):
        value = re.sub(r"[^A-Z0-9]", "", value.upper())
        if len(value) < 6:
            raise ValueError("Enter the bank's transaction reference, not the checkout narration.")
        return value


class Rejection(ProofId):
    revision: int = Field(ge=1)
    model_config = ConfigDict(str_strip_whitespace=True)
    reason: str = Field(min_length=10, max_length=1000)


async def owned(db, id, principal):
    co = await db.get(Checkout, id)
    if co is None or co.workspace_id != principal.workspace.id or co.provider != svc.PROVIDER:
        raise HTTPException(404, "Transfer purchase not found")
    return co


async def locked(db, id):
    co = (
        await db.execute(
            update(Checkout)
            .where(Checkout.id == id, Checkout.provider == svc.PROVIDER)
            .values(status=Checkout.status)
            .returning(Checkout)
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()
    if co is None:
        raise HTTPException(404, "Transfer purchase not found")
    return co


async def output(db, co, *, admin=False):
    review = await db.get(TransferReview, co.id)
    proof = await db.get(PaymentProof, review.proof_id) if review and review.proof_id else None
    result = {
        "id": co.id,
        "status": co.status,
        "currency": co.payment_context["currency"],
        "amount": co.payment_context["amount"],
        "amount_usd": str(co.amount_usd),
        "credits": str(co.credits),
        "ngn_per_usd": co.payment_context.get("ngn_per_usd"),
        "bank": {
            **co.payment_context["bank"],
            "recipient_display_name": svc.recipient_display(co.payment_context["bank"]),
        },
        "reference": co.payment_context["reference"],
        "created_at": co.created_at,
        "paid_at": co.paid_at,
        "review_status": review.status if review else "awaiting_receipt",
        "revision": review.revision if review else 0,
        "submitted_at": review.submitted_at if review else None,
        "reviewed_at": review.reviewed_at if review else None,
        "payment_reference": review.payment_reference if review else None,
        "reason": review.reason if review and (admin or review.status == "rejected") else "",
        "receipt": {
            "id": proof.id,
            "filename": proof.filename,
            "content_type": proof.content_type,
            "url": registry.get_storage().presign_get(proof.key, 600),
        }
        if proof and proof.status == "clean"
        else None,
    }
    if admin and review:
        ws = await db.get(Workspace, co.workspace_id)
        result.update(
            company=ws.name if ws else "Deleted business",
            workspace_id=co.workspace_id,
            customer=review.submitted_by,
            reviewed_by=review.reviewed_by,
            sender_reference=co.payment_context.get("sender_reference", ""),
            notifications=[
                {"recipient": m.recipient, "status": m.status, "kind": m.kind, "attempts": m.attempts}
                for m in (await db.execute(select(TransferMail).where(TransferMail.checkout_id == co.id))).scalars()
            ],
        )
    return result


@router.get("/v1/billing/transfer/{id}")
async def status(id: str, p: Principal = Depends(current_principal), db: AsyncSession = Depends(get_session)):
    return await output(db, await owned(db, id, p))


@router.post("/v1/billing/transfer/{id}/uploads", dependencies=[Depends(limit("payment-proof-upload", 30, 3600))])
async def start_upload(
    id: str, body: ReceiptUpload, p: Principal = Depends(current_principal), db: AsyncSession = Depends(get_session)
):
    co = await owned(db, id, p)
    review = await db.get(TransferReview, id)
    if co.paid_at or (review and review.status == "pending_review"):
        raise HTTPException(409, "This purchase is already paid or awaiting review")
    if p.workspace.suspended:
        raise HTTPException(403, "This workspace is suspended")
    proof_id = new_id()
    ext = svc.RECEIPT_TYPES[body.content_type]
    key = f"payments/{id}/receipts/{proof_id}/upload.{ext}"
    filename = re.sub(r"[\x00-\x1f\x7f]", "", PurePath(body.filename.replace("\\", "/")).name)[:200] or f"receipt.{ext}"
    db.add(
        PaymentProof(
            id=proof_id,
            checkout_id=id,
            key=key,
            filename=filename,
            content_type=body.content_type,
            size_bytes=body.size_bytes,
        )
    )
    await db.commit()
    return {
        "proof_id": proof_id,
        "upload_url": registry.get_storage().presign_put(key, 600),
        "max_bytes": svc.MAX_RECEIPT_BYTES,
    }


@router.post(
    "/v1/billing/transfer/{id}/uploads/confirm", dependencies=[Depends(limit("payment-proof-confirm", 30, 3600))]
)
async def confirm_upload(
    id: str, body: ProofId, p: Principal = Depends(current_principal), db: AsyncSession = Depends(get_session)
):
    await owned(db, id, p)
    proof = (
        await db.execute(
            update(PaymentProof)
            .where(PaymentProof.id == body.proof_id, PaymentProof.checkout_id == id)
            .values(status=PaymentProof.status)
            .returning(PaymentProof)
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()
    if not proof or proof.checkout_id != id:
        raise HTTPException(404, "Receipt upload not found")
    if proof.status == "clean":
        return {"proof_id": proof.id, "status": "clean"}
    if proof.status != "pending":
        raise HTTPException(409, "Upload a new receipt")
    storage = registry.get_storage()
    try:
        data = await storage.get(proof.key, svc.MAX_RECEIPT_BYTES)
        if not data or len(data) != proof.size_bytes:
            raise uploads.InvalidUpload("The uploaded size did not match. Please upload the complete receipt.")
        uploads.validate_content(proof.content_type, data)
        scan = await registry.get_scanner().scan(data)
        if not scan.clean:
            raise uploads.InvalidUpload("This receipt was blocked by our security scan.")
    except (uploads.InvalidUpload, ObjectTooLarge) as error:
        proof.status = "rejected"
        await storage.delete(proof.key)
        await db.commit()
        raise HTTPException(422, str(error)) from error
    except Exception as error:
        raise HTTPException(503, "The receipt could not be checked. Please try again.") from error
    raw_key = proof.key
    # Publish an immutable server-written copy: the client's PUT URL cannot alter reviewed evidence.
    verified_key = raw_key.replace("/upload.", "/verified.")
    await storage.put(verified_key, data, proof.content_type)
    proof.key, proof.sha256, proof.status = verified_key, hashlib.sha256(data).hexdigest(), "clean"
    await storage.delete(raw_key)
    await db.commit()
    return {"proof_id": proof.id, "status": "clean"}


@router.post("/v1/billing/transfer/{id}/submit", dependencies=[Depends(limit("payment-proof-submit", 10, 3600))])
async def submit(
    id: str,
    body: SubmitProof,
    bg: BackgroundTasks,
    p: Principal = Depends(current_principal),
    db: AsyncSession = Depends(get_session),
):
    await owned(db, id, p)
    co = await locked(db, id)
    review = await db.get(TransferReview, id)
    if not review:
        raise HTTPException(404, "Transfer purchase not found")
    if co.paid_at:
        return await output(db, co)
    if p.workspace.suspended:
        raise HTTPException(403, "This workspace is suspended")
    if review.status == "pending_review":
        if review.proof_id != body.proof_id:
            raise HTTPException(409, "Your receipt is already being reviewed")
        await db.commit()
        bg.add_task(svc.deliver_notifications, id)
        return await output(db, co)
    if review.status == "rejected" and review.proof_id == body.proof_id:
        raise HTTPException(422, "Upload a corrected receipt before resubmitting.")
    proof = await db.get(PaymentProof, body.proof_id)
    if not proof or proof.checkout_id != id or proof.status != "clean" or not proof.sha256:
        raise HTTPException(422, "Upload and confirm a valid payment receipt first")
    review.proof_id, review.status = proof.id, "pending_review"
    review.revision += 1
    review.submitted_by, review.submitted_at = p.user.email, utcnow()
    review.reason, review.reviewed_by, review.reviewed_at = "", None, None
    co.status = "pending_review"
    co.payment_context = {**co.payment_context, "sender_reference": body.sender_reference.strip()}
    audit(
        db,
        p.user.email,
        "payment.receipt_submitted",
        target_type="checkout",
        target_id=id,
        detail={"proof_id": proof.id, "revision": review.revision},
    )
    await svc.queue_notifications(db, co, review, "submitted")
    await db.commit()
    bg.add_task(svc.deliver_notifications, id)
    return await output(db, co)


@router.get("/v1/admin/bank-transfers")
async def overview(_: Principal = Depends(require("finance.view")), db: AsyncSession = Depends(get_session)):
    rows = (
        (
            await db.execute(
                select(Checkout)
                .join(Workspace)
                .where(Checkout.provider == svc.PROVIDER, Workspace.deleted_at.is_(None))
                # Always include the complete action queue, even if newer unsubmitted
                # purchases have pushed a receipt outside the recent-history window.
                .where(
                    or_(
                        Checkout.status == "pending_review",
                        Checkout.id.in_(
                            select(Checkout.id)
                            .where(Checkout.provider == svc.PROVIDER)
                            .order_by(Checkout.created_at.desc())
                            .limit(100)
                        ),
                    )
                )
                .order_by(case((Checkout.status == "pending_review", 0), else_=1), Checkout.created_at.desc())
            )
        )
        .scalars()
        .all()
    )
    return [await output(db, co, admin=True) for co in rows]


@router.get("/v1/admin/bank-transfer-accounts")
async def get_accounts(_: Principal = Depends(require("finance.view")), db: AsyncSession = Depends(get_session)):
    result = {}
    row = await db.get(SystemSetting, svc.ACCOUNTS_KEY)
    for currency in ["USD", "NGN"]:
        saved = (row.value if row else {}).get(currency)
        if saved is not None:
            result[currency] = saved
        else:
            try:
                result[currency] = await svc.receiving_account(db, currency)
            except HTTPException:
                result[currency] = None
    return result


@router.put("/v1/admin/bank-transfer-accounts/{currency}")
async def set_account(
    currency: Literal["USD", "NGN"],
    body: svc.BankAccount,
    p: Principal = Depends(require("settings.manage")),
    db: AsyncSession = Depends(get_session),
):
    # Serialize settings edits so USD and NGN changes cannot overwrite each other.
    async def lock_setting():
        return (
            await db.execute(
                update(SystemSetting)
                .where(SystemSetting.key == svc.ACCOUNTS_KEY)
                .values(updated_at=SystemSetting.updated_at)
                .returning(SystemSetting)
                .execution_options(populate_existing=True)
            )
        ).scalar_one_or_none()

    row = await lock_setting()
    if row is None:
        try:
            async with db.begin_nested():
                db.add(SystemSetting(key=svc.ACCOUNTS_KEY, value={}))
                await db.flush()
        except IntegrityError:
            pass  # Another administrator created the setting concurrently.
        row = await lock_setting()
    assert row is not None
    row.value = {**row.value, currency: body.model_dump()}
    row.updated_by, row.updated_at = p.user.email, utcnow()
    audit(db, p.user.email, "payment.bank_account_updated", target_type="settings", target_id=currency)
    await db.commit()
    return body


@router.post("/v1/admin/bank-transfers/{id}/approve")
async def approve(
    id: str,
    body: Approval,
    bg: BackgroundTasks,
    p: Principal = Depends(require("finance.manage")),
    db: AsyncSession = Depends(get_session),
):
    co = await locked(db, id)
    review = await db.get(TransferReview, id)
    if co.paid_at:
        await db.commit()
        return {"result": "duplicate", "status": "paid"}
    ws = await db.get(Workspace, co.workspace_id)
    if not review or review.status != "pending_review" or not ws or ws.deleted_at or ws.suspended:
        raise HTTPException(409, "This payment is not available for approval")
    if review.revision != body.revision or review.proof_id != body.proof_id:
        raise HTTPException(409, "The receipt has changed. Refresh and review the current receipt.")
    proof = await db.get(PaymentProof, review.proof_id)
    if not proof or proof.status != "clean" or not proof.sha256:
        raise HTTPException(409, "No verified receipt is attached")
    if body.payment_reference == co.payment_context["reference"].upper():
        raise HTTPException(422, "Use the bank's transaction reference, not the checkout narration.")

    # Do not reuse a transfer already allocated through the legacy online-verification path.
    def normalized(column):
        for separator in [" ", "-", "/", "_", ".", ":"]:
            column = func.replace(column, separator, "")
        return func.upper(column)

    legacy = (
        await db.execute(
            select(BankReceipt.id).where(
                BankReceipt.status == "matched",
                or_(
                    normalized(BankReceipt.transfer_id) == body.payment_reference,
                    normalized(BankReceipt.data["unique_reference"].as_string()) == body.payment_reference,
                ),
            )
        )
    ).first()
    if legacy:
        raise HTTPException(409, "This bank reference has already credited another purchase")
    try:
        review.payment_reference, review.approved_proof_hash = body.payment_reference, proof.sha256
        review.status, review.reviewed_by, review.reviewed_at, review.reason = (
            "approved",
            p.user.email,
            utcnow(),
            body.reason,
        )
        await db.flush()  # Unique reference and receipt hash prevent reuse across purchases.
        from app.routes.billing import handle_payment_event

        result = await handle_payment_event(
            db, PaymentEvent(event_id=f"manual-bank:{id}", checkout_id=id, status="paid", amount_usd=co.amount_usd)
        )
        audit(
            db,
            p.user.email,
            "payment.transfer_approved",
            target_type="checkout",
            target_id=id,
            detail={
                "credits": str(co.credits),
                "reference": body.payment_reference,
                "proof_id": proof.id,
                "reason": body.reason,
            },
        )
        await svc.queue_notifications(db, co, review, "approved")
        await db.commit()
    except IntegrityError as error:
        await db.rollback()
        raise HTTPException(
            409, "This transfer reference or receipt has already been used for an approved purchase."
        ) from error
    bg.add_task(svc.deliver_notifications, id)
    return {"result": result, "status": "paid", "credits": str(co.credits)}


@router.post("/v1/admin/bank-transfers/{id}/reject")
async def reject(
    id: str,
    body: Rejection,
    bg: BackgroundTasks,
    p: Principal = Depends(require("finance.manage")),
    db: AsyncSession = Depends(get_session),
):
    co = await locked(db, id)
    review = await db.get(TransferReview, id)
    if co.paid_at or not review or review.status != "pending_review":
        raise HTTPException(409, "This payment cannot be rejected")
    if review.revision != body.revision or review.proof_id != body.proof_id:
        raise HTTPException(409, "The receipt has changed. Refresh and review the current receipt.")
    review.status, review.reason = "rejected", body.reason
    review.reviewed_by, review.reviewed_at = p.user.email, utcnow()
    co.status = "rejected"
    audit(
        db,
        p.user.email,
        "payment.transfer_rejected",
        target_type="checkout",
        target_id=id,
        detail={"reason": body.reason},
    )
    await svc.queue_notifications(db, co, review, "rejected")
    await db.commit()
    bg.add_task(svc.deliver_notifications, id)
    return {"status": "rejected"}
