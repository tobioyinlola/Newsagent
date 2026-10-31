"""Receipt submission is evidence for a human reviewer, never automatic payment proof."""

import hashlib
import json
from datetime import timedelta

from fastapi import HTTPException
from pydantic import BaseModel, ConfigDict, Field
from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import session_maker
from app.integrations.billing.nuvion import NuvionError
from app.models import Checkout, StaffMember, SystemSetting, TransferMail, TransferReview, Workspace
from app.models.base import utcnow
from app.services import payments, rbac
from app.services.notifications import send_email

PROVIDER = "manual_bank"
ACCOUNTS_KEY = "bank_transfer_accounts"
MAX_RECEIPT_BYTES = 5 * 1024 * 1024
RECEIPT_TYPES = {"image/png": "png", "image/jpeg": "jpg", "application/pdf": "pdf"}


class BankAccount(BaseModel):
    model_config = ConfigDict(str_strip_whitespace=True)
    enabled: bool = True
    bank_name: str = Field(min_length=2, max_length=200)
    account_number: str = Field(min_length=3, max_length=100)
    beneficiary_name: str = Field(default="", max_length=200)
    account_label: str = Field(default="", max_length=200)
    routing_number: str = Field(default="", max_length=100)
    swift_code: str = Field(default="", max_length=100)
    iban: str = Field(default="", max_length=100)
    bank_address: str = Field(default="", max_length=500)
    instructions: str = Field(default="", max_length=1500)


def recipient_display(bank: dict) -> str:
    name = str(bank.get("beneficiary_name") or bank.get("account_label") or "").strip()
    company = "Sydney Money Technology Inc"
    return name if "sydney money technology" in name.lower() else " / ".join(filter(None, [name, company]))


def receiving_key(currency: str, bank: dict) -> str:
    values = [
        currency,
        *[
            "".join(str(bank.get(k) or "").upper().split())
            for k in ["account_number", "routing_number", "swift_code", "iban"]
        ],
    ]
    return hashlib.sha256(json.dumps(values).encode()).hexdigest()


async def receiving_account(db: AsyncSession, currency: str) -> dict:
    row = await db.get(SystemSetting, ACCOUNTS_KEY)
    override = (row.value if row else {}).get(currency)
    if override:
        bank = BankAccount.model_validate(override)
        if not bank.enabled:
            raise HTTPException(503, f"{currency} bank transfers are temporarily unavailable.")
        return bank.model_dump()
    try:
        billing = payments.provider(currency=currency)
        data = await billing.call("GET", f"/accounts/{billing.account_id}", params={"entity_id": billing.entity_id})
        account = data.get("account", {})
        if (
            account.get("id") != billing.account_id
            or account.get("entity_id") != billing.entity_id
            or account.get("currency") != currency
            or account.get("deleted")
        ):
            raise NuvionError("Bank account unavailable")
        for detail in data.get("account_details", []):
            if (
                detail.get("account_id") != billing.account_id
                or detail.get("entity_id") != billing.entity_id
                or detail.get("currency") != currency
                or detail.get("status") != "active"
                or detail.get("deleted")
                or detail.get("config", {}).get("inflow_enabled") is not True
            ):
                continue
            issuer = detail.get("issuer") or {}
            meta = issuer.get("meta") or {}
            number = detail.get("account_number") or meta.get("account_number")
            name = meta.get("bank_name") or issuer.get("name")
            if number and name:
                return BankAccount(
                    bank_name=name,
                    account_number=number,
                    beneficiary_name=detail.get("beneficiary_name") or meta.get("receiver_name") or "",
                    account_label=account.get("display_name") or "",
                    routing_number=detail.get("routing_number") or meta.get("routing_number") or "",
                    swift_code=detail.get("swift_code") or meta.get("swift_code") or "",
                    iban=detail.get("iban") or "",
                    bank_address=meta.get("bank_address") or "",
                ).model_dump()
    except NuvionError:
        pass
    raise HTTPException(503, f"{currency} bank transfer details are not available. Please contact the team.")


async def accounts_available(db: AsyncSession) -> dict[str, bool]:
    row = await db.get(SystemSetting, ACCOUNTS_KEY)
    configured = row.value if row else {}
    settings = get_settings()
    return {
        currency: bool(configured[currency].get("enabled", True))
        if currency in configured
        else bool(settings.billing_provider == "nuvion" and getattr(settings, key))
        for currency, key in [("USD", "nuvion_account_id"), ("NGN", "nuvion_ngn_account_id")]
    }


async def recipients(db: AsyncSession) -> set[str]:
    rows = (await db.execute(select(StaffMember).where(StaffMember.status == "active"))).scalars()
    return rbac.owner_emails() | {row.email.lower() for row in rows if "finance.manage" in (row.permissions or [])}


async def queue_notifications(db: AsyncSession, co: Checkout, review: TransferReview, kind: str) -> None:
    ws = await db.get(Workspace, co.workspace_id)
    currency = co.payment_context["currency"]
    amount = co.payment_context["amount"]
    details = f"Purchase: {co.id}\nBusiness: {ws.name if ws else ''}\nCustomer: {review.submitted_by or ''}\nAmount: {currency} {amount}\nCredits: {co.credits}\nTransfer narration: {co.payment_context['reference']}"
    admin_url = f"{get_settings().app_base_url}/admin/revenue"
    user_url = f"{get_settings().app_base_url}/billing/transfer/{co.id}"
    messages: list[tuple[str | None, str, str, str]]
    if kind == "submitted":
        messages = [
            (
                email,
                "admin_action",
                "Action required: bank payment needs credit approval",
                f"A customer has submitted a bank-transfer receipt. Please verify the funds arrived and approve or reject the purchase.\n\n{details}\n\nReview securely: {admin_url}",
            )
            for email in sorted(await recipients(db))
        ]
        messages += [
            (
                review.submitted_by,
                "customer_submitted",
                "Payment receipt received",
                f"We received your payment receipt. Your credits will be added in a few minutes once our team confirms the transfer. Please do not pay again.\n\n{details}\n\nTrack your payment: {user_url}",
            )
        ]
    elif kind == "approved":
        messages = [
            (
                review.submitted_by,
                "customer_approved",
                "Payment confirmed — credits added",
                f"Your bank transfer has been approved and {co.credits} credits have been added to your wallet.\n\n{details}\nBank reference: {review.payment_reference}\n\nView your payment: {user_url}",
            )
        ]
        messages += [
            (
                email,
                "admin_approved",
                "Bank payment approved — credits added",
                f"This bank purchase has been approved by {review.reviewed_by}.\n\n{details}\nBank reference: {review.payment_reference}\n\nView: {admin_url}",
            )
            for email in sorted(await recipients(db))
        ]
    else:
        messages = [
            (
                review.submitted_by,
                "customer_rejected",
                "Payment receipt needs attention",
                f"Our team could not approve this receipt. No credits have been added.\nReason: {review.reason}\n\n{details}\n\nView the payment and upload a corrected receipt: {user_url}",
            )
        ]
    for email, message_kind, subject, body in messages:
        if not email:
            continue
        exists = (
            await db.execute(
                select(TransferMail.id).where(
                    TransferMail.checkout_id == co.id,
                    TransferMail.revision == review.revision,
                    TransferMail.kind == message_kind,
                    TransferMail.recipient == email,
                )
            )
        ).first()
        if not exists:
            db.add(
                TransferMail(
                    checkout_id=co.id,
                    revision=review.revision,
                    kind=message_kind,
                    recipient=email,
                    subject=subject,
                    body=body,
                )
            )
    await db.flush()


async def deliver_notifications(checkout_id: str | None = None) -> int:
    sent = 0
    cutoff = utcnow() - timedelta(minutes=10)
    async with session_maker()() as db:
        query = select(TransferMail.id).where(
            TransferMail.attempts < 10,
            or_(
                TransferMail.status == "pending",
                (TransferMail.status == "sending") & (TransferMail.last_attempt_at < cutoff),
            ),
        )
        if checkout_id:
            query = query.where(TransferMail.checkout_id == checkout_id)
        ids = list((await db.execute(query.order_by(TransferMail.created_at).limit(100))).scalars())
        await db.commit()
        for id in ids:
            mail = (
                await db.execute(
                    update(TransferMail)
                    .where(
                        TransferMail.id == id,
                        TransferMail.attempts < 10,
                        or_(
                            TransferMail.status == "pending",
                            (TransferMail.status == "sending") & (TransferMail.last_attempt_at < cutoff),
                        ),
                    )
                    .values(status="sending", attempts=TransferMail.attempts + 1, last_attempt_at=utcnow())
                    .returning(TransferMail)
                    .execution_options(populate_existing=True)
                )
            ).scalar_one_or_none()
            if mail is None:
                await db.rollback()
                continue
            co = await db.get(Checkout, mail.checkout_id)
            review = await db.get(TransferReview, mail.checkout_id)
            ws = await db.get(Workspace, co.workspace_id) if co else None
            stale = not co or not review or not ws or ws.deleted_at or mail.revision != review.revision
            if mail.kind in {"admin_action", "customer_submitted"} and (
                not review or review.status != "pending_review"
            ):
                stale = True
            if mail.kind.startswith("admin_") and mail.recipient not in await recipients(db):
                stale = True
            if stale:
                mail.status = "cancelled"
                await db.commit()
                continue
            await db.commit()
            ok = await send_email(mail.recipient, mail.subject, mail.body)
            mail.status = "sent" if ok else "failed" if mail.attempts >= 10 else "pending"
            if ok:
                mail.sent_at = utcnow()
                sent += 1
            await db.commit()
    return sent
