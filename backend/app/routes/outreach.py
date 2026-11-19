"""Back office: outreach templates and settings, contacts import, and the conversation inbox with outlets."""

import re
from typing import Literal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from pydantic import BaseModel, EmailStr, Field, TypeAdapter, ValidationError
from sqlalchemy import func, or_, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import Principal, require
from app.db import get_session
from app.models import DistributionPlacement, DistributionRequest, OutreachMessage, OutreachOptout, OutreachThread
from app.models.base import utcnow
from app.routes.distribution import OUTLETS
from app.routes.distribution_operations import save_setting
from app.services import distribution as dist
from app.services import distribution_catalog as catalog_service
from app.services import outreach, outreach_agent, outreach_gmail
from app.services.audit import audit
from app.services.ratelimit import limit

router = APIRouter(tags=["outreach"])


# ---------- settings and templates ----------
@router.get("/v1/admin/outreach/config")
async def get_config(
    p: Principal = Depends(require("operations.view")), db: AsyncSession = Depends(get_session)
) -> dict:
    from app.config import get_settings

    cfg = await outreach.get_config(db)
    return {
        "config": cfg.model_dump(mode="json"),
        "variables": outreach.VARIABLE_NAMES,
        "steps": [
            {"id": k, "label": v["label"], "never_auto": v["never_auto"], "default": v["default"]}
            for k, v in outreach_agent.STEPS.items()
        ],
        "engine_on": outreach.enabled(),
        "mailbox": await outreach_gmail.status(db),
        "needs_contact": (
            await db.execute(select(func.count()).select_from(DistributionPlacement).where(DistributionPlacement.outreach_state == "needs_contact"))
        ).scalar_one(),
        "reply_domain": get_settings().outreach_reply_domain,
        "sending": {
            "via_mailbox": bool(get_settings().outreach_smtp_host),
            "mailbox": get_settings().outreach_mailbox or get_settings().outreach_smtp_user,
            "reads_replies": bool(get_settings().outreach_imap_host),
            "reply_address_example": outreach.reply_address("0123456789abcdef0123", await outreach_gmail.address(db)),
        },
    }


@router.put("/v1/admin/outreach/config")
async def put_config(
    body: outreach.OutreachConfig,
    p: Principal = Depends(require("operations.manage")),
    db: AsyncSession = Depends(get_session),
) -> dict:
    for step, value in body.policy.items():
        if step not in outreach_agent.STEPS or value not in {"auto", "approve"}:
            raise HTTPException(422, f"Unknown step or setting: {step}")
    await outreach.save_config(db, p.user.email, body)
    return {"config": body.model_dump(mode="json")}


class PreviewIn(BaseModel):
    template_id: str | None = None
    subject: str | None = Field(default=None, max_length=250)
    body: str | None = Field(default=None, max_length=12000)
    outlet_id: str | None = None


@router.post("/v1/admin/outreach/preview")
async def preview(
    body: PreviewIn,
    p: Principal = Depends(require("operations.view")),
    db: AsyncSession = Depends(get_session),
) -> dict:
    """What a template looks like with sample details (nothing is sent)."""
    cfg = await outreach.get_config(db)
    outlet = OUTLETS.get(body.outlet_id or "") or next(iter(OUTLETS.values()))
    contact = ""
    for o in await catalog_service.catalog(db, admin=True):
        if o["id"] == outlet["id"]:
            contact = o.get("contact_name") or ""
    values = {
        "contact_name": contact or "Ada",
        "outlet_name": outlet["name"],
        "headline": "Acme opens its first store in Lagos",
        "summary": "Acme has opened its first store in Lagos, serving customers across the city.",
        "announcement": "Acme has opened its first store in Lagos, serving customers across the city.\n\nThe store opens daily from 9am.",
        "story": "Acme opens its first store in Lagos\n\nAcme has opened its first store in Lagos, serving customers across the city.\n\nThe store opens daily from 9am.",
        "assets": "Video: https://example.com/video\nCompany logo: https://example.com/logo.png",
        "reference": "CF-DIST-SAMPLE",
        "payment_summary": "Our client has paid Cover Founder to arrange this distribution request.",
        "sender_name": cfg.sender_name,
        "sender_title": cfg.sender_title,
        "customer_name": "Tunde Bello",
        "company_name": "Acme Foods",
    }
    if body.subject is not None and body.body is not None:
        try:
            outreach.check_placeholders(body.subject)
            outreach.check_placeholders(body.body)
            subject = body.subject.format_map(values)
            text = body.body.format_map(values).rstrip() + "\n\n--\n" + outreach.footer(cfg)
        except (ValueError, KeyError) as e:
            raise HTTPException(422, str(e)) from e
        return {"template_id": None, "subject": subject, "body": text}
    tid, subject, text = outreach.render_template(cfg, body.template_id, values)
    return {"template_id": tid, "subject": subject, "body": text}


# ---------- contacts ----------
class ContactsIn(BaseModel):
    text: str = Field(max_length=200000)
    enable_automatic: bool = True  # also switch on automatic outreach for the outlets that get a contact


def _outlet_lookup() -> dict[str, dict]:
    keys: dict[str, dict] = {}
    for o in OUTLETS.values():
        keys[o["id"]] = o
        keys[o["name"].strip().lower()] = o
    return keys


def _check_contacts(text: str, current: dict[str, dict]) -> list[dict]:
    try:
        raw = outreach.split_header(text)
    except ValueError as e:
        raise HTTPException(
            422, "Could not read that list. Paste a CSV (outlet, contact_name, contact_email) or JSON."
        ) from e
    keys = _outlet_lookup()
    out = []
    for n, r in enumerate(raw, 1):
        name = str(r.get("outlet") or r.get("outlet_name") or r.get("name") or "").strip()
        emails = [x for x in re.split(r"[;,\s]+", str(r.get("contact_email") or r.get("email") or "").lower()) if x]
        email = emails[0] if emails else ""
        others = emails[1:]
        who = str(r.get("contact_name") or r.get("contact") or "").strip()
        template = str(r.get("template") or "").strip() or None
        outlet = keys.get(name.lower()) or keys.get(name)
        row = {
            "row": n,
            "outlet": name,
            "outlet_id": outlet["id"] if outlet else None,
            "outlet_name": outlet["name"] if outlet else None,
            "contact_name": who,
            "contact_email": email,
            "cc_emails": others,
            "template": template,
            "status": "ok",
        }
        if outlet is None:
            row["status"] = "unknown_outlet"
        else:
            bad = len(others) > 5  # a main contact and up to five more
            if not bad:
                try:
                    for addr in emails or [""]:
                        TypeAdapter(EmailStr).validate_python(addr)
                except ValidationError:
                    bad = True
            if bad:
                row["status"] = "bad_email"
            else:
                cur = current.get(outlet["id"], {})
                same_cc = sorted(str(x).lower() for x in cur.get("cc_emails") or []) == sorted(others)
                if cur.get("contact_email") == email and (cur.get("contact_name") or "") == who and same_cc:
                    row["status"] = "unchanged"
        out.append(row)
    return out


@router.post("/v1/admin/outreach/contacts/preview")
async def contacts_preview(
    body: ContactsIn, p: Principal = Depends(require("operations.view")), db: AsyncSession = Depends(get_session)
) -> dict:
    current = {o["id"]: o for o in await catalog_service.catalog(db, admin=True)}
    rows = _check_contacts(body.text, current)
    return {"rows": rows, "will_change": sum(1 for r in rows if r["status"] == "ok")}


@router.post("/v1/admin/outreach/contacts/apply")
async def contacts_apply(
    body: ContactsIn,
    request: Request,
    p: Principal = Depends(require("operations.manage")),
    db: AsyncSession = Depends(get_session),
) -> dict:
    current = {o["id"]: o for o in await catalog_service.catalog(db, admin=True)}
    rows = [r for r in _check_contacts(body.text, current) if r["status"] == "ok"]
    cfg = await outreach.get_config(db)
    templates = {t.id for t in cfg.templates}
    for r in rows:
        if r["template"] and r["template"] not in templates:
            raise HTTPException(
                422, f"Row {r['row']}: unknown template '{r['template']}'. Use one of: {', '.join(sorted(templates))}"
            )

    def change(old: dict) -> dict:
        outlets = dict(old.get("outlets", {}))
        for r in rows:
            base = {**outlets.get(r["outlet_id"], {})}
            base["contact_name"], base["contact_email"], base["cc_emails"] = r["contact_name"], r["contact_email"], r["cc_emails"]
            if r["template"]:
                base["outreach_template"] = r["template"]
            if body.enable_automatic:
                base["direct_access"] = True
            outlets[r["outlet_id"]] = _full_outlet(base, r["outlet_id"], current)
        return {**old, "outlets": outlets}

    if rows:
        await save_setting(db, p, change)
        audit(
            db,
            p.user.email,
            "outreach.contacts_imported",
            target_type="setting",
            target_id=catalog_service.KEY,
            detail={"count": len(rows)},
            request=request,
        )
        await db.commit()
        await outreach.catch_up()  # paid requests that were waiting for these contacts are written to now
    return {"applied": len(rows)}


def _full_outlet(base: dict, outlet_id: str, current: dict[str, dict]) -> dict:
    """A saved outlet entry must be a complete, valid OutletConfig (prices and policies as they are now)."""
    live = current[outlet_id]
    keep = (
        "credits",
        "accepts_logo",
        "accepts_images",
        "logo_credits",
        "picture_credits",
        "direct_access",
        "contact_name",
        "contact_email",
        "cc_emails",
        "skip_outreach",
        "email_subject",
        "email_body",
        "outreach_template",
    )
    merged = {k: live.get(k) for k in keep if live.get(k) is not None}
    merged.update({k: v for k, v in base.items() if k in keep})
    return catalog_service.OutletConfig.model_validate(merged).model_dump(mode="json")


# ---------- conversations ----------
def _snippet(text: str, n: int = 140) -> str:
    one = " ".join(text.split())
    return one[:n] + ("…" if len(one) > n else "")


def _thread_row(t: OutreachThread, last: OutreachMessage | None) -> dict:
    return {
        "id": t.id,
        "request_id": t.request_id,
        "placement_id": t.placement_id,
        "outlet_id": t.outlet_id,
        "outlet_name": t.outlet_name,
        "contact_name": t.contact_name,
        "contact_email": t.contact_email,
        "status": t.status,
        "ai_paused": t.ai_paused,
        "last_inbound_at": outreach.when(t.last_inbound_at),
        "last_outbound_at": outreach.when(t.last_outbound_at),
        "updated_at": outreach.when(t.updated_at),
        "last": {"direction": last.direction, "status": last.status, "snippet": _snippet(last.body)} if last else None,
    }


@router.get("/v1/admin/outreach/threads")
async def list_threads(
    status: str | None = None,
    q: str | None = None,
    limit: int = 100,
    p: Principal = Depends(require("operations.view")),
    db: AsyncSession = Depends(get_session),
) -> dict:
    query = select(OutreachThread)
    if status:
        query = query.where(OutreachThread.status == status)
    if q and q.strip():
        like = f"%{q.strip().lower()}%"
        query = query.where(
            or_(
                func.lower(OutreachThread.outlet_name).like(like),
                func.lower(OutreachThread.contact_email).like(like),
                func.lower(OutreachThread.request_id).like(like),
            )
        )
    threads = (
        (await db.execute(query.order_by(OutreachThread.updated_at.desc()).limit(min(max(limit, 1), 300))))
        .scalars()
        .all()
    )
    counts = {
        s: n
        for s, n in (
            await db.execute(select(OutreachThread.status, func.count()).group_by(OutreachThread.status))
        ).all()
    }
    rows = []
    for t in threads:
        last = (
            await db.execute(
                select(OutreachMessage)
                .where(OutreachMessage.thread_id == t.id, OutreachMessage.status != "discarded")
                .order_by(OutreachMessage.created_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
        rows.append(_thread_row(t, last))
    return {"threads": rows, "counts": counts}


SAFE_AI = (
    "step",
    "intent",
    "confidence",
    "reasons",
    "summary",
    "suspicious",
    "has_account_details",
    "automatic",
    "sender_mismatch",
    "opt_out",
    "error",
    "approved_by",
    "edited",
)


def _message_out(m: OutreachMessage) -> dict:
    return {
        "id": m.id,
        "direction": m.direction,
        "kind": m.kind,
        "status": m.status,
        "subject": m.subject,
        "body": m.body,
        "sender": m.sender,
        "actor": m.actor,
        "ai": {k: v for k, v in (m.ai or {}).items() if k in SAFE_AI},
        "created_at": outreach.when(m.created_at),
        "sent_at": outreach.when(m.sent_at),
    }


async def _thread(db: AsyncSession, id: str) -> OutreachThread:
    t = await db.get(OutreachThread, id)
    if t is None:
        raise HTTPException(404, "Conversation not found")
    return t


@router.get("/v1/admin/outreach/threads/{id}")
async def get_thread(
    id: str, p: Principal = Depends(require("operations.view")), db: AsyncSession = Depends(get_session)
) -> dict:
    t = await _thread(db, id)
    msgs = (
        (
            await db.execute(
                select(OutreachMessage)
                .where(OutreachMessage.thread_id == id, OutreachMessage.status != "discarded")
                .order_by(OutreachMessage.created_at)
            )
        )
        .scalars()
        .all()
    )
    req = await db.get(DistributionRequest, t.request_id)
    placement = await db.get(DistributionPlacement, t.placement_id)
    return {
        "thread": _thread_row(t, msgs[-1] if msgs else None),
        "messages": [_message_out(m) for m in msgs],
        "facts": outreach.public_facts(t.facts),
        "request": {"id": req.id, "headline": req.data.get("headline", ""), "status": req.status} if req else None,
        "placement": {"id": placement.id, "internal_status": placement.internal_status, "status": placement.status}
        if placement
        else None,
    }


class ReplyIn(BaseModel):
    body: str = Field(min_length=1, max_length=20000)
    subject: str | None = Field(default=None, max_length=250)
    send_now: bool = False  # skip the wait before a reply goes out


@router.post("/v1/admin/outreach/threads/{id}/reply")
async def reply(
    id: str,
    body: ReplyIn,
    tasks: BackgroundTasks,
    p: Principal = Depends(require("operations.manage")),
    db: AsyncSession = Depends(get_session),
) -> dict:
    t = await _thread(db, id)
    try:
        msg = await outreach.send_reply(db, t, body.body, p.user.email, subject=body.subject, send_now=body.send_now)
    except outreach.CannotSend as e:
        raise HTTPException(409, str(e)) from e
    audit(db, p.user.email, "outreach.reply", target_type="outreach_thread", target_id=id)
    await db.commit()
    tasks.add_task(dist.deliver_request, t.request_id)
    return _message_out(msg)


class StatusIn(BaseModel):
    status: Literal["awaiting_reply", "replied", "agreed", "closed", "do_not_contact"] | None = None
    ai_paused: bool | None = None


@router.post("/v1/admin/outreach/threads/{id}/status")
async def set_status(
    id: str,
    body: StatusIn,
    p: Principal = Depends(require("operations.manage")),
    db: AsyncSession = Depends(get_session),
) -> dict:
    t = await _thread(db, id)
    if body.status:
        t.status = body.status
        if body.status == "do_not_contact":
            if await db.get(OutreachOptout, t.contact_email) is None:
                db.add(OutreachOptout(email=t.contact_email, reason="marked by " + p.user.email))
    if body.ai_paused is not None:
        t.ai_paused = body.ai_paused
    t.updated_at = utcnow()
    audit(
        db,
        p.user.email,
        "outreach.status",
        target_type="outreach_thread",
        target_id=id,
        detail={"status": body.status, "ai_paused": body.ai_paused},
    )
    await db.commit()
    return _thread_row(t, None)


# ---------- the agent's drafts ----------
class ApproveIn(BaseModel):
    body: str | None = Field(default=None, max_length=20000)
    send_now: bool = False


async def _message(db: AsyncSession, thread_id: str, mid: str) -> OutreachMessage:
    m = await db.get(OutreachMessage, mid)
    if m is None or m.thread_id != thread_id:
        raise HTTPException(404, "Message not found")
    return m


@router.post("/v1/admin/outreach/threads/{id}/messages/{mid}/approve")
async def approve(
    id: str,
    mid: str,
    body: ApproveIn,
    tasks: BackgroundTasks,
    p: Principal = Depends(require("operations.manage")),
    db: AsyncSession = Depends(get_session),
) -> dict:
    t = await _thread(db, id)
    draft = await _message(db, id, mid)
    try:
        msg = await outreach_agent.approve_draft(db, t, draft, p.user.email, body.body, body.send_now)
    except outreach.CannotSend as e:
        raise HTTPException(409, str(e)) from e
    audit(
        db,
        p.user.email,
        "outreach.draft_approved",
        target_type="outreach_thread",
        target_id=id,
        detail={"step": draft.ai.get("step")},
    )
    await db.commit()
    tasks.add_task(dist.deliver_request, t.request_id)
    return _message_out(msg)


@router.post("/v1/admin/outreach/threads/{id}/messages/{mid}/discard")
async def discard(
    id: str, mid: str, p: Principal = Depends(require("operations.manage")), db: AsyncSession = Depends(get_session)
) -> dict:
    t = await _thread(db, id)
    draft = await _message(db, id, mid)
    if draft.kind != "ai_draft" or draft.status != "pending_approval":
        raise HTTPException(409, "That draft is no longer waiting for approval.")
    draft.status = "discarded"
    pending = (
        await db.execute(
            select(OutreachMessage.id)
            .where(
                OutreachMessage.thread_id == id, OutreachMessage.status == "pending_approval", OutreachMessage.id != mid
            )
            .limit(1)
        )
    ).first()
    if not pending and t.status == "needs_approval":
        t.status = "replied"
    audit(db, p.user.email, "outreach.draft_discarded", target_type="outreach_thread", target_id=id)
    await db.commit()
    return {"ok": True}


@router.post("/v1/admin/outreach/threads/{id}/ai-draft")
async def ask_for_draft(
    id: str, p: Principal = Depends(require("operations.manage")), db: AsyncSession = Depends(get_session)
) -> dict:
    """Ask the agent to read the newest reply again and draft an answer (it ignores a pause, since a person asked)."""
    t = await _thread(db, id)
    last = (
        await db.execute(
            select(OutreachMessage)
            .where(
                OutreachMessage.thread_id == id,
                OutreachMessage.direction == "in",
                OutreachMessage.status.in_(["received"]),
            )
            .order_by(OutreachMessage.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()
    if last is None:
        raise HTTPException(409, "There is no reply to answer yet.")
    last.ai = {**last.ai, "processed": False}
    await db.commit()
    outreach_agent.schedule(t.id, last.id, force=True)
    return {"ok": True}


# ---------- account details ----------
@router.get("/v1/admin/outreach/threads/{id}/account-details")
async def reveal_account(
    id: str, p: Principal = Depends(require("operations.manage")), db: AsyncSession = Depends(get_session)
) -> dict:
    """The account details an outlet sent, in full. Each reveal is recorded. Verify them with the outlet another way before paying."""
    import json

    from app.services import crypto

    t = await _thread(db, id)
    enc = (t.facts or {}).get("account_details_enc")
    if not enc:
        raise HTTPException(404, "No account details were sent")
    originals = []
    for m in (
        await db.execute(
            select(OutreachMessage).where(OutreachMessage.thread_id == id, OutreachMessage.direction == "in")
        )
    ).scalars():
        if (m.ai or {}).get("original_enc"):
            originals.append({"id": m.id, "text": crypto.decrypt(m.ai["original_enc"])})
    audit(db, p.user.email, "outreach.account_details_viewed", target_type="outreach_thread", target_id=id)
    await db.commit()
    return {
        "details": json.loads(crypto.decrypt(enc)),
        "messages": originals,
        "verified": bool((t.facts or {}).get("account_verified_by")),
    }


@router.post("/v1/admin/outreach/threads/{id}/account-details/verify")
async def verify_account(
    id: str, p: Principal = Depends(require("operations.manage")), db: AsyncSession = Depends(get_session)
) -> dict:
    t = await _thread(db, id)
    if not (t.facts or {}).get("account_details_enc"):
        raise HTTPException(404, "No account details were sent")
    t.facts = {**t.facts, "account_verified_by": p.user.email, "account_verified_at": utcnow().isoformat()}
    audit(db, p.user.email, "outreach.account_details_verified", target_type="outreach_thread", target_id=id)
    await db.commit()
    return {"ok": True}


class TestSendIn(BaseModel):
    to: EmailStr


@router.post("/v1/admin/outreach/test-send")
async def test_send(
    body: TestSendIn, p: Principal = Depends(require("operations.manage")), db: AsyncSession = Depends(get_session)
) -> dict:
    """Send a sample outreach email (the default template, sample details) to an address of yours, exactly the way real ones go out."""
    from app.services.notifications import send_email

    cfg = await outreach.get_config(db)
    box = await outreach_gmail.address(db)
    if not await outreach_gmail.ready(db):
        raise HTTPException(409, "Connect a Gmail address first (Mailbox, above), so there is somewhere to send from.")
    _, subject, text = outreach.render_template(
        cfg,
        None,
        {
            "contact_name": "there",
            "outlet_name": "your publication",
            "headline": "Acme opens its first store in Lagos",
            "summary": "Acme has opened its first store in Lagos.",
            "announcement": "Acme has opened its first store in Lagos.",
            "assets": "(story materials would be listed here)",
            "reference": "CF-DIST-TEST",
            "payment_summary": "This is a test.",
            "sender_name": cfg.sender_name,
            "sender_title": cfg.sender_title,
            "customer_name": "Tunde Bello",
            "company_name": "Acme Foods",
        },
    )
    ok = await send_email(
        body.to,
        "[Test] " + subject,
        text,
        plain=True,
        reply_to=outreach.reply_address("0123456789abcdef0123", box),
        provider=await outreach_gmail.provider(db),
    )
    audit(db, p.user.email, "outreach.test_send", target_type="setting", target_id=outreach.KEY, detail={"ok": ok})
    await db.commit()
    if not ok:
        raise HTTPException(502, "The mail server did not accept the message. Check the sender settings.")
    return {"sent": True}


# ---------- outlets still waiting for a contact ----------
class ContactIn(BaseModel):
    contact_name: str = Field(default="", max_length=200)
    emails: list[EmailStr] = Field(min_length=1, max_length=6)  # the first is the main contact; the others are copied on every email


@router.get("/v1/admin/outreach/needs-contact")
async def needs_contact(
    p: Principal = Depends(require("operations.view")), db: AsyncSession = Depends(get_session)
) -> dict:
    """Paid requests where an outlet has no contact email yet (nobody has been written to), and those waiting only for a mailbox."""
    rows = (
        await db.execute(
            select(DistributionPlacement, DistributionRequest)
            .join(DistributionRequest, DistributionRequest.id == DistributionPlacement.request_id)
            .where(DistributionPlacement.outreach_state.in_(("needs_contact", "waiting_mailbox")))
            .order_by(DistributionRequest.paid_at, DistributionPlacement.created_at)
            .limit(300)
        )
    ).all()
    items = [
        {
            "placement_id": pl.id,
            "request_id": req.id,
            "outlet_id": pl.outlet_id,
            "outlet_name": pl.data.get("name", ""),
            "headline": (req.data or {}).get("headline", ""),
            "requester": req.created_by,
            "paid_at": outreach.when(req.paid_at),
            "state": pl.outreach_state,
        }
        for pl, req in rows
    ]
    return {
        "needs_contact": [i for i in items if i["state"] == "needs_contact"],
        "waiting_mailbox": sum(1 for i in items if i["state"] == "waiting_mailbox"),
    }


@router.put("/v1/admin/outreach/needs-contact/{placement_id}")
async def add_contact(
    placement_id: str,
    body: ContactIn,
    request: Request,
    p: Principal = Depends(require("operations.manage")),
    db: AsyncSession = Depends(get_session),
) -> dict:
    """Give an outlet its contact (one email or several). It is saved on the outlet, so every later request uses it too, and the
    conversation for this paid request starts straight away."""
    pl = await db.get(DistributionPlacement, placement_id)
    if pl is None or pl.outreach_state not in {"needs_contact", "waiting_mailbox"}:
        raise HTTPException(404, "That outlet is not waiting for a contact.")
    current = {o["id"]: o for o in await catalog_service.catalog(db, admin=True)}
    if pl.outlet_id not in current:
        raise HTTPException(404, "Unknown outlet.")
    emails = [str(e).lower() for e in body.emails]
    main, others = emails[0], [e for e in dict.fromkeys(emails[1:]) if e != emails[0]]

    def change(old: dict) -> dict:
        outlets = dict(old.get("outlets", {}))
        base = {**outlets.get(pl.outlet_id, {}), "contact_name": body.contact_name.strip(), "contact_email": main, "cc_emails": others}
        outlets[pl.outlet_id] = _full_outlet(base, pl.outlet_id, current)
        return {**old, "outlets": outlets}

    await save_setting(db, p, change)
    audit(
        db,
        p.user.email,
        "outreach.contact_added",
        target_type="placement",
        target_id=placement_id,
        detail={"outlet_id": pl.outlet_id, "emails": len(emails)},
        request=request,
    )
    await db.commit()
    started = await outreach.catch_up(limit=300)
    await db.refresh(pl)
    return {"state": pl.outreach_state, "started": started}


# ---------- the Gmail mailbox ----------
class MailboxIn(BaseModel):
    address: str = Field(min_length=3, max_length=320)
    app_password: str = Field(min_length=1, max_length=200)


def _bad_mailbox(e: Exception) -> HTTPException:
    if isinstance(e, outreach_gmail.ConnectFailed):
        return HTTPException(422, {"message": e.result["message"], "steps": e.result["steps"], "smtp": e.result["smtp"], "imap": e.result["imap"]})
    return HTTPException(422, {"message": str(e), "steps": []})


@router.get("/v1/admin/outreach/mailbox")
async def mailbox_status(p: Principal = Depends(require("operations.view")), db: AsyncSession = Depends(get_session)) -> dict:
    """Which mailbox outreach uses, how it sends, and how the last look at the inbox went. Never includes the password."""
    return await outreach_gmail.status(db)


@router.post("/v1/admin/outreach/mailbox/test", dependencies=[Depends(limit("outreach-mailbox", 10, 60))])
async def mailbox_test(body: MailboxIn, p: Principal = Depends(require("operations.manage"))) -> dict:
    """Try an address and app password without saving anything."""
    try:
        addr = outreach_gmail.valid_address(body.address)
    except ValueError as e:
        raise _bad_mailbox(e) from e
    return await outreach_gmail.test_connection(addr, outreach_gmail.clean_password(body.app_password))


@router.put("/v1/admin/outreach/mailbox", dependencies=[Depends(limit("outreach-mailbox", 10, 60))])
async def mailbox_connect(
    body: MailboxIn, p: Principal = Depends(require("operations.manage")), db: AsyncSession = Depends(get_session)
) -> dict:
    """Connect the Gmail address (tested first, then saved encrypted). Conversations that were waiting for a mailbox start."""
    try:
        await outreach_gmail.connect(db, p.user.email, body.address, body.app_password)
    except (outreach_gmail.ConnectFailed, ValueError) as e:
        raise _bad_mailbox(e) from e
    await outreach.catch_up(limit=300)
    return await outreach_gmail.status(db)


@router.delete("/v1/admin/outreach/mailbox")
async def mailbox_disconnect(p: Principal = Depends(require("operations.manage")), db: AsyncSession = Depends(get_session)) -> dict:
    await outreach_gmail.disconnect(db, p.user.email)
    return await outreach_gmail.status(db)
