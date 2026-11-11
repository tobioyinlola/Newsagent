"""Marketing email to our own users, sent through the same sender as every other email.

Everything that sends marketing goes through `send()`, which applies the guards in one place: the engine switch, the pause
switch, the person's opt-out, the suppression list, a minimum gap between emails to one person, and a daily cap. Sign-in codes,
receipts and other account emails do not use this path and are never held back by it."""

import logging
import secrets
from datetime import timedelta

from pydantic import BaseModel, Field
from sqlalchemy import func, select
from sqlalchemy.exc import IntegrityError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.integrations import registry
from app.models import MarketingPref, MarketingSend, MarketingSuppression, SystemSetting, User, Workspace
from app.models.base import utcnow
from app.services import email_templates as templates

log = logging.getLogger("marketing")
KEY = "marketing"


class MarketingConfig(BaseModel):
    paused: bool = False  # the kill switch: nothing marketing goes out while true
    min_gap_days: int = Field(2, ge=0, le=60)  # at most one marketing email to a person in this many days
    daily_cap: int = Field(500, ge=0, le=100000)  # at most this many marketing emails a day, in total
    track: bool = True  # count opens (a tiny picture) and clicks on the button (a link through our site)
    per_minute: int = Field(20, ge=1, le=600)  # how fast a campaign is delivered, so a big list is spread out


def engine_mode() -> str:
    m = get_settings().marketing_email.strip().lower()
    return m if m in {"on", "dry_run"} else "off"


async def get_config(db: AsyncSession) -> MarketingConfig:
    row = await db.get(SystemSetting, KEY)
    return MarketingConfig.model_validate(row.value or {}) if row else MarketingConfig()


async def save_config(db: AsyncSession, actor: str, cfg: MarketingConfig) -> None:
    row = await db.get(SystemSetting, KEY)
    if row is None:
        row = SystemSetting(key=KEY, value={})
        db.add(row)
    row.value = cfg.model_dump()
    row.updated_by, row.updated_at = actor, utcnow()


# ---------- unsubscribe ----------
async def pref_for(db: AsyncSession, user_id: str) -> MarketingPref:
    pref = await db.get(MarketingPref, user_id)
    if pref is None:
        pref = MarketingPref(user_id=user_id, token=secrets.token_urlsafe(32))
        db.add(pref)
        await db.flush()
    return pref


def tracking_url(kind: str, token: str) -> str:
    """The address an email's open picture (o) or button (c) points at. Like the unsubscribe link, it is on the app's own domain."""
    return f"{get_settings().app_base_url.rstrip('/')}/v1/m/{kind}/{token}"


def unsubscribe_url(token: str) -> str:
    return f"{get_settings().app_base_url.rstrip('/')}/v1/unsubscribe/{token}"


async def set_opt_out(db: AsyncSession, token: str, out: bool, source: str) -> MarketingPref | None:
    pref = (await db.execute(select(MarketingPref).where(MarketingPref.token == token))).scalar_one_or_none()
    if pref is None:
        return None
    pref.opted_out_at, pref.source = (utcnow() if out else None), source
    return pref


async def suppress(db: AsyncSession, email: str, reason: str) -> None:
    email = email.strip().lower()
    if await db.get(MarketingSuppression, email) is None:
        db.add(MarketingSuppression(email=email, reason=reason[:100]))


# ---------- sending ----------
async def _skip_reason(db: AsyncSession, user: User, cfg: MarketingConfig, now) -> str:
    if cfg.paused:
        return "paused"
    pref = await db.get(MarketingPref, user.id)
    if pref is not None and pref.opted_out_at is not None:
        return "opted_out"
    if await db.get(MarketingSuppression, user.email.strip().lower()) is not None:
        return "suppressed"
    ws = await db.get(Workspace, user.workspace_id)
    if ws is None or ws.deleted_at is not None or ws.suspended:
        return "account_inactive"
    if cfg.min_gap_days:
        last = (
            await db.execute(
                select(func.max(MarketingSend.created_at)).where(
                    MarketingSend.user_id == user.id, MarketingSend.status.in_(("sent", "dry_run"))
                )
            )
        ).scalar_one_or_none()
        if last is not None and (last if last.tzinfo else last.replace(tzinfo=now.tzinfo)) > now - timedelta(
            days=cfg.min_gap_days
        ):
            return "too_soon"
    start = now.replace(hour=0, minute=0, second=0, microsecond=0)
    today = (
        await db.execute(
            select(func.count())
            .select_from(MarketingSend)
            .where(MarketingSend.status.in_(("sent", "dry_run")), MarketingSend.created_at >= start)
        )
    ).scalar_one()
    if today >= cfg.daily_cap:
        return "daily_cap"
    return ""


async def send(
    db: AsyncSession,
    user: User,
    subject: str,
    body: str,
    *,
    button: tuple[str, str] | None = None,
    heading: str | None = None,
    preheader: str = "",
    kind: str = "campaign",
    ref: str = "",
    idempotency_key: str | None = None,
    provider=None,
) -> str:
    """Send one marketing email to one user. Returns "sent", "dry_run", or "skipped:<reason>"; a failed send returns "failed".
    The same `idempotency_key` never sends twice. The caller commits."""
    mode = engine_mode()
    if mode == "off":
        return "skipped:engine_off"
    if (
        idempotency_key
        and (await db.execute(select(MarketingSend.id).where(MarketingSend.idempotency_key == idempotency_key))).first()
    ):
        return "skipped:already_sent"
    cfg = await get_config(db)
    now = utcnow()
    reason = await _skip_reason(db, user, cfg, now)

    def log_row(status: str, why: str = "", **extra) -> MarketingSend:
        row = MarketingSend(
            **extra,
            user_id=user.id,
            kind=kind,
            ref=ref,
            subject=subject[:500],
            status=status,
            skip_reason=why,
            idempotency_key=idempotency_key if status != "skipped" else None,
        )
        db.add(row)
        return row

    if reason:
        if reason not in {
            "paused",
            "daily_cap",
        }:  # these pass by themselves and are retried every minute: don't log each try
            log_row("skipped", reason)
        return f"skipped:{reason}"
    if mode == "dry_run":
        log_row("dry_run")
        return "dry_run"
    pref = await pref_for(db, user.id)
    link = unsubscribe_url(pref.token)
    token = click_url = pixel = None
    if cfg.track:
        token = secrets.token_urlsafe(24)
        pixel = tracking_url("o", token) + ".gif"
        if button:
            click_url, button = button[1], (button[0], tracking_url("c", token))
    html, text = templates.render(
        heading or subject,
        body,
        button=button,
        preheader=preheader,
        pixel=pixel or "",
        footer="You are receiving this because you have a Cover Founder account. You can stop these emails at any time.",
        footer_link=("Unsubscribe", link),
    )
    headers = {"List-Unsubscribe": f"<{link}>", "List-Unsubscribe-Post": "List-Unsubscribe=One-Click"}
    row = log_row("sent", track_token=token, click_url=click_url)
    try:
        await db.flush()
    except IntegrityError:  # the same send raced in from another worker
        await db.rollback()
        return "skipped:already_sent"
    try:
        await (provider or registry.get_email()).send(user.email, subject, text, html, headers=headers)
    except Exception:  # noqa: BLE001  a failed email must not break the run
        log.exception("marketing email failed: %s", subject)
        row.status, row.idempotency_key = "failed", None
        return "failed"
    return "sent"


async def send_test(db: AsyncSession, to: User, subject: str, text: str, html: str, *, provider=None) -> None:
    """A copy sent to the operator's own address to check it. It skips the opt-out, gap and cap (it is one email to oneself),
    works while the engine is off, is marked as a test, and never counts toward the caps. Raises if the email can't go."""
    await (provider or registry.get_email()).send(to.email, f"[Test] {subject}", text, html)
    db.add(MarketingSend(user_id=to.id, kind="test", subject=subject[:500], status="test"))
