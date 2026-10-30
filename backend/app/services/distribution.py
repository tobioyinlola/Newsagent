"""Paid distribution fulfilment and a durable, independently retryable email outbox."""

import hashlib
import logging
import time
from datetime import UTC, timedelta
from html import escape

from sqlalchemy import or_, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import session_maker
from app.integrations import registry
from app.models import Asset, DistributionActivity, DistributionMail, DistributionPlacement, DistributionRequest
from app.models.base import new_id, utcnow
from app.services import email_templates
from app.services.distribution_catalog import BODY, SUBJECT, settings
from app.services.notifications import send_email


def activity(db, row, kind, detail=None, *, actor="system", placement=None):
    db.add(
        DistributionActivity(
            request_id=row.id,
            placement_id=placement.id if placement else None,
            actor=actor,
            kind=kind,
            detail=detail or {},
        )
    )


def invoice(row) -> dict | None:
    if not row.paid_at:
        return None
    return {
        "number": "CF-DIST-" + row.id.upper(),
        "issued_at": row.paid_at.isoformat(),
        "payment_method": "Credit wallet",
        "status": "paid" if row.total_credits else "no_charge",
        "total_credits": str(row.total_credits),
        "reference": f"distribution:{row.id}",
        "items": row.data.get("outlets", []),
    }


def breakdown(row):
    lines = []
    for o in row.data.get("outlets", []):
        lines.append(
            f"{o['name']}: {o['credits']} credits (placement {o.get('base_credits', o['credits'])}; logo {o.get('logo_fee', '0')}; pictures {o.get('picture_fee', '0')})"
        )
    return "\n".join(lines)


def customer_recipients(row):
    return sorted({x.strip().lower() for x in [row.created_by, row.data["contact_email"]]})


async def queue_mail(db, row, kind, recipient, subject, body, *, key, placement=None):
    recipient = recipient.strip().lower()
    dedupe = f"{row.id}:{kind}:" + hashlib.sha256((key + ":" + recipient).encode()).hexdigest()
    existing = (
        await db.execute(select(DistributionMail.id).where(DistributionMail.dedupe_key == dedupe))
    ).scalar_one_or_none()
    if existing:
        return
    db.add(
        DistributionMail(
            request_id=row.id,
            placement_id=placement.id if placement else None,
            dedupe_key=dedupe,
            kind=kind,
            recipient=recipient,
            subject=subject.replace("\n", " ").replace("\r", " ")[:300],
            body=body,
        )
    )
    activity(db, row, "email_queued", {"kind": kind, "recipient": recipient}, placement=placement)
    await db.flush()


async def queue_receipts(db, row):
    if row.email_sent_at:
        return
    inv = invoice(row)
    body = (
        f"Your distribution request has been submitted successfully. Someone from the Cover Founder team will reach out to you within the next 24 hours.\n\n"
        f"Receipt / credit invoice: {inv['number']}\nHeadline: {row.data['headline']}\n\n{breakdown(row)}\n\n"
        f"Total: {row.total_credits} credits\nPayment method: Credit wallet\n"
        f"Payment status: {'Paid — credits deducted' if row.total_credits else 'Confirmed — no credit charge'}\n"
        f"Reference: {inv['reference']}\n\nView your per-outlet progress and download your receipt: {get_settings().app_base_url}/distribution/request?draft={row.id}"
    )
    for recipient in customer_recipients(row):
        await queue_mail(db, row, "receipt", recipient, "Your distribution request is confirmed", body, key="receipt")


async def materials(db, row, line: dict) -> str:
    # The caller supplies the request's full internal materials or the outlet's restricted snapshot.
    storage = registry.get_storage()
    lines = []
    video = (
        (await db.execute(select(Asset).where(Asset.project_id == row.data["project_id"], Asset.type == "render")))
        .scalars()
        .first()
    )
    if video:
        lines.append("Video: " + storage.presign_get(video.storage_key, 604800))
    if line.get("logo_key"):
        lines.append("Company logo: " + storage.presign_get(line["logo_key"], 604800))
    for i, key in enumerate(line.get("picture_keys", []), 1):
        lines.append(f"Picture {i}: " + storage.presign_get(key, 604800))
    return "\n".join(lines) + (
        "\nDownload links expire after 7 days; reply if you need refreshed links."
        if lines
        else "No downloadable materials supplied."
    )


async def outreach_copy(db, row, placement, config):
    values = {
        "contact_name": config.get("contact_name") or "Editorial team",
        "outlet_name": placement.data["name"],
        "headline": row.data["headline"],
        "summary": row.data["announcement"][:1000],
        "announcement": row.data["announcement"],
        "assets": await materials(db, row, placement.data),
        "reference": "CF-DIST-" + row.id.upper(),
        "payment_summary": (
            "Our client has paid Cover Founder to arrange this distribution request."
            if row.total_credits
            else "Our client has confirmed a distribution request with Cover Founder."
        ),
    }
    return (
        config.get("email_subject", SUBJECT).format_map(values).replace("\n", " ").replace("\r", " ")[:300],
        config.get("email_body", BODY).format_map(values),
    )


async def plan_submission(db, row, catalog):
    await queue_receipts(db, row)
    config = await settings(db)
    team = (config.value if config else {}).get("team_emails", [])
    downloads = await materials(db, row, row.data) if team else ""
    for recipient in team:
        data = row.data
        body = (
            f"A distribution request has been confirmed.\nPayment: {'Paid from credit wallet' if row.total_credits else 'No-charge request'}\n"
            f"Total: {row.total_credits} credits\nReceipt: {invoice(row)['number']}\nRequester: {row.created_by}\n"
            f"Contact: {data['contact_name']} <{data['contact_email']}>\nPhone: {data['phone']}\nWhatsApp: {data['whatsapp']}\n"
            f"Video project: {data['project_id']}\n\nSelected outlets and charges:\n{breakdown(row)}\n\n"
            f"Headline: {data['headline']}\n\nAnnouncement:\n{data['announcement']}\n\n"
            f"Company logo uploaded: {'Yes' if data.get('logo_key') else 'No'}\nAdditional pictures: {len(data.get('picture_keys', []))}\n"
            f"\nSubmitted materials (download links expire in 7 days):\n{downloads}\n\n"
            f"Review the request and download all submitted assets securely: {get_settings().admin_base_url}/distribution"
        )
        await queue_mail(
            db,
            row,
            "team_sale",
            recipient,
            "Paid distribution submitted" if row.total_credits else "No-charge distribution submitted",
            body,
            key="sale",
        )
    by_id = {o["id"]: o for o in catalog}
    for line in row.data["outlets"]:
        config = by_id[line["id"]]
        placement = DistributionPlacement(
            request_id=row.id, outlet_id=line["id"], data=line, contact_email=config.get("contact_email") or ""
        )
        db.add(placement)
        await db.flush()
        placement.outreach_subject, placement.outreach_body = await outreach_copy(db, row, placement, config)
        if config.get("direct_access") and placement.contact_email:
            await queue_mail(
                db,
                row,
                "outreach",
                placement.contact_email,
                placement.outreach_subject,
                placement.outreach_body,
                key=placement.id + ":initial",
                placement=placement,
            )
    activity(
        db,
        row,
        "submitted",
        {"credits": str(row.total_credits), "outlets": len(row.data["outlets"])},
        actor=row.created_by,
    )


async def queue_publication(db, row, placement):
    key = placement.id + ":" + hashlib.sha256(placement.published_url.encode()).hexdigest()[:24]
    count = len(row.data["outlets"])
    progress = (
        f"This request covers {count} media outlets. Each outlet is tracked separately; we'll notify you as more placements go live.\n"
        if count > 1
        else "Your selected outlet's publication link and receipt are available on your dashboard.\n"
    )
    for recipient in customer_recipients(row):
        await queue_mail(
            db,
            row,
            "published",
            recipient,
            f"Your announcement is live on {placement.data['name']}",
            f"Your announcement, {row.data['headline']}, is now published on {placement.data['name']}.\n\n"
            f"Read the published post: {placement.published_url}\n\n"
            f"{progress}"
            f"View all publication links and progress: {get_settings().app_base_url}/distribution/request?draft={row.id}",
            key=key,
            placement=placement,
        )


def utc(value):
    return value.replace(tzinfo=UTC) if value.tzinfo is None else value


async def send_confirmation(db: AsyncSession, row: DistributionRequest, *, deadline: float | None = None) -> bool:
    """Drain the request's outbox; safe across concurrent workers. No provider exception can undo payment."""
    if not row.paid_at:
        return False
    await db.execute(
        update(DistributionRequest)
        .where(DistributionRequest.id == row.id)
        .values(updated_at=DistributionRequest.updated_at)
    )
    await queue_receipts(db, row)
    await db.commit()
    cutoff = utcnow() - timedelta(minutes=10)
    ids = (
        (
            await db.execute(
                select(DistributionMail.id)
                .where(
                    DistributionMail.request_id == row.id,
                    or_(
                        DistributionMail.status.in_(["pending", "failed", "retry_requested"]),
                        (DistributionMail.status == "sending") & (DistributionMail.claimed_at < cutoff),
                    ),
                    or_(DistributionMail.attempts < 8, DistributionMail.status == "retry_requested"),
                )
                .order_by(DistributionMail.created_at)
            )
        )
        .scalars()
        .all()
    )
    await db.commit()
    for ident in ids:
        if deadline is not None and time.monotonic() >= deadline:
            break
        token = new_id()
        claimed = (
            await db.execute(
                update(DistributionMail)
                .where(
                    DistributionMail.id == ident,
                    or_(
                        DistributionMail.status.in_(["pending", "failed", "retry_requested"]),
                        (DistributionMail.status == "sending") & (DistributionMail.claimed_at < cutoff),
                    ),
                    or_(DistributionMail.attempts < 8, DistributionMail.status == "retry_requested"),
                )
                .values(
                    status="sending", claim_token=token, claimed_at=utcnow(), attempts=DistributionMail.attempts + 1
                )
                .returning(DistributionMail.id)
            )
        ).scalar_one_or_none()
        await db.commit()
        if not claimed:
            continue
        mail = await db.get(DistributionMail, ident, populate_existing=True)
        await db.commit()  # No transaction stays open while the provider is called.
        try:
            if mail.kind in {"outreach", "team_sale"}:
                footer = (
                    "Cover Founder is contacting your publication about a sponsorship enquiry. Please reply directly to this email."
                    if mail.kind == "outreach"
                    else "You are a configured recipient of Cover Founder distribution notifications."
                )
                html, text = email_templates.render(mail.subject, mail.body, footer=footer)
                success = await send_email(mail.recipient, mail.subject, text, html=html)
            else:
                success = await send_email(mail.recipient, mail.subject, mail.body)
        except Exception:  # An adapter or test double must not bypass persisted retry handling.
            success = False
        changed = (
            await db.execute(
                update(DistributionMail)
                .where(DistributionMail.id == ident, DistributionMail.claim_token == token)
                .values(
                    status="sent" if success else "failed",
                    sent_at=utcnow() if success else None,
                    error="" if success else "Email provider did not accept delivery.",
                    claim_token=None,
                    updated_at=utcnow(),
                )
                .returning(DistributionMail.id)
            )
        ).scalar_one_or_none()
        if changed:
            activity(
                db,
                row,
                "email_sent" if success else "email_failed",
                {"mail_id": ident, "kind": mail.kind, "recipient": mail.recipient},
            )
        await db.commit()
    receipts = (
        (
            await db.execute(
                select(DistributionMail)
                .where(DistributionMail.request_id == row.id, DistributionMail.kind == "receipt")
                .execution_options(populate_existing=True)
            )
        )
        .scalars()
        .all()
    )
    await db.commit()
    if receipts and all(m.status == "sent" for m in receipts):
        await db.execute(
            update(DistributionRequest)
            .where(DistributionRequest.id == row.id, DistributionRequest.email_sent_at.is_(None))
            .values(email_sent_at=utcnow())
        )
        await db.commit()
    await db.refresh(row)
    return row.email_sent_at is not None


async def deliver_request(id):
    try:
        async with session_maker()() as db:
            row = await db.get(DistributionRequest, id)
            if row:
                await send_confirmation(db, row, deadline=time.monotonic() + 30)
    except Exception as error:
        logging.getLogger("distribution").warning(
            "Distribution email processing deferred for request %s (%s)", id, type(error).__name__
        )


async def retry_confirmations() -> int:
    count = 0
    deadline = time.monotonic() + 30
    async with session_maker()() as db:
        cutoff = utcnow() - timedelta(minutes=10)
        pending_ids = select(DistributionMail.request_id).where(
            or_(
                DistributionMail.status.in_(["pending", "failed", "retry_requested"]),
                (DistributionMail.status == "sending") & (DistributionMail.claimed_at < cutoff),
            ),
            or_(DistributionMail.attempts < 8, DistributionMail.status == "retry_requested"),
        )
        receipt_ids = select(DistributionMail.request_id).where(DistributionMail.kind == "receipt")
        rows = (
            (
                await db.execute(
                    select(DistributionRequest)
                    .where(
                        DistributionRequest.paid_at.is_not(None),
                        or_(
                            (DistributionRequest.email_sent_at.is_(None) & ~DistributionRequest.id.in_(receipt_ids)),
                            DistributionRequest.id.in_(pending_ids),
                        ),
                    )
                    .limit(100)
                )
            )
            .scalars()
            .all()
        )
        for row in rows:
            if time.monotonic() >= deadline:
                break
            before = row.email_sent_at
            if await send_confirmation(db, row, deadline=deadline) and before is None:
                count += 1
    return count


async def details(db, row, *, admin=False):
    placements = (
        (
            await db.execute(
                select(DistributionPlacement)
                .where(DistributionPlacement.request_id == row.id)
                .order_by(DistributionPlacement.created_at, DistributionPlacement.outlet_id)
            )
        )
        .scalars()
        .all()
    )
    result = {"invoice": invoice(row), "placements": [placement_output(p, admin=admin) for p in placements]}
    if admin:
        mails = (
            (
                await db.execute(
                    select(DistributionMail)
                    .where(DistributionMail.request_id == row.id)
                    .order_by(DistributionMail.created_at.desc())
                )
            )
            .scalars()
            .all()
        )
        events = (
            (
                await db.execute(
                    select(DistributionActivity)
                    .where(DistributionActivity.request_id == row.id)
                    .order_by(DistributionActivity.created_at.desc())
                    .limit(200)
                )
            )
            .scalars()
            .all()
        )
        result["emails"] = [
            {
                "id": m.id,
                "placement_id": m.placement_id,
                "kind": m.kind,
                "recipient": m.recipient,
                "subject": m.subject,
                "body": m.body,
                "status": m.status,
                "attempts": m.attempts,
                "sent_at": m.sent_at,
                "created_at": m.created_at,
                "error": m.error,
            }
            for m in mails
        ]
        result["activity"] = [
            {
                "id": e.id,
                "placement_id": e.placement_id,
                "actor": e.actor,
                "kind": e.kind,
                "detail": e.detail,
                "created_at": e.created_at,
            }
            for e in events
        ]
    return result


def placement_output(p, *, admin=False):
    value = {
        "id": p.id,
        "outlet_id": p.outlet_id,
        "name": p.data["name"],
        "status": p.status,
        "published_url": p.published_url if p.status == "published" or admin else "",
        "published_at": p.published_at,
        "credits": p.data["credits"],
    }
    if admin:
        value.update(
            internal_status=p.internal_status,
            internal_notes=p.internal_notes,
            contact_email=p.contact_email,
            outreach_subject=p.outreach_subject,
            outreach_body=p.outreach_body,
        )
    return value


def receipt_html(row):
    inv = invoice(row)
    rows = "".join(
        f"<tr><td>{escape(i['name'])}</td><td>{escape(i.get('base_credits', i['credits']))}</td><td>{escape(i.get('logo_fee', '0'))}</td><td>{escape(i.get('picture_fee', '0'))}</td><td>{escape(i['credits'])}</td></tr>"
        for i in inv["items"]
    )
    return (
        f'<!doctype html><html lang="en"><meta charset="utf-8"><title>{inv["number"]}</title>'
        "<style>body{font:16px sans-serif;max-width:900px;margin:40px auto;padding:20px;color:#222}table{width:100%;border-collapse:collapse}td,th{padding:12px;border-bottom:1px solid #ccc;text-align:left}</style>"
        f"<h1>Cover Founder — distribution receipt</h1><p>Receipt / credit invoice: {inv['number']}</p>"
        f"<p>Issued: {inv['issued_at']}</p><p>Customer: {escape(row.data['contact_name'])} · {escape(row.data['contact_email'])}</p>"
        f"<h2>{escape(row.data['headline'])}</h2><table><thead><tr><th>Outlet</th><th>Placement credits</th><th>Logo credits</th><th>Picture credits</th><th>Total credits</th></tr></thead><tbody>{rows}</tbody></table>"
        f"<h2>Total: {row.total_credits} credits</h2><p>Credit wallet · {'Paid' if row.total_credits else 'Confirmed with no credit charge'}</p>"
        f"<p>Payment reference: {inv['reference']}</p><p>This receipt records a credit-wallet purchase. It is not a separate USD or NGN card charge.</p></html>"
    )
