"""The agent that reads an outlet's reply and writes our next email.

The model only reads and drafts. WHAT HAPPENS NEXT is decided here, in code:
  * a step type is worked out from what the outlet said and what the draft contains (not from what the model claims),
  * a table of steps says auto or approve, editable by the team; the money steps (payment terms, accepting an offer, asking for or confirming
    account details) can never be automatic,
  * anything about a price, an account, a deadline, a link, an unexpected sender, a low-confidence reading or a suspicious email is held for a person,
  * the agent never pays, never marks anything paid or published, and never repeats bank details.
"""

import json
import logging
import re
from dataclasses import dataclass, field
from datetime import timedelta

from pydantic import BaseModel, Field, field_validator
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import session_maker
from app.integrations import registry
from app.models import DistributionRequest, OutreachMessage, OutreachThread
from app.models.base import utcnow
from app.services import crypto, outreach
from app.services import distribution as dist
from app.services.notifications import notify_operators

log = logging.getLogger("outreach")

# step id -> label, default policy, never automatic
STEPS: dict[str, dict] = {
    "thanks": {"label": "Thank them", "default": "auto", "never_auto": False},
    "ask_rates": {"label": "Ask for their rates", "default": "auto", "never_auto": False},
    "ask_timeline": {"label": "Ask how soon it can go live", "default": "auto", "never_auto": False},
    "send_materials": {"label": "Send the story materials again", "default": "auto", "never_auto": False},
    "answer_question": {"label": "Answer a question about the story", "default": "auto", "never_auto": False},
    "discuss_price": {"label": "Talk about their price", "default": "approve", "never_auto": False},
    "confirm_price": {"label": "Confirm a price", "default": "approve", "never_auto": False},
    "deadline": {"label": "Agree a date or deadline", "default": "approve", "never_auto": False},
    "other": {"label": "Anything else", "default": "approve", "never_auto": False},
    "accept_offer": {"label": "Accept their offer (commit to pay)", "default": "approve", "never_auto": True},
    "payment_terms": {"label": "Payment arrangements", "default": "approve", "never_auto": True},
    "request_account_details": {"label": "Ask for their account details", "default": "approve", "never_auto": True},
    "confirm_account_details": {"label": "Confirm account details", "default": "approve", "never_auto": True},
}
RESTRICTIVE = [
    "accept_offer",
    "payment_terms",
    "request_account_details",
    "confirm_account_details",
    "confirm_price",
    "discuss_price",
    "deadline",
    "other",
]
MIN_CONFIDENCE = 0.7

MONEY_RE = re.compile(
    r"([$€£₦]\s?\d|\b\d[\d,.]*\s?(usd|ngn|eur|gbp|dollars?|naira|credits?)\b|\b(usd|ngn|eur|gbp)\s?\d)", re.I
)
ACCOUNT_WORD_RE = re.compile(
    r"\b(bank|account (number|no)|iban|swift|routing|sort code|wire|bank transfer|beneficiary)\b", re.I
)
DEADLINE_RE = re.compile(
    r"\b(deadline|by (monday|tuesday|wednesday|thursday|friday|saturday|sunday|tomorrow|tonight|end of)|within \d+ (hours?|days?)|asap|on \d{1,2}(st|nd|rd|th)?\s)",
    re.I,
)
URL_RE = re.compile(r"https?://|www\.", re.I)
LONG_DIGITS = re.compile(r"\d{6,}")
INJECTION_RE = re.compile(
    r"ignore (all |your |the )?(previous|prior|above) (instructions|rules)|system prompt|you are now|disregard (your|the) (rules|instructions)",
    re.I,
)


class Analysis(BaseModel):
    intent: str = "unclear"
    confidence: float = Field(default=0.0, ge=0, le=1)
    summary: str = Field(default="", max_length=400)
    quoted_price: float | None = None
    currency: str | None = Field(default=None, max_length=8)
    deadline: str | None = Field(default=None, max_length=120)
    asks: list[str] = Field(default_factory=list, max_length=10)
    account_details: dict | None = None
    suspicious: bool = False

    @field_validator("intent")
    @classmethod
    def known(cls, v):
        known = {
            "accepts",
            "asks_question",
            "quotes_price",
            "requests_details",
            "requests_payment_terms",
            "sends_account_details",
            "declines",
            "out_of_office",
            "complaint",
            "unclear",
        }
        return v if v in known else "unclear"

    @field_validator("confidence", mode="before")
    @classmethod
    def number(cls, v):
        try:
            return min(1.0, max(0.0, float(v)))
        except (TypeError, ValueError):
            return 0.0

    @field_validator("quoted_price", mode="before")
    @classmethod
    def price(cls, v):
        try:
            return float(v) if v not in (None, "") else None
        except (TypeError, ValueError):
            return None

    @field_validator("account_details", mode="before")
    @classmethod
    def details(cls, v):
        return v if isinstance(v, dict) and any(x for x in v.values()) else None


class Draft(BaseModel):
    subject: str = Field(default="", max_length=250)
    body: str = Field(min_length=1, max_length=4000)
    step: str = "other"

    @field_validator("step")
    @classmethod
    def known(cls, v):
        return v if v in STEPS else "other"


@dataclass
class Flags:
    money: bool = False
    account: bool = False
    deadline: bool = False
    link: bool = False
    digits: bool = False
    injection: bool = False
    reasons: list[str] = field(default_factory=list)


def content_flags(draft_text: str, inbound_text: str) -> Flags:
    f = Flags(
        money=bool(MONEY_RE.search(draft_text)),
        account=bool(ACCOUNT_WORD_RE.search(draft_text)),
        deadline=bool(DEADLINE_RE.search(draft_text)),
        link=bool(URL_RE.search(draft_text)),
        digits=bool(LONG_DIGITS.search(draft_text)),
        injection=bool(INJECTION_RE.search(inbound_text)),
    )
    return f


def effective_policy(cfg: outreach.OutreachConfig) -> dict[str, str]:
    return {k: ("approve" if v["never_auto"] else cfg.policy.get(k, v["default"])) for k, v in STEPS.items()}


def effective_step(declared: str, analysis: Analysis, flags: Flags) -> str:
    """The most restrictive of what the model said, what the outlet said, and what the draft actually contains."""
    candidates = [declared if declared in STEPS else "other"]
    if analysis.intent == "quotes_price" or analysis.quoted_price is not None:
        candidates.append("discuss_price")
    if analysis.intent == "sends_account_details" or analysis.account_details:
        candidates.append("confirm_account_details")
    if analysis.intent == "requests_payment_terms":
        candidates.append("payment_terms")
    if analysis.intent in {"complaint", "unclear"}:
        candidates.append("other")
    if flags.money:
        candidates.append("discuss_price")
    if flags.account:
        candidates.append("confirm_account_details")
    if flags.deadline or analysis.deadline:
        candidates.append("deadline")
    order = {s: i for i, s in enumerate(RESTRICTIVE)}
    risky = [c for c in candidates if c in order]
    return min(risky, key=lambda c: order[c]) if risky else candidates[0]


def decide(
    cfg: outreach.OutreachConfig,
    thread: OutreachThread,
    analysis: Analysis,
    step: str,
    flags: Flags,
    inbound_meta: dict,
    sent_today: int,
) -> tuple[bool, list[str]]:
    """(may it be sent without a person, why not). Pure: the same inputs always give the same answer."""
    why: list[str] = []
    if cfg.mode == "draft":
        why.append("The agent is in draft mode: every reply needs approval.")
    info = STEPS[step]
    if info["never_auto"]:
        why.append(f"“{info['label']}” involves payment or account details, so a person always handles it.")
    elif effective_policy(cfg).get(step) == "approve":
        why.append(f"Your settings require approval for “{info['label']}”.")
    if analysis.confidence < MIN_CONFIDENCE:
        why.append("The agent was not sure it understood the reply.")
    if analysis.suspicious or flags.injection:
        why.append("The email looks like it is trying to instruct the agent, or looks suspicious.")
    if inbound_meta.get("sender_mismatch"):
        why.append("The reply came from a different company than the contact we wrote to.")
    if thread.ai_turns >= cfg.ai_turn_limit:
        why.append(f"The agent has already written {thread.ai_turns} replies in this conversation.")
    if flags.money:
        why.append("The draft mentions an amount.")
    if flags.account or flags.digits:
        why.append("The draft mentions bank or account details.")
    if flags.deadline:
        why.append("The draft mentions a date or deadline.")
    if flags.link:
        why.append("The draft contains a link.")
    if analysis.intent in {"complaint", "unclear"}:
        why.append("The reply is a complaint or was unclear.")
    if sent_today >= cfg.daily_cap:
        why.append("The daily limit for automatic replies has been reached.")
    return (not why), why


def mask_digits(text: str) -> str:
    return re.sub(r"\d{6,}", lambda m: "••••" + m.group(0)[-4:], text)


def mask_account(details: dict) -> str:
    parts = []
    for k in ("bank_name", "account_name"):
        if details.get(k):
            parts.append(str(details[k])[:60])
    for k in ("account_number", "iban", "routing", "swift"):
        v = str(details.get(k) or "").replace(" ", "")
        if v:
            parts.append("••••" + v[-4:])
    return " · ".join(parts) or "details received"


async def _history(db: AsyncSession, thread: OutreachThread, upto: OutreachMessage) -> list[dict]:
    rows = (
        (
            await db.execute(
                select(OutreachMessage)
                .where(
                    OutreachMessage.thread_id == thread.id,
                    OutreachMessage.status.in_(["sent", "queued", "received"]),
                    OutreachMessage.created_at < upto.created_at,
                )
                .order_by(OutreachMessage.created_at.desc())
                .limit(8)
            )
        )
        .scalars()
        .all()
    )
    return [
        {"from": "us" if m.direction == "out" else "them", "text": mask_digits(m.body)[:1500]} for m in reversed(rows)
    ]


async def _notify(thread: OutreachThread, why: str) -> None:
    try:
        await notify_operators(
            why,
            f"{thread.outlet_name}: open the Outreach inbox in the back office: {get_settings().admin_base_url}/outreach",
        )
    except Exception:  # noqa: BLE001
        log.exception("could not notify the team")


async def sent_today(db: AsyncSession) -> int:
    since = utcnow() - timedelta(hours=24)
    return int(
        (
            await db.execute(
                select(func.count())
                .select_from(OutreachMessage)
                .where(OutreachMessage.kind == "ai_auto", OutreachMessage.created_at > since)
            )
        ).scalar_one()
    )


async def handle_reply(thread_id: str, message_id: str, force: bool = False) -> dict:
    """Read one stored reply and either answer it or hold a draft for a person. Safe to run twice."""
    deliver_for: str | None = None
    notify: str | None = None
    async with session_maker()() as db:
        thread = await db.get(OutreachThread, thread_id)
        msg = await db.get(OutreachMessage, message_id)
        if (
            thread is None
            or msg is None
            or msg.direction != "in"
            or msg.status != "received"
            or msg.ai.get("processed")
        ):
            return {"result": "skipped"}
        cfg = await outreach.get_config(db)
        if not outreach.enabled() or thread.status in {"do_not_contact", "closed"}:
            return {"result": "skipped"}
        if (cfg.paused or thread.ai_paused) and not force:  # a person asking for a draft overrides a pause
            return {"result": "skipped"}
        later_human = (
            await db.execute(
                select(OutreachMessage.id)
                .where(
                    OutreachMessage.thread_id == thread.id,
                    OutreachMessage.direction == "out",
                    OutreachMessage.kind == "human",
                    OutreachMessage.created_at > msg.created_at,
                )
                .limit(1)
            )
        ).first()
        if later_human:  # a person already answered this one
            msg.ai = {**msg.ai, "processed": True}
            await db.commit()
            return {"result": "skipped"}
        row = await db.get(DistributionRequest, thread.request_id)
        if row is None:
            return {"result": "skipped"}
        llm = registry.get_llm()
        original = msg.body
        context = {
            "outlet": thread.outlet_name,
            "contact_name": thread.contact_name,
            "headline": row.data.get("headline", ""),
            "summary": str(row.data.get("announcement", ""))[:600],
            "sender_name": cfg.sender_name,
            "history": await _history(db, thread, msg),
            "latest": original,
        }
        try:
            analysis = Analysis.model_validate(await llm.analyze_outreach_reply(context))
        except Exception as e:  # noqa: BLE001
            return await _fail(db, thread, msg, f"The agent could not read this reply ({type(e).__name__}).")
        meta = {
            **msg.ai,
            "intent": analysis.intent,
            "confidence": analysis.confidence,
            "summary": mask_digits(analysis.summary),
            "suspicious": analysis.suspicious,
        }
        details = analysis.account_details
        if not details and ACCOUNT_WORD_RE.search(original) and LONG_DIGITS.search(original):
            details = {"other": "details in the message"}
            analysis.intent = (
                "sends_account_details" if analysis.intent not in {"declines", "complaint"} else analysis.intent
            )
        facts = dict(thread.facts or {})
        if analysis.quoted_price is not None:
            facts["quoted_price"], facts["currency"] = analysis.quoted_price, analysis.currency
        if analysis.deadline:
            facts["deadline"] = analysis.deadline
        if details:  # stored encrypted, shown masked, revealed only on request (audited)
            facts["account_details_enc"] = crypto.encrypt(json.dumps(details))
            facts["account_masked"] = mask_account(details)
            facts["account_verified_by"] = None
            meta["has_account_details"] = True
            meta["original_enc"] = crypto.encrypt(original)
            msg.body = mask_digits(original)
        facts["last_intent"] = analysis.intent
        thread.facts = facts
        if analysis.intent == "out_of_office":
            msg.status, msg.ai = "ignored", {**meta, "processed": True}
            await db.commit()
            return {"result": "ignored"}
        if analysis.intent == "declines":
            thread.status = "closed"
            msg.ai = {**meta, "processed": True}
            await db.commit()
            await _notify(thread, "An outlet declined")
            return {"result": "closed"}
        try:
            safe_analysis = {**analysis.model_dump(), "account_details": None, "has_account_details": bool(details)}
            draft = Draft.model_validate(await llm.draft_outreach_reply(context, safe_analysis))
        except Exception as e:  # noqa: BLE001
            return await _fail(db, thread, msg, f"The agent could not write a reply ({type(e).__name__}).", meta)
        flags = content_flags(draft.body, original)
        step = effective_step(draft.step, analysis, flags)
        auto, why = decide(cfg, thread, analysis, step, flags, msg.ai, await sent_today(db))
        subject = draft.subject or None
        msg.ai = {**meta, "processed": True, "step": step}
        ai = {"step": step, "intent": analysis.intent, "confidence": analysis.confidence, "reasons": why}
        if auto:
            try:
                await outreach.send_reply(db, thread, draft.body, "ai", subject=subject, kind="ai_auto", ai=ai)
            except outreach.CannotSend:
                await db.commit()
                return {"result": "skipped"}
            thread.ai_turns += 1
            thread.status = "awaiting_reply"
            deliver_for = thread.request_id
            result = "sent"
        else:
            db.add(
                OutreachMessage(
                    thread_id=thread.id,
                    direction="out",
                    kind="ai_draft",
                    status="pending_approval",
                    subject=(subject or "Re: " + (msg.subject or "your reply"))[:300],
                    body=draft.body,
                    ai=ai,
                    actor="ai",
                )
            )
            thread.status = "needs_approval"
            notify = "A reply is waiting for your approval"
            result = "held"
        thread.updated_at = utcnow()
        if row:
            dist.activity(db, row, f"outreach_agent_{result}", {"thread_id": thread.id, "step": step}, actor="ai")
        await db.commit()
    if deliver_for:
        await dist.deliver_request(deliver_for)
    if notify:
        await _notify(thread, notify)
    return {"result": result}


async def _fail(
    db: AsyncSession, thread: OutreachThread, msg: OutreachMessage, why: str, meta: dict | None = None
) -> dict:
    """The model failed or answered nonsense: a person takes it from here, nothing is sent."""
    msg.ai = {**(meta or msg.ai), "processed": True, "error": why}
    thread.status = "needs_approval"
    thread.updated_at = utcnow()
    await db.commit()
    await _notify(thread, "A reply needs your attention")
    return {"result": "failed"}


async def will_handle(db: AsyncSession, thread_id: str) -> bool:
    """Whether the agent will read a new reply in this conversation (it is on, not paused, and no person has taken over)."""
    thread = await db.get(OutreachThread, thread_id)
    if thread is None or thread.ai_paused or thread.status in {"do_not_contact", "closed"}:
        return False
    cfg = await outreach.get_config(db)
    return outreach.enabled() and not cfg.paused


def schedule(thread_id: str, message_id: str, force: bool = False) -> None:
    from app.pipeline.queue import enqueue

    enqueue("outreach_reply", {"thread_id": thread_id, "message_id": message_id, "force": force})


async def approve_draft(
    db: AsyncSession,
    thread: OutreachThread,
    draft: OutreachMessage,
    actor: str,
    body: str | None = None,
    send_now: bool = False,
) -> OutreachMessage:
    """A person approves (optionally after editing) a held draft: it is sent from the conversation as their decision."""
    if draft.kind != "ai_draft" or draft.status != "pending_approval":
        raise outreach.CannotSend("That draft is no longer waiting for approval.")
    text = (body or draft.body).strip()
    sent = await outreach.send_reply(
        db,
        thread,
        text,
        actor,
        subject=draft.subject,
        kind="ai_draft",
        ai={**draft.ai, "approved_by": actor, "edited": text != draft.body.strip()},
        send_now=send_now,
    )
    draft.status = "discarded"
    draft.ai = {**draft.ai, "approved_by": actor}
    thread.ai_turns += 1
    return sent


async def requeue_unprocessed() -> int:
    """A reply stored but never read (the worker restarted) is handed to the agent again."""
    since, cutoff = utcnow() - timedelta(days=2), utcnow() - timedelta(minutes=3)
    n = 0
    async with session_maker()() as db:
        rows = (
            (
                await db.execute(
                    select(OutreachMessage).where(
                        OutreachMessage.direction == "in",
                        OutreachMessage.status == "received",
                        OutreachMessage.created_at > since,
                        OutreachMessage.created_at < cutoff,
                    )
                )
            )
            .scalars()
            .all()
        )
        todo = [(m.thread_id, m.id) for m in rows if not m.ai.get("processed")]
    for t, m in todo:
        schedule(t, m)
        n += 1
    return n
