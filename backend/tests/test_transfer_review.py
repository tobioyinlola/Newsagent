import asyncio
import base64
from decimal import Decimal

import pytest
from sqlalchemy import select

from app.config import get_settings
from app.integrations import registry
from app.integrations.malware.mock import EICAR
from app.models import PaymentProof, StaffMember, TransferMail, TransferReview, User, Workspace
from app.services import ledger, rbac
from app.services import transfer_reviews as svc
from app.services.privacy import delete_workspace, export_workspace
from tests.conftest import OPS, OWNER
from tests.helpers import api_path

PNG = base64.b64decode(
    "iVBORw0KGgoAAAANSUhEUgAAAAEAAAABCAYAAAAfFcSJAAAADUlEQVR42mP8z8BQDwAEhQGAhKmMIQAAAABJRU5ErkJggg=="
)


@pytest.fixture
async def review_mode(client, workspace, usage_accounting, monkeypatch):
    monkeypatch.setattr(get_settings(), "bank_transfer_review_enabled", True)
    for currency, number in [("USD", "1111222233"), ("NGN", "4444555566")]:
        r = await client.put(
            f"/v1/admin/bank-transfer-accounts/{currency}",
            headers=OPS,
            json={
                "bank_name": "Test receiving bank",
                "beneficiary_name": "Test Cover Founder",
                "account_number": number,
                "routing_number": "021000021" if currency == "USD" else "",
            },
        )
        assert r.status_code == 200, r.text


async def checkout(client, currency="USD", custom=False):
    body = {"amount_usd": "10", "currency": currency, "payment_method": "bank_transfer"}
    if custom:
        q = (await client.post("/v1/billing/custom-quote", headers=OWNER, json={"credits": "220"})).json()
        body.update(amount_usd=q["amount_usd"], custom_credits=q["credits"], custom_quote_version=q["quote_version"])
    if currency == "NGN":
        body["ngn_per_usd"] = str(get_settings().ngn_per_usd)
    r = await client.post("/v1/billing/checkout", headers=OWNER, json=body)
    assert r.status_code == 200, r.text
    return r.json()["checkout_id"]


async def upload(client, id, content=PNG, content_type="image/png"):
    r = await client.post(
        f"/v1/billing/transfer/{id}/uploads",
        headers=OWNER,
        json={"filename": "receipt.png", "content_type": content_type, "size_bytes": len(content)},
    )
    assert r.status_code == 200, r.text
    result = r.json()
    assert (await client.put(api_path(result["upload_url"]), content=content)).status_code == 200
    return result


async def submit(client, id, content=PNG):
    result = await upload(client, id, content)
    confirmed = await client.post(
        f"/v1/billing/transfer/{id}/uploads/confirm", headers=OWNER, json={"proof_id": result["proof_id"]}
    )
    assert confirmed.status_code == 200, confirmed.text
    r = await client.post(
        f"/v1/billing/transfer/{id}/submit",
        headers=OWNER,
        json={"proof_id": result["proof_id"], "sender_reference": "PAYER-BANK-12345"},
    )
    assert r.status_code == 200, r.text
    return r.json()


def approval(payment, reference="BANK-TRANSFER-123456"):
    return {
        "proof_id": payment["receipt"]["id"],
        "revision": payment["revision"],
        "funds_confirmed": True,
        "payment_reference": reference,
        "reason": "Verified the exact amount arrived in the receiving bank statement.",
    }


async def balance(maker, workspace):
    async with maker() as db:
        ws = await db.get(Workspace, workspace)
        assert await ledger.ledger_sum(db, workspace) == ws.credit_balance
        return ws.credit_balance


@pytest.mark.parametrize("currency", ["USD", "NGN"])
@pytest.mark.parametrize("custom", [False, True])
async def test_transfer_receipt_approval_and_history_credit_once(
    client, workspace, maker, review_mode, currency, custom
):
    methods = (await client.get("/v1/billing/payment-methods", headers=OWNER)).json()
    assert not methods["usd_card"] and not methods["ngn_card"]
    assert methods["usd_bank_transfer"] and methods["ngn_bank_transfer"] and methods["manual_review"]
    assert (
        await client.post(
            "/v1/billing/checkout",
            headers=OWNER,
            json={"amount_usd": "10", "currency": currency, "payment_method": "card"},
        )
    ).status_code == 409
    id = await checkout(client, currency, custom)
    payment = await submit(client, id)
    assert payment["status"] == "pending_review" and payment["receipt"]["url"]
    assert await balance(maker, workspace) == 10
    amount = Decimal("220") if custom else Decimal("3.70")
    path = f"/v1/admin/bank-transfers/{id}/approve"
    assert (await client.post(path, headers=OWNER, json=approval(payment))).status_code == 403
    assert (
        await client.post(path, headers=OPS, json={**approval(payment), "funds_confirmed": False})
    ).status_code == 422
    for _ in range(2):
        r = await client.post(path, headers=OPS, json=approval(payment))
        assert r.status_code == 200 and r.json()["status"] == "paid", r.text
    assert await balance(maker, workspace) == 10 + amount
    history = (await client.get("/v1/billing/checkouts", headers=OWNER)).json()
    assert (
        history[0]["review_required"]
        and history[0]["status"] == "paid"
        and history[0]["payment_method"] == "bank_transfer"
    )
    report = (await client.get("/v1/admin/bank-transfers", headers=OPS)).json()
    assert report[0]["reviewed_by"] == "ops@example.com" and report[0]["payment_reference"] == "BANKTRANSFER123456"
    assert all(m["status"] == "sent" for m in report[0]["notifications"])
    mails = registry.get_email().sent
    assert any("Action required" in m["subject"] and m["to"] == "ops@example.com" for m in mails)
    assert any("credits added" in m["subject"].lower() and m["to"] == "owner@acme.test" for m in mails)


async def test_receipt_repeat_and_two_admin_approvals_do_not_duplicate(client, workspace, maker, review_mode):
    id = await checkout(client)
    payment = await submit(client, id)
    before = len(registry.get_email().sent)
    r = await client.post(
        f"/v1/billing/transfer/{id}/submit", headers=OWNER, json={"proof_id": payment["receipt"]["id"]}
    )
    assert r.status_code == 200 and len(registry.get_email().sent) == before
    results = await asyncio.gather(
        *[client.post(f"/v1/admin/bank-transfers/{id}/approve", headers=OPS, json=approval(payment)) for _ in range(2)]
    )
    assert all(r.status_code == 200 for r in results), [r.text for r in results]
    assert {r.json()["result"] for r in results} == {"granted", "duplicate"}
    assert await balance(maker, workspace) == Decimal("13.70")


async def test_receipt_or_bank_reference_cannot_pay_two_purchases(client, workspace, maker, review_mode):
    first = await checkout(client)
    payment = await submit(client, first)
    assert (
        await client.post(f"/v1/admin/bank-transfers/{first}/approve", headers=OPS, json=approval(payment))
    ).status_code == 200
    second = await checkout(client)
    payment2 = await submit(client, second, PNG + b"different-receipt")
    assert (
        await client.post(
            f"/v1/admin/bank-transfers/{second}/approve",
            headers=OPS,
            json=approval(payment2, "bank / transfer - 123456"),
        )
    ).status_code == 409
    third = await checkout(client)
    payment3 = await submit(client, third)
    assert (
        await client.post(
            f"/v1/admin/bank-transfers/{third}/approve", headers=OPS, json=approval(payment3, "NEWBANKREFERENCE999")
        )
    ).status_code == 409
    assert await balance(maker, workspace) == Decimal("13.70")


async def test_reject_and_corrected_receipt_resubmission_stale_approval_protected(
    client, workspace, maker, review_mode
):
    id = await checkout(client)
    old = await submit(client, id)
    rejection = {
        "reason": "Receipt is incomplete. Please upload the full transaction receipt.",
        "proof_id": old["receipt"]["id"],
        "revision": old["revision"],
    }
    assert (await client.post(f"/v1/admin/bank-transfers/{id}/reject", headers=OPS, json=rejection)).status_code == 200
    assert await balance(maker, workspace) == 10
    assert (
        await client.post(f"/v1/billing/transfer/{id}/submit", headers=OWNER, json={"proof_id": old["receipt"]["id"]})
    ).status_code == 422
    corrected = await submit(client, id, PNG + b"corrected")
    assert corrected["revision"] == 2
    assert (
        await client.post(f"/v1/admin/bank-transfers/{id}/approve", headers=OPS, json=approval(old))
    ).status_code == 409
    assert (
        await client.post(f"/v1/admin/bank-transfers/{id}/approve", headers=OPS, json=approval(corrected))
    ).status_code == 200
    assert await balance(maker, workspace) == Decimal("13.70")


@pytest.mark.parametrize(
    ("content", "kind"),
    [(b"fake png", "image/png"), (PNG + EICAR, "image/png"), (b"%PDF-1.7 /JavaScript /JS (bad)", "application/pdf")],
)
async def test_unsafe_receipts_cannot_be_submitted(client, workspace, maker, review_mode, content, kind):
    id = await checkout(client)
    result = await upload(client, id, content, kind)
    assert (
        await client.post(
            f"/v1/billing/transfer/{id}/uploads/confirm", headers=OWNER, json={"proof_id": result["proof_id"]}
        )
    ).status_code == 422
    assert (
        await client.post(f"/v1/billing/transfer/{id}/submit", headers=OWNER, json={"proof_id": result["proof_id"]})
    ).status_code == 422
    assert await balance(maker, workspace) == 10


async def test_reviewed_receipt_is_immutable_and_customer_cannot_access_another_workspace(
    client, workspace, maker, review_mode
):
    id = await checkout(client)
    up = await upload(client, id)
    assert (
        await client.post(
            f"/v1/billing/transfer/{id}/uploads/confirm", headers=OWNER, json={"proof_id": up["proof_id"]}
        )
    ).status_code == 200
    await client.put(api_path(up["upload_url"]), content=b"altered after scan")
    async with maker() as db:
        proof = await db.get(PaymentProof, up["proof_id"])
        assert "/verified." in proof.key
        assert await registry.get_storage().get(proof.key, 10000) == PNG
        other = Workspace(name="Other payer")
        db.add(other)
        await db.flush()
        db.add(User(email="other-payer@example.com", workspace_id=other.id))
        await db.commit()
    other = {"Authorization": "Bearer dev:other-payer@example.com"}
    assert (await client.get(f"/v1/billing/transfer/{id}", headers=other)).status_code == 404
    assert (
        await client.post(f"/v1/billing/transfer/{id}/submit", headers=other, json={"proof_id": up["proof_id"]})
    ).status_code == 404
    assert (await client.get("/v1/admin/bank-transfers", headers=OWNER)).status_code == 403


async def test_active_approvers_not_suspended_staff_receive_alerts_and_failed_mail_retries(
    client, workspace, maker, review_mode, monkeypatch
):
    async with maker() as db:
        for email, status, perms in [
            ("admin@example.com", "active", list(rbac.ALL)),
            ("finance@example.com", "active", ["finance.view", "finance.manage"]),
            ("revoked@example.com", "suspended", list(rbac.ALL)),
            ("support@example.com", "active", ["overview.view"]),
        ]:
            db.add(
                StaffMember(
                    email=email,
                    role="custom",
                    permissions=perms,
                    status=status,
                    workspace_id=workspace,
                    invited_by="ops@example.com",
                )
            )
        await db.commit()
    original = svc.send_email

    async def failure(*args, **kwargs):
        return False

    monkeypatch.setattr(svc, "send_email", failure)
    id = await checkout(client)
    payment = await submit(client, id)
    assert payment["status"] == "pending_review"
    async with maker() as db:
        mails = (await db.execute(select(TransferMail))).scalars().all()
        assert {m.recipient for m in mails if m.kind == "admin_action"} == {
            "ops@example.com",
            "admin@example.com",
            "finance@example.com",
        }
        assert all(m.status == "pending" for m in mails)
    monkeypatch.setattr(svc, "send_email", original)
    assert await svc.deliver_notifications(id) == 4
    assert await svc.deliver_notifications(id) == 0


async def test_account_changes_do_not_change_existing_purchase_and_privacy_removes_files(
    client, workspace, maker, review_mode
):
    id = await checkout(client)
    payment = await submit(client, id)
    assert (
        await client.put(
            "/v1/admin/bank-transfer-accounts/USD",
            headers=OWNER,
            json={"bank_name": "Bad bank", "account_number": "bad123"},
        )
    ).status_code == 403
    assert (
        await client.put(
            "/v1/admin/bank-transfer-accounts/USD",
            headers=OPS,
            json={"bank_name": "New bank", "account_number": "9999888877"},
        )
    ).status_code == 200
    old = (await client.get(f"/v1/billing/transfer/{id}", headers=OWNER)).json()
    assert old["bank"]["account_number"] == "1111222233"
    async with maker() as db:
        ws = await db.get(Workspace, workspace)
        owner = (await db.execute(select(User).where(User.email == "owner@acme.test"))).scalar_one()
        exported = await export_workspace(db, ws, owner)
        assert exported["bank_transfer_reviews"][0]["receipt"]["filename"] == "receipt.png"
        proof = await db.get(PaymentProof, payment["receipt"]["id"])
        key = proof.key
        await delete_workspace(db, ws)
        await db.commit()
        assert not await registry.get_storage().exists(key)
        assert (await db.get(TransferReview, id)).submitted_by is None
        assert not (await db.execute(select(TransferMail))).scalars().all()


@pytest.mark.parametrize("currency", ["USD", "NGN"])
async def test_verified_nuvion_bank_details_are_used_without_inventing_beneficiary(maker, monkeypatch, currency):
    class Bank:
        account_id = "verified-account"
        entity_id = "verified-entity"

        async def call(self, method, path, params):
            assert (method, path, params) == ("GET", "/accounts/verified-account", {"entity_id": "verified-entity"})
            return {
                "account": {
                    "id": self.account_id,
                    "entity_id": self.entity_id,
                    "currency": currency,
                    "display_name": "Account label",
                },
                "account_details": [
                    {
                        "account_id": self.account_id,
                        "entity_id": self.entity_id,
                        "currency": currency,
                        "status": "active",
                        "config": {"inflow_enabled": True},
                        "account_number": "1234567890",
                        "issuer": {
                            "name": "Verified bank",
                            "meta": {
                                "routing_number": "021000021",
                                "bank_address": "Verified bank address",
                                **({"receiver_name": "Verified beneficiary"} if currency == "USD" else {}),
                            },
                        },
                    }
                ],
            }

    monkeypatch.setattr(svc.payments, "provider", lambda **kwargs: Bank())
    async with maker() as db:
        bank = await svc.receiving_account(db, currency)
    assert bank["account_number"] == "1234567890"
    assert bank["routing_number"] == "021000021"
    assert bank["beneficiary_name"] == ("Verified beneficiary" if currency == "USD" else "")
    assert bank["account_label"] == "Account label"


def test_payment_recipient_adds_company_once_without_changing_bank_identity():
    bank = {"beneficiary_name": "Verified beneficiary", "account_number": "1234567890"}
    assert svc.recipient_display(bank) == "Verified beneficiary / Sydney Money Technology Inc"
    assert bank == {"beneficiary_name": "Verified beneficiary", "account_number": "1234567890"}
    assert (
        svc.recipient_display({"beneficiary_name": "Verified beneficiary / Sydney Money Technology Inc"})
        == "Verified beneficiary / Sydney Money Technology Inc"
    )
