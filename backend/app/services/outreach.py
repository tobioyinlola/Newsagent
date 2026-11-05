"""AI outreach to distribution outlets: templates, a conversation per placement, and replies that find their way back.

OUTREACH_AI=off (the default) leaves the original one-way outreach email exactly as it was. With OUTREACH_AI=on, an outlet that has a
contact and automatic outreach gets a conversation: the chosen template goes out from a tagged reply address, and what the outlet
answers is kept as a thread the team (and later the agent) can answer.
"""

import logging
import random
import re
import secrets
from datetime import datetime, timedelta
from string import Formatter

from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import (
    DistributionMail,
    DistributionPlacement,
    DistributionRequest,
    OutreachMessage,
    OutreachOptout,
    OutreachThread,
    SystemSetting,
    Workspace,
)
from app.models.base import new_id, utcnow
from app.services import distribution as dist
from app.services.audit import audit
from app.services.distribution_catalog import VARIABLES

log = logging.getLogger("outreach")

KEY = "outreach"
VARIABLE_NAMES = sorted(VARIABLES | {"sender_name", "sender_title", "customer_name", "company_name"})
FOOTER_OPT_OUT = "If you would rather not hear from us, reply STOP and we will not contact you again."

INTRO = """Hello {contact_name},

I'm {sender_name}, {sender_title} at Cover Founder. Our client {company_name} has an announcement we would like to publish on {outlet_name}, and we would like to pay for the placement.

Headline: {headline}
Summary: {summary}

Could you please let us know:
1. Whether you can publish it as a sponsored article.
2. Your rate, and what it includes.
3. Your usual turnaround time.

The full announcement and materials:
{assets}

Thank you,
{sender_name}
Cover Founder
Reference: {reference}"""

RATES = """Hello {contact_name},

This is {sender_name} from Cover Founder. We'd like to place a sponsored article for {company_name} on {outlet_name}: "{headline}".

What is your rate for a sponsored article, and how soon could it go live? If you need anything from us (images, a logo, a quote), tell us and we will send it today.

Kind regards,
{sender_name}, {sender_title}
Cover Founder
Reference: {reference}"""

FORMAL = """Dear {contact_name},

Cover Founder is a news and distribution platform. {payment_summary} We would like to arrange a paid publication on {outlet_name} for our client {company_name}.

Headline: {headline}

Announcement:
{announcement}

Publication materials:
{assets}

Please confirm whether you can accept this placement, the applicable fee, your publication timeline and the payment arrangements, so that we can proceed.

Yours sincerely,
{sender_name}
{sender_title}, Cover Founder
Reference: {reference}"""

DEFAULT_TEMPLATES = [
    {"id": "intro", "name": "Friendly introduction", "subject": "Publication enquiry: {headline}", "body": INTRO},
    {
        "id": "rates",
        "name": "Short rates enquiry",
        "subject": "Rates for a sponsored article on {outlet_name}?",
        "body": RATES,
    },
    {"id": "formal", "name": "Formal request", "subject": "Sponsored publication request: {headline}", "body": FORMAL},
]


def check_placeholders(value: str) -> str:
    try:
        for _, name, spec, conversion in Formatter().parse(value):
            if name is not None and (name not in VARIABLE_NAMES or spec or conversion):
                raise ValueError(
                    f"Unknown or unsupported placeholder: {{{name}}}. Use only: " + ", ".join(VARIABLE_NAMES)
                )
    except ValueError as e:
        raise ValueError(str(e)) from e
    return value


class Template(BaseModel):
    id: str = Field(min_length=1, max_length=40, pattern=r"^[a-z0-9_-]+$")
    name: str = Field(min_length=1, max_length=80)
    subject: str = Field(min_length=1, max_length=250)
    body: str = Field(min_length=1, max_length=12000)

    @field_validator("subject", "body")
    @classmethod
    def placeholders(cls, v):
        return check_placeholders(v)

    @field_validator("subject")
    @classmethod
    def one_line(cls, v):
        if "\n" in v or "\r" in v:
            raise ValueError("Subject must be a single line.")
        return v


class OutreachConfig(BaseModel):
    templates: list[Template] = Field(
        default_factory=lambda: [Template(**t) for t in DEFAULT_TEMPLATES], min_length=1, max_length=3
    )
    default_template: str = "intro"
    sender_name: str = Field(default="The Cover Founder team", max_length=120)
    sender_title: str = Field(default="Partnerships", max_length=120)
    footer_address: str = Field(default="", max_length=300)  # the company's postal address, shown under every email
    mode: str = Field(
        default="draft", pattern=r"^(draft|policy)$"
    )  # how much the agent may do on its own (used by the agent)
    daily_cap: int = Field(default=200, ge=0, le=5000)  # automatic (agent) replies a day
    reply_delay_minutes: int = Field(
        default_factory=lambda: get_settings().outreach_reply_delay_minutes, ge=0, le=1440
    )  # a reply goes out no sooner than this after the outlet wrote
    new_gap_minutes: int = Field(
        default_factory=lambda: get_settings().outreach_new_gap_minutes, ge=0, le=240
    )  # first emails are spread at least this far apart
    new_daily_cap: int = Field(
        default_factory=lambda: get_settings().outreach_new_daily_cap, ge=1, le=2000
    )  # first emails a day
    send_cap_per_day: int = Field(
        default=150, ge=1, le=5000
    )  # every outreach email a day (a mailbox that sends too much gets blocked)
    ai_turn_limit: int = Field(default=6, ge=1, le=30)
    paused: bool = False
    policy: dict[str, str] = Field(
        default_factory=dict
    )  # step type -> auto | approve (filled in by the agent's defaults)

    @field_validator("default_template")
    @classmethod
    def known(cls, v, info):
        ids = [t.id for t in info.data.get("templates", [])]
        if ids and v not in ids:
            raise ValueError("The default template must be one of the templates.")
        return v


def enabled() -> bool:
    return get_settings().outreach_ai == "on"


async def get_config(db: AsyncSession) -> OutreachConfig:
    row = await db.get(SystemSetting, KEY)
    return OutreachConfig.model_validate(row.value if row and row.value else {})


async def save_config(db: AsyncSession, actor: str, cfg: OutreachConfig) -> None:
    row = await db.get(SystemSetting, KEY)
    value = cfg.model_dump(mode="json")
    if row is None:
        db.add(SystemSetting(key=KEY, value=value, updated_by=actor))
    else:
        row.value, row.updated_by, row.updated_at = value, actor, utcnow()
    audit(db, actor, "outreach.configuration_changed", target_type="setting", target_id=KEY)
    await db.commit()


def reply_address(token: str) -> str | None:
    """Where this conversation's replies should come back to. With a mailbox set (Gmail or Workspace), plus-addressing on it
    (name+<code>@domain); otherwise outreach+<code>@<the reply domain>."""
    s = get_settings()
    box = s.outreach_mailbox.strip()
    if "@" in box:
        local, domain = box.rsplit("@", 1)
        return f"{local.split('+')[0]}+{token}@{domain}"
    domain = s.outreach_reply_domain.strip()
    return f"outreach+{token}@{domain}" if domain else None


def new_message_id() -> str:
    s = get_settings()
    domain = (
        s.outreach_reply_domain.strip()
        or (s.outreach_mailbox.rsplit("@", 1)[-1] if "@" in s.outreach_mailbox else "")
        or "outreach.local"
    )
    return f"<{secrets.token_hex(12)}@{domain}>"


def footer(cfg: OutreachConfig) -> str:
    lines = [FOOTER_OPT_OUT]
    if cfg.footer_address.strip():
        lines.append(cfg.footer_address.strip())
    return "\n".join(lines)


async def is_opted_out(db: AsyncSession, email: str) -> bool:
    return (await db.get(OutreachOptout, email.strip().lower())) is not None


async def build_values(
    db: AsyncSession, row: DistributionRequest, placement: DistributionPlacement, outlet_cfg: dict, cfg: OutreachConfig
) -> dict:
    ws = await db.get(Workspace, row.workspace_id)
    return {
        "contact_name": outlet_cfg.get("contact_name") or "Editorial team",
        "outlet_name": placement.data["name"],
        "headline": row.data["headline"],
        "summary": row.data["announcement"][:1000],
        "announcement": row.data["announcement"],
        "assets": await dist.materials(db, row, placement.data),
        "reference": "CF-DIST-" + row.id.upper(),
        "payment_summary": (
            "Our client has paid Cover Founder to arrange this distribution request."
            if row.total_credits
            else "Our client has confirmed a distribution request with Cover Founder."
        ),
        "sender_name": cfg.sender_name,
        "sender_title": cfg.sender_title,
        "customer_name": row.data.get("contact_name", ""),
        "company_name": ws.name if ws else "our client",
    }


def render_template(cfg: OutreachConfig, template_id: str | None, values: dict) -> tuple[str, str, str]:
    """(template id used, subject, body with the footer). An unknown id falls back to the default template."""
    by_id = {t.id: t for t in cfg.templates}
    t = by_id.get(template_id or "") or by_id.get(cfg.default_template) or cfg.templates[0]
    subject = t.subject.format_map(values).replace("\n", " ").replace("\r", " ")[:300]
    body = t.body.format_map(values).rstrip() + "\n\n--\n" + footer(cfg)
    return t.id, subject, body


def _aware_dt(t: datetime) -> datetime:
    return t if t.tzinfo else t.replace(tzinfo=utcnow().tzinfo)


def _jitter(minutes: float) -> timedelta:
    """A wait with some give in it, so the emails do not go out on a clock."""
    return timedelta(minutes=minutes * random.uniform(1.0, 1.4))  # noqa: S311 (timing variety, not security)


def reply_not_before(thread: OutreachThread, cfg: "OutreachConfig") -> datetime | None:
    """A reply waits until some minutes after the outlet wrote (nobody answers in seconds). None = no need to wait."""
    if cfg.reply_delay_minutes <= 0 or thread.last_inbound_at is None:
        return None
    due = _aware_dt(thread.last_inbound_at) + _jitter(cfg.reply_delay_minutes)
    return due if due > utcnow() else None


async def next_first_slot(db: AsyncSession, cfg: "OutreachConfig") -> datetime | None:
    """When the next FIRST email to an outlet may go: spread out (not a burst), and no more than a day's cap. None = now."""
    now = utcnow()
    when = func.coalesce(DistributionMail.send_after, DistributionMail.created_at)
    first = (DistributionMail.thread_id.is_not(None)) & (DistributionMail.in_reply_to.is_(None))
    last = (await db.execute(select(func.max(when)).where(first))).scalar_one_or_none()
    slot = now
    if last is not None and cfg.new_gap_minutes > 0:
        slot = max(now, _aware_dt(last) + _jitter(cfg.new_gap_minutes))
    for _ in range(14):  # find a day with room
        day = slot.replace(hour=0, minute=0, second=0, microsecond=0)
        used = (
            await db.execute(
                select(func.count())
                .select_from(DistributionMail)
                .where(first, when >= day, when < day + timedelta(days=1))
            )
        ).scalar_one()
        if used < cfg.new_daily_cap:
            break
        slot = day + timedelta(days=1, hours=8)  # tomorrow morning
    return slot if slot > now + timedelta(seconds=5) else None


async def send_room(db: AsyncSession) -> int:
    """How many more conversation emails may go today."""
    cfg = await get_config(db)
    day = utcnow().replace(hour=0, minute=0, second=0, microsecond=0)
    sent = (
        await db.execute(
            select(func.count())
            .select_from(DistributionMail)
            .where(
                DistributionMail.thread_id.is_not(None),
                DistributionMail.status == "sent",
                DistributionMail.sent_at >= day,
            )
        )
    ).scalar_one()
    return max(0, cfg.send_cap_per_day - int(sent))


async def deliver_due() -> int:
    """Send the held conversation emails whose time has come (run every minute). Returns how many requests were looked at."""
    if not enabled():
        return 0
    from app.db import session_maker

    async with session_maker()() as db:
        ids = (
            (
                await db.execute(
                    select(DistributionMail.request_id)
                    .where(
                        DistributionMail.thread_id.is_not(None),
                        DistributionMail.status.in_(["pending", "failed"]),
                        DistributionMail.attempts < 8,
                        DistributionMail.send_after.is_not(None),
                        DistributionMail.send_after <= utcnow(),
                    )
                    .distinct()
                )
            )
            .scalars()
            .all()
        )
    for rid in ids:
        await dist.deliver_request(rid)
    return len(ids)


async def start_thread(
    db: AsyncSession, row: DistributionRequest, placement: DistributionPlacement, outlet_cfg: dict
) -> OutreachThread | None:
    """Open the conversation for a placement and queue the first email. Returns None when the outlet cannot be contacted."""
    email = (placement.contact_email or "").strip().lower()
    if not email:
        return None
    if await is_opted_out(db, email):
        dist.activity(db, row, "outreach_skipped", {"reason": "opted_out", "recipient": email}, placement=placement)
        return None
    existing = (
        await db.execute(select(OutreachThread).where(OutreachThread.placement_id == placement.id))
    ).scalar_one_or_none()
    if existing:
        return existing
    cfg = await get_config(db)
    values = await build_values(db, row, placement, outlet_cfg, cfg)
    template_id, subject, body = render_template(cfg, outlet_cfg.get("outreach_template"), values)
    token = secrets.token_hex(10)
    thread = OutreachThread(
        request_id=row.id,
        placement_id=placement.id,
        outlet_id=placement.outlet_id,
        outlet_name=placement.data.get("name", ""),
        contact_name=outlet_cfg.get("contact_name") or "",
        contact_email=email,
        template_id=template_id,
        reply_token=token,
        status="awaiting_reply",
        facts={},
        last_outbound_at=utcnow(),
    )
    db.add(thread)
    await db.flush()
    placement.outreach_subject, placement.outreach_body = subject, body
    await _queue(
        db,
        row,
        thread,
        placement,
        subject,
        body,
        kind="template",
        actor="system",
        key=placement.id + ":initial",
        send_after=await next_first_slot(db, cfg),  # spread out: not a burst, and within a day's limit
    )
    dist.activity(db, row, "outreach_started", {"thread_id": thread.id, "template": template_id}, placement=placement)
    return thread


async def _queue(
    db,
    row,
    thread: OutreachThread,
    placement,
    subject: str,
    body: str,
    *,
    kind: str,
    actor: str,
    key: str,
    in_reply_to: str | None = None,
    ai: dict | None = None,
    send_after: datetime | None = None,
) -> OutreachMessage:
    message_id = new_message_id()
    mail = await dist.queue_mail(
        db,
        row,
        "outreach",
        thread.contact_email,
        subject,
        body,
        key=key,
        placement=placement,
        thread_id=thread.id,
        reply_to=reply_address(thread.reply_token),
        message_id=message_id,
        in_reply_to=in_reply_to,
        send_after=send_after,
    )
    msg = OutreachMessage(
        thread_id=thread.id,
        direction="out",
        kind=kind,
        status="queued",
        subject=subject.replace("\n", " ")[:300],
        body=body,
        message_id=message_id,
        in_reply_to=in_reply_to,
        mail_id=mail.id if mail else None,
        sender=get_settings().email_from,
        ai=ai or {},
        actor=actor,
    )
    db.add(msg)
    await db.flush()
    return msg


async def last_message_id(db: AsyncSession, thread_id: str) -> str | None:
    return (
        await db.execute(
            select(OutreachMessage.message_id)
            .where(
                OutreachMessage.thread_id == thread_id,
                OutreachMessage.message_id.is_not(None),
                OutreachMessage.status.in_(["sent", "received", "queued"]),
            )
            .order_by(OutreachMessage.created_at.desc())
            .limit(1)
        )
    ).scalar_one_or_none()


class CannotSend(Exception):
    pass


async def send_reply(
    db: AsyncSession,
    thread: OutreachThread,
    text: str,
    actor: str,
    *,
    subject: str | None = None,
    kind: str = "human",
    ai: dict | None = None,
    send_now: bool = False,
) -> OutreachMessage:
    """Queue a reply in the conversation. Used for a person's own reply and for approved or automatic agent replies."""
    if thread.status == "do_not_contact" or await is_opted_out(db, thread.contact_email):
        raise CannotSend("This contact asked us to stop. They will not be emailed again.")
    if not text.strip():
        raise CannotSend("Write a message first.")
    row = await db.get(DistributionRequest, thread.request_id)
    placement = await db.get(DistributionPlacement, thread.placement_id)
    if row is None or placement is None:
        raise CannotSend("This request no longer exists.")
    cfg = await get_config(db)
    prior = (
        await db.execute(
            select(OutreachMessage.subject)
            .where(OutreachMessage.thread_id == thread.id)
            .order_by(OutreachMessage.created_at)
            .limit(1)
        )
    ).scalar_one_or_none() or "Your publication"
    subj = subject or (prior if prior.lower().startswith("re:") else "Re: " + prior)
    body = text.rstrip() + "\n\n--\n" + footer(cfg)
    in_reply_to = await last_message_id(db, thread.id)
    msg = await _queue(
        db,
        row,
        thread,
        placement,
        subj,
        body,
        kind=kind,
        actor=actor,
        key=f"{thread.id}:reply:{new_id()}",
        in_reply_to=in_reply_to,
        ai=ai,
        send_after=None if send_now else reply_not_before(thread, cfg),
    )
    thread.last_outbound_at = utcnow()
    thread.updated_at = utcnow()
    if thread.status in {"replied", "needs_approval"}:
        thread.status = "awaiting_reply"
    dist.activity(
        db, row, "outreach_reply_queued", {"thread_id": thread.id, "kind": kind}, actor=actor, placement=placement
    )
    return msg


async def mark_delivery(db: AsyncSession, mail: DistributionMail, success: bool) -> None:
    """Called by the mail outbox after it tries to send a conversation email."""
    if not mail.thread_id:
        return
    await db.execute(
        update(OutreachMessage)
        .where(OutreachMessage.mail_id == mail.id)
        .values(status="sent" if success else "failed", sent_at=utcnow() if success else None)
    )


def split_header(text: str) -> list[dict]:
    """CSV or JSON rows from pasted text: outlet, contact_name, contact_email, template (optional)."""
    import csv
    import io
    import json

    text = text.strip()
    if not text:
        return []
    if text[0] in "[{":
        data = json.loads(text)
        return data if isinstance(data, list) else [data]
    sample = text.splitlines()[0]
    delimiter = "\t" if "\t" in sample else ";" if sample.count(";") > sample.count(",") else ","
    reader = csv.reader(io.StringIO(text), delimiter=delimiter)
    rows = [r for r in reader if any(c.strip() for c in r)]
    if not rows:
        return []
    head = [c.strip().lower().replace(" ", "_") for c in rows[0]]
    if "outlet" in head or "outlet_name" in head or "name" in head:
        return [dict(zip(head, [c.strip() for c in r], strict=False)) for r in rows[1:]]
    cols = ["outlet", "contact_name", "contact_email", "template"]
    return [dict(zip(cols, [c.strip() for c in r], strict=False)) for r in rows]


EMAIL_RE = re.compile(r"^[^@\s]+@[^@\s]+\.[^@\s]+$")


def when(value: datetime | None) -> str | None:
    return value.isoformat() if value else None


def public_facts(facts: dict) -> dict:
    """What the admin may see by default: everything except stored account details, which are shown only masked (see the agent step)."""
    shown = {k: v for k, v in (facts or {}).items() if k != "account_details_enc"}
    shown["has_account_details"] = bool((facts or {}).get("account_details_enc"))
    shown["account_verified"] = bool((facts or {}).get("account_verified_by"))
    return shown
