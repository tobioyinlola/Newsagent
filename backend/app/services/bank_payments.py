"""NGN bank collections: references identify an order, online verification proves payment."""

import re
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from sqlalchemy import update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.integrations.billing.base import PaymentEvent
from app.integrations.billing.nuvion import NuvionBilling, NuvionError, PaymentMismatch
from app.models import Checkout
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


def check_transfer(co: Checkout, transfer: dict, billing: NuvionBilling) -> None:
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
        or transfer.get("narration", "").strip() != reference(co)
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


async def settle_transfer(db: AsyncSession, co: Checkout, transfer: dict, billing: NuvionBilling) -> str:
    check_transfer(co, transfer, billing)
    if co.paid_at:
        return "duplicate"
    await db.execute(
        update(Checkout)
        .where(Checkout.id == co.id, Checkout.provider_ref.is_(None))
        .values(provider_ref=transfer["id"])
    )
    await db.commit()
    await db.refresh(co)
    if co.provider_ref != transfer["id"]:
        return "additional_transfer_requires_review"
    from app.routes.billing import handle_payment_event

    result = await handle_payment_event(
        db,
        PaymentEvent(
            event_id=f"nuvion-bank:{transfer['id']}", checkout_id=co.id, status="paid", amount_usd=co.amount_usd
        ),
    )
    await db.commit()
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
    narration = transfer.get("narration", "").strip()
    if not re.fullmatch(r"CF[0-9a-f]{32}", narration):
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
