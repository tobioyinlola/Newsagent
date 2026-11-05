"""Replies from outlets: match them to their conversation, clean them up, keep them once, and honour a request to stop."""

import logging
import re
from dataclasses import dataclass, field
from email import message_from_bytes
from email.message import EmailMessage
from email.policy import default as default_policy
from email.utils import parseaddr

from sqlalchemy import select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import DistributionPlacement, DistributionRequest, OutreachMessage, OutreachOptout, OutreachThread
from app.models.base import utcnow
from app.services import distribution as dist

log = logging.getLogger("outreach")

TOKEN_RE = re.compile(r"outreach\+([a-z0-9]{8,40})@", re.I)
WROTE_RE = re.compile(r"^on\s.{5,300}$", re.I)
QUOTE_MARKERS = (
    re.compile(r"^-{2,}\s*(original message|forwarded message)\s*-{2,}\s*$", re.I),
    re.compile(r"^_{5,}\s*$"),
    re.compile(r"^from:\s.+<.+>\s*$", re.I),
    re.compile(r"^sent from my\s", re.I),
    re.compile(r"^get outlook for\s", re.I),
)
AUTO_SUBJECT = re.compile(
    r"^(automatic reply|auto[- ]?reply|out of office|undeliverable|delivery status notification|mail delivery (failed|subsystem)|returned mail)",
    re.I,
)
STOP_START = re.compile(r"^\s*(stop|unsubscribe)\b", re.I | re.M)
STOP_ANY = re.compile(
    r"\b(unsubscribe|do not (contact|email) (us|me)|don'?t (contact|email) (us|me)|remove (us|me) from)\b", re.I
)
MAX_BODY = 20000


@dataclass
class InboundMail:
    to: list[str]
    sender: str
    subject: str = ""
    text: str = ""
    message_id: str | None = None
    in_reply_to: str | None = None
    references: str = ""
    headers: dict[str, str] = field(default_factory=dict)


def clean_reply(text: str) -> str:
    """The part the person actually wrote: no quoted history, no mail-client footers."""
    lines = text.replace("\r\n", "\n").replace("\r", "\n").split("\n")
    kept: list[str] = []
    for i, line in enumerate(lines):
        s = line.strip()
        if s.startswith(">"):
            if any(k.strip() for k in kept):
                break
            continue
        if any(m.match(s) for m in QUOTE_MARKERS) and any(k.strip() for k in kept):
            break
        # "On Tue, 4 Nov 2026 at 09:10, Ada <a@b.c> wrote:" (the mail client may wrap it onto two lines)
        joined = (s + " " + (lines[i + 1].strip() if i + 1 < len(lines) else "")).strip()
        if (
            WROTE_RE.match(s)
            and (s.lower().endswith("wrote:") or joined.lower().endswith("wrote:"))
            and any(k.strip() for k in kept)
        ):
            break
        if s == "--" and any(k.strip() for k in kept):
            break
        kept.append(line)
    return "\n".join(kept).strip()[:MAX_BODY]


def is_automatic(m: InboundMail) -> bool:
    h = {k.lower(): v.lower() for k, v in m.headers.items()}
    if h.get("auto-submitted", "no") not in {"no", ""} or "x-autoreply" in h or "x-autorespond" in h:
        return True
    if h.get("precedence", "") in {"bulk", "auto_reply", "junk"}:
        return True
    name, addr = parseaddr(m.sender)
    local = addr.split("@")[0].lower()
    return bool(
        AUTO_SUBJECT.match(m.subject.strip()) or local in {"mailer-daemon", "postmaster", "no-reply", "noreply"}
    )


def wants_stop(clean: str) -> bool:
    words = clean.split()
    return bool(words) and len(words) <= 80 and bool(STOP_START.search(clean) or STOP_ANY.search(clean))


def sender_address(raw: str) -> str:
    return parseaddr(raw)[1].strip().lower()


def domain_of(addr: str) -> str:
    return addr.rsplit("@", 1)[-1].lower() if "@" in addr else ""


async def match_thread(db: AsyncSession, m: InboundMail) -> OutreachThread | None:
    """By the tagged address first (it cannot be confused), then by the message it answers, then by who wrote and what about."""
    for to in m.to:
        t = TOKEN_RE.search(to or "")
        if t:
            thread = (
                await db.execute(select(OutreachThread).where(OutreachThread.reply_token == t.group(1).lower()))
            ).scalar_one_or_none()
            if thread:
                return thread
    refs = [x for x in re.findall(r"<[^>]+>", " ".join(filter(None, [m.in_reply_to or "", m.references]))) if x]
    if refs:
        row = (
            await db.execute(select(OutreachMessage.thread_id).where(OutreachMessage.message_id.in_(refs)).limit(1))
        ).scalar_one_or_none()
        if row:
            return await db.get(OutreachThread, row)
    addr = sender_address(m.sender)
    if addr:
        return (
            await db.execute(
                select(OutreachThread)
                .where(OutreachThread.contact_email == addr)
                .order_by(OutreachThread.last_outbound_at.desc())
                .limit(1)
            )
        ).scalar_one_or_none()
    return None


async def receive(db: AsyncSession, m: InboundMail) -> dict:
    """Keep a reply in its conversation. Returns {"result": stored | duplicate | unmatched | ignored | opt_out, "thread_id": ...}."""
    thread = await match_thread(db, m)
    if thread is None:
        log.warning(
            "inbound mail matched no conversation",
            extra={"sender": sender_address(m.sender), "subject": m.subject[:80]},
        )
        return {"result": "unmatched"}
    if (
        m.message_id
        and (
            await db.execute(
                select(OutreachMessage.id).where(
                    OutreachMessage.thread_id == thread.id, OutreachMessage.message_id == m.message_id
                )
            )
        ).first()
    ):
        return {"result": "duplicate", "thread_id": thread.id}
    clean = clean_reply(m.text) or m.text.strip()[:MAX_BODY]
    addr = sender_address(m.sender)
    automatic = is_automatic(m)
    mismatch = bool(addr) and domain_of(addr) != domain_of(thread.contact_email)
    msg = OutreachMessage(
        thread_id=thread.id,
        direction="in",
        kind="received",
        status="ignored" if automatic else "received",
        subject=m.subject.replace("\n", " ")[:300],
        body=clean,
        message_id=m.message_id,
        in_reply_to=m.in_reply_to,
        sender=m.sender[:320],
        ai={"automatic": automatic, "sender_mismatch": mismatch},
        actor=addr,
        sent_at=utcnow(),
    )
    try:
        async with db.begin_nested():
            db.add(msg)
            await db.flush()
    except IntegrityError:  # the same message arrived twice at once
        return {"result": "duplicate", "thread_id": thread.id}
    row = await db.get(DistributionRequest, thread.request_id)
    placement = await db.get(DistributionPlacement, thread.placement_id)
    if automatic:  # recorded for the history, never answered
        dist.activity(db, row, "outreach_auto_reply", {"thread_id": thread.id}, placement=placement) if row else None
        return {"result": "ignored", "thread_id": thread.id, "message_id": msg.id}
    thread.last_inbound_at = utcnow()
    thread.updated_at = utcnow()
    if wants_stop(clean):
        if await db.get(OutreachOptout, thread.contact_email) is None:
            db.add(OutreachOptout(email=thread.contact_email, reason="asked to stop by email"))
        thread.status = "do_not_contact"
        msg.ai = {**msg.ai, "opt_out": True}
        if row:
            dist.activity(db, row, "outreach_opt_out", {"thread_id": thread.id}, actor=addr, placement=placement)
        return {"result": "opt_out", "thread_id": thread.id, "message_id": msg.id}
    if thread.status not in {"do_not_contact", "agreed"}:
        thread.status = "replied"
    if row:
        dist.activity(db, row, "outreach_reply_received", {"thread_id": thread.id}, actor=addr, placement=placement)
    return {"result": "stored", "thread_id": thread.id, "message_id": msg.id}


def parse_rfc822(raw: bytes) -> InboundMail:
    """A raw email (from a mailbox) as an InboundMail: the plain-text part, or the HTML with its tags removed."""
    msg = message_from_bytes(raw, policy=default_policy)
    assert isinstance(msg, EmailMessage)
    body = msg.get_body(preferencelist=("plain", "html"))
    text = body.get_content() if body is not None else ""
    if body is not None and body.get_content_type() == "text/html":
        text = re.sub(r"<(script|style)[\s\S]*?</\1>", " ", text, flags=re.I)
        text = re.sub(r"<br\s*/?>|</p>|</div>", "\n", text, flags=re.I)
        text = re.sub(r"<[^>]+>", "", text)
    tos = [str(x) for x in (msg.get_all("To", []) + msg.get_all("Delivered-To", []) + msg.get_all("X-Original-To", []))]
    return InboundMail(
        to=[a for chunk in tos for a in re.split(r"[,;]\s*", chunk) if a],
        sender=str(msg.get("From", "")),
        subject=str(msg.get("Subject", "")),
        text=text or "",
        message_id=str(msg.get("Message-ID", "")).strip() or None,
        in_reply_to=str(msg.get("In-Reply-To", "")).strip() or None,
        references=str(msg.get("References", "")),
        headers={
            k: str(v)
            for k, v in msg.items()
            if k.lower() in {"auto-submitted", "x-autoreply", "x-autorespond", "precedence"}
        },
    )
