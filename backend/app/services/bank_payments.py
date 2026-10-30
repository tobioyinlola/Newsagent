"""NGN bank collections: references identify an order, online verification proves payment."""

import re
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.integrations.billing.base import PaymentEvent
from app.integrations.billing.nuvion import NuvionBilling, NuvionError, PaymentMismatch
from app.models import BankReceipt, Checkout
from app.models.base import new_id, utcnow
from app.services import payments


def reference(checkout: Checkout) -> str:
    return "CF" + checkout.id


async def receiving_details(billing: NuvionBilling) -> dict:
    data = await billing.call("GET", f"/accounts/{billing.account_id}", params={"entity_id": billing.entity_id})
    account = data.get("account", {})
    if (
        account.get("id") != billing.account_id
        or account.get("entity_id") != billing.entity_id
        or account.get("currency") != "NGN"
        or account.get("deleted")
    ):
        raise NuvionError("The naira receiving account is unavailable. Please choose another payment method.")
    for detail in data.get("account_details", []):
        if (
            detail.get("account_id") == billing.account_id
            and detail.get("entity_id") == billing.entity_id
            and detail.get("currency") == "NGN"
            and detail.get("status") == "active"
            and not detail.get("deleted")
            and detail.get("config", {}).get("inflow_enabled") is True
            and detail.get("account_number")
            and detail.get("issuer", {}).get("name")
        ):
            return {
                "account_number": detail["account_number"],
                "bank_name": detail["issuer"]["name"],
                "beneficiary_name": detail.get("beneficiary_name"),
                "account_label": account.get("display_name", ""),
            }
    raise NuvionError("Naira bank transfers are temporarily unavailable. Please choose another payment method.")


def check_transfer(co: Checkout, transfer: dict, billing: NuvionBilling, *, manual=False) -> None:
    context = co.payment_context
    amount = transfer.get("amount")
    created = transfer.get("created")
    if (
        co.provider != "nuvion_bank"
        or billing.currency != "NGN"
        or any(context.get(k) != v for k, v in billing.context.items())
        or transfer.get("account_id") != context["account_id"]
        or transfer.get("entity_id") != context["entity_id"]
        or transfer.get("currency") != "NGN"
        or transfer.get("type") != "inflow"
        or transfer.get("payment_type") != "bank-transfer"
        or transfer.get("status") != "successful"
        or (not manual and transfer.get("narration", "").strip() != reference(co))
        or (
            manual
            and re.fullmatch(r"CF[0-9a-f]{32}", transfer.get("narration", "").strip())
            and transfer.get("narration", "").strip() != reference(co)
        )
        or not isinstance(amount, int)
        or isinstance(amount, bool)
        or Decimal(amount) != Decimal(context["amount_ngn"]) * 100
        or not isinstance(created, int)
        or isinstance(created, bool)
        or created < int(payments.utc(co.created_at).timestamp() * 1000)
        or not isinstance(transfer.get("id"), str)
        or not transfer["id"]
    ):
        raise PaymentMismatch("The transfer does not match this purchase. No credits were added; contact support.")


async def remember_receipt(db: AsyncSession, transfer: dict, billing: NuvionBilling) -> BankReceipt:
    amount, created, id = transfer.get("amount"), transfer.get("created"), transfer.get("id")
    if (
        transfer.get("account_id") != billing.account_id
        or transfer.get("entity_id") != billing.entity_id
        or transfer.get("currency") != "NGN"
        or transfer.get("type") != "inflow"
        or transfer.get("payment_type") != "bank-transfer"
        or transfer.get("status") != "successful"
        or not isinstance(amount, int)
        or isinstance(amount, bool)
        or not 0 < amount <= 10**14
        or not isinstance(created, int)
        or isinstance(created, bool)
        or not 0 < created <= int(utcnow().timestamp() * 1000) + 60000
        or not isinstance(id, str)
        or not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", id)
    ):
        raise PaymentMismatch("The bank transfer is not a verified settled NGN inflow to this account.")
    data = {
        k: transfer.get(k)
        for k in ["id", "account_id", "entity_id", "currency", "amount", "type", "payment_type", "status", "created"]
    }
    data.update(
        narration=str(transfer.get("narration") or "")[:1000],
        unique_reference=str(transfer.get("unique_reference") or "")[:200],
    )
    await db.commit()  # End earlier read transactions before the unique receipt insertion.
    insert = pg_insert if db.get_bind().dialect.name == "postgresql" else sqlite_insert
    await db.execute(
        insert(BankReceipt)
        .values(
            id=new_id(),
            api_url=billing.base_url,
            transfer_id=id,
            data=data,
            status="unmatched",
            created_at=utcnow(),
            updated_at=utcnow(),
        )
        .on_conflict_do_nothing(index_elements=["api_url", "transfer_id"])
    )
    await db.commit()
    return (
        await db.execute(
            select(BankReceipt).where(BankReceipt.api_url == billing.base_url, BankReceipt.transfer_id == id)
        )
    ).scalar_one()


async def settle_transfer(
    db: AsyncSession,
    co: Checkout,
    transfer: dict,
    billing: NuvionBilling,
    *,
    actor: str | None = None,
    reason: str = "",
) -> str:
    check_transfer(co, transfer, billing, manual=actor is not None)
    receipt = await remember_receipt(db, transfer, billing)
    receipt_id, checkout_id = receipt.id, co.id
    await db.commit()
    receipt = (
        await db.execute(
            update(BankReceipt)
            .where(BankReceipt.id == receipt_id)
            .values(updated_at=utcnow())
            .returning(BankReceipt)
            .execution_options(populate_existing=True)
        )
    ).scalar_one()
    if receipt.checkout_id and receipt.checkout_id != checkout_id:
        raise PaymentMismatch("This transfer has already been assigned to another purchase.")
    co = (
        await db.execute(
            select(Checkout)
            .where(Checkout.id == checkout_id)
            .with_for_update()
            .execution_options(populate_existing=True)
        )
    ).scalar_one()
    check_transfer(co, transfer, billing, manual=actor is not None)
    if (co.provider_ref and co.provider_ref != transfer["id"]) or (co.paid_at and co.provider_ref != transfer["id"]):
        return "additional_transfer_requires_review"
    # Also detect allocations made before the receipt registry existed.
    other = (
        await db.execute(select(Checkout.id).where(Checkout.provider_ref == transfer["id"], Checkout.id != co.id))
    ).first()
    if other:
        raise PaymentMismatch("This transfer has already been assigned to another purchase.")
    co.provider_ref = transfer["id"]
    receipt.checkout_id, receipt.status = co.id, "matched"
    if not receipt.matched_at:
        receipt.matched_by, receipt.matched_at = actor or "automatic-reference-match", utcnow()
    from app.routes.billing import handle_payment_event

    result = await handle_payment_event(
        db,
        PaymentEvent(
            event_id=f"nuvion-bank:{transfer['id']}", checkout_id=co.id, status="paid", amount_usd=co.amount_usd
        ),
    )
    claim = co.payment_context.get("bank_claim")
    if claim and claim.get("transfer_id") == transfer["id"]:
        co.payment_context = {**co.payment_context, "bank_claim": {**claim, "status": "matched"}}
    if actor and result == "granted":
        from app.services.audit import audit

        audit(
            db,
            actor,
            "payment.bank_manually_matched",
            target_type="checkout",
            target_id=co.id,
            detail={
                "transfer_id": transfer["id"],
                "amount_ngn": str(billing.amount(co)),
                "credits": str(co.credits),
                "reason": reason,
                "original_narration": receipt.data["narration"],
            },
        )
    await db.commit()
    import logging

    logging.getLogger("payments").info(
        "Bank payment settlement: checkout=%s transfer=%s result=%s", co.id, transfer["id"], result
    )
    if result == "granted":
        await payments.credit_email(db, co)
    return result


async def process_inflow(db: AsyncSession, data) -> str:
    if not get_settings().nuvion_ngn_account_id:
        return "ignored"
    if (
        not isinstance(data, dict)
        or not isinstance(data.get("id"), str)
        or not re.fullmatch(r"[A-Za-z0-9_-]{1,100}", data["id"])
    ):
        return "ignored"
    billing = payments.provider(currency="NGN")
    if data.get("account_id") != billing.account_id:
        return "ignored"
    # The signed notification is a wake-up signal; only current provider data selects an order.
    transfer = await billing.call("GET", f"/transfers/{data['id']}", params={"entity_id": billing.entity_id})
    if transfer.get("id") != data["id"]:
        raise PaymentMismatch("Transfer ID mismatch")
    cached = await remember_receipt(db, transfer, billing)
    if cached.status == "matched" and cached.checkout_id:
        return "duplicate"
    narration = transfer.get("narration", "").strip()
    if not re.fullmatch(r"CF[0-9a-f]{32}", narration):
        import logging

        logging.getLogger("payments").warning(
            "Bank inflow requires review: transfer=%s reason=unmatched_reference", transfer["id"]
        )
        return "unmatched_reference"
    co = await db.get(Checkout, narration[2:])
    if co is None or co.provider != "nuvion_bank":
        return "unknown_checkout"
    if transfer.get("id") != data["id"]:
        raise PaymentMismatch("Transfer ID mismatch")
    return await settle_transfer(db, co, transfer, billing)


async def reconcile_bank(db: AsyncSession, co: Checkout, billing: NuvionBilling) -> str:
    if co.paid_at:
        return "duplicate"
    if co.last_verified_at and datetime.now(UTC) - payments.utc(co.last_verified_at) < timedelta(seconds=15):
        return "pending"
    co.last_verified_at = datetime.now(UTC)
    await db.commit()
    if co.provider_ref:
        transfer = await billing.call("GET", f"/transfers/{co.provider_ref}", params={"entity_id": billing.entity_id})
        return await settle_transfer(db, co, transfer, billing)
    params = {
        "entity_id": billing.entity_id,
        "account_id": billing.account_id,
        "type": "inflow",
        "payment_type": "bank-transfer",
        "status": "successful",
        "currency": "NGN",
        "amount_min": int(billing.amount(co) * 100),
        "amount_max": int(billing.amount(co) * 100),
        "date_from": payments.utc(co.created_at).isoformat(),
        "limit": 50,
    }
    for _ in range(10):
        page = await billing.call("GET", "/transfers", params=params)
        for item in page.get("data", []):
            if item.get("account_id") == billing.account_id and item.get("status") == "successful":
                await remember_receipt(db, item, billing)
            if item.get("narration", "").strip() == reference(co):
                transfer = await billing.call(
                    "GET", f"/transfers/{item['id']}", params={"entity_id": billing.entity_id}
                )
                if transfer.get("id") != item["id"]:
                    raise PaymentMismatch("Transfer ID mismatch")
                return await settle_transfer(db, co, transfer, billing)
        pagination = page.get("meta", {}).get("pagination", {})
        if not pagination.get("has_next") or not pagination.get("next_cursor"):
            break
        params["cursor"] = pagination["next_cursor"]
    return "pending"


async def find_claim(db: AsyncSession, co: Checkout, receipt_reference: str, billing: NuvionBilling) -> BankReceipt:
    params = {
        "entity_id": billing.entity_id,
        "account_id": billing.account_id,
        "type": "inflow",
        "payment_type": "bank-transfer",
        "status": "successful",
        "currency": "NGN",
        "amount_min": int(billing.amount(co) * 100),
        "amount_max": int(billing.amount(co) * 100),
        "date_from": payments.utc(co.created_at).isoformat(),
        "limit": 50,
    }
    for _ in range(10):
        page = await billing.call("GET", "/transfers", params=params)
        for item in page.get("data", []):
            if receipt_reference in {item.get("id"), item.get("unique_reference")}:
                transfer = await billing.call(
                    "GET", f"/transfers/{item['id']}", params={"entity_id": billing.entity_id}
                )
                if transfer.get("id") != item["id"] or receipt_reference not in {
                    transfer.get("id"),
                    transfer.get("unique_reference"),
                }:
                    raise PaymentMismatch("The bank transaction reference could not be verified.")
                check_transfer(co, transfer, billing, manual=True)
                narration = transfer.get("narration", "").strip()
                if re.fullmatch(r"CF[0-9a-f]{32}", narration) and narration != reference(co):
                    raise PaymentMismatch("This transfer identifies a different purchase.")
                receipt = await remember_receipt(db, transfer, billing)
                if receipt.checkout_id and receipt.checkout_id != co.id:
                    raise PaymentMismatch("This transfer has already been assigned to another purchase.")
                return receipt
        pagination = page.get("meta", {}).get("pagination", {})
        if not pagination.get("has_next") or not pagination.get("next_cursor"):
            break
        params["cursor"] = pagination["next_cursor"]
    raise PaymentMismatch(
        "We could not verify a settled transfer with that transaction reference for this purchase. Check the reference on your receipt or contact support."
    )
