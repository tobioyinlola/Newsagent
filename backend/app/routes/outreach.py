"""Back office: outreach templates and settings, contacts import, and the conversation inbox with outlets."""

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
from app.services import outreach
from app.services.audit import audit

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
        "engine_on": outreach.enabled(),
        "reply_domain": get_settings().outreach_reply_domain,
    }


@router.put("/v1/admin/outreach/config")
async def put_config(
    body: outreach.OutreachConfig,
    p: Principal = Depends(require("operations.manage")),
    db: AsyncSession = Depends(get_session),
) -> dict:
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
        email = str(r.get("contact_email") or r.get("email") or "").strip().lower()
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
            "template": template,
            "status": "ok",
        }
        if outlet is None:
            row["status"] = "unknown_outlet"
        else:
            try:
                TypeAdapter(EmailStr).validate_python(email)
            except ValidationError:
                row["status"] = "bad_email"
            else:
                cur = current.get(outlet["id"], {})
                if cur.get("contact_email") == email and (cur.get("contact_name") or "") == who:
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
            base["contact_name"], base["contact_email"] = r["contact_name"], r["contact_email"]
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
        "ai": m.ai,
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
                select(OutreachMessage).where(OutreachMessage.thread_id == id).order_by(OutreachMessage.created_at)
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
        msg = await outreach.send_reply(db, t, body.body, p.user.email, subject=body.subject)
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
