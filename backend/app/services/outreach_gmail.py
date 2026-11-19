"""The mailbox outreach is sent from and replies are read from: a Gmail (or Google Workspace) address connected in the back office.

Google no longer lets an app sign in with a plain password, so the connection uses an *app password* (a 16-letter password made in the
Google account, which needs 2-step verification). It is kept encrypted in the settings table and never sent back to the browser.

Two ways to send, chosen when the mailbox is connected:
- `smtp`: straight through Gmail, so every email also sits in the mailbox's Sent folder.
- `relay`: when the host blocks outgoing SMTP (Railway does on its Free, Trial and Hobby plans), the email goes out through the app's usual
  email service instead, with the Gmail address as the reply address and a hidden copy sent to it. Replies and copies still land in Gmail.
Replies are read from the mailbox over IMAP either way."""

import asyncio
import imaplib
import logging
import smtplib
from dataclasses import dataclass
from email.utils import formataddr

from pydantic import EmailStr, TypeAdapter, ValidationError
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.integrations import registry
from app.integrations.email.base import EmailProvider
from app.integrations.email.smtp import SmtpEmail
from app.models import SystemSetting
from app.models.base import utcnow
from app.services import crypto
from app.services.audit import audit

log = logging.getLogger("outreach.mailbox")
KEY = "outreach_mailbox"
SMTP_HOST, SMTP_PORT = "smtp.gmail.com", 587
IMAP_HOST, IMAP_PORT = "imap.gmail.com", 993
TIMEOUT_S = 12


class ConnectFailed(Exception):
    """The mailbox could not be connected; `.result` says why, in plain words, with the steps to fix it."""

    def __init__(self, result: dict) -> None:
        super().__init__(result.get("message", ""))
        self.result = result


@dataclass(frozen=True)
class Mailbox:
    address: str
    password: str
    mode: str  # smtp | relay


def clean_password(raw: str) -> str:
    """Google shows an app password in groups of four with spaces; the spaces are not part of it."""
    return "".join(raw.split())


def valid_address(raw: str) -> str:
    try:
        return str(TypeAdapter(EmailStr).validate_python(raw.strip())).lower()
    except ValidationError:
        raise ValueError("Enter the full Gmail address, like name@gmail.com.") from None


# ---------- what is stored ----------
async def _row(db: AsyncSession) -> SystemSetting | None:
    return await db.get(SystemSetting, KEY)


async def current(db: AsyncSession) -> Mailbox | None:
    """The connected mailbox, or None (then outreach falls back to the OUTREACH_* settings, if any)."""
    row = await _row(db)
    v = (row.value if row else None) or {}
    if not v.get("address") or not v.get("password_enc"):
        return None
    try:
        return Mailbox(v["address"], crypto.decrypt(v["password_enc"]), v.get("mode", "smtp"))
    except Exception:  # noqa: BLE001  a key change or damaged value: treat as not connected rather than crash every send
        log.exception("could not read the stored mailbox password")
        return None


async def address(db: AsyncSession) -> str | None:
    """The address replies come back to (plus-addressed per conversation)."""
    box = await current(db)
    if box:
        return box.address
    env = get_settings().outreach_mailbox.strip()
    return env if "@" in env else None


async def ready(db: AsyncSession) -> bool:
    """Whether outreach has somewhere to send from and read replies at. Without it nothing is sent, so a reply can never go unseen."""
    s = get_settings()
    routes = (s.outreach_smtp_host, s.outreach_reply_domain, s.outreach_imap_host, s.outreach_mailbox if "@" in s.outreach_mailbox else "")
    return bool(await current(db) or any(x.strip() for x in routes))  # a connected Gmail, or any reply route set in the settings


class _CopyTo(EmailProvider):
    """Wraps a provider so every email also goes, hidden, to one more address (the Gmail mailbox, in relay mode)."""

    def __init__(self, inner: EmailProvider, bcc: str) -> None:
        self.inner, self.bcc = inner, bcc

    async def send(self, to, subject, text, html=None, *, reply_to=None, headers=None, cc=None, bcc=None) -> None:  # type: ignore[no-untyped-def]
        await self.inner.send(
            to, subject, text, html, reply_to=reply_to, headers=headers, cc=cc, bcc=[*(bcc or []), self.bcc]
        )


async def provider(db: AsyncSession) -> EmailProvider:
    """Who sends conversation emails: the connected mailbox, else the OUTREACH_SMTP_* settings, else the app's usual sender."""
    box = await current(db)
    if box is None:
        return registry.get_outreach_email()
    if box.mode == "relay":
        return _CopyTo(registry.get_email(), box.address)
    return SmtpEmail(
        SMTP_HOST,
        SMTP_PORT,
        box.address,
        box.password,
        starttls=True,
        sender=formataddr((get_settings().outreach_from_name, box.address)),
    )


async def imap_credentials(db: AsyncSession) -> tuple[str, int, str, str, str] | None:
    """(host, port, user, password, folder) of the mailbox to read replies from."""
    box = await current(db)
    if box:
        return IMAP_HOST, IMAP_PORT, box.address, box.password, "INBOX"
    s = get_settings()
    if s.outreach_imap_host and s.outreach_imap_user and s.outreach_imap_password:
        return s.outreach_imap_host, s.outreach_imap_port, s.outreach_imap_user, s.outreach_imap_password, s.outreach_imap_folder
    return None


# ---------- trying a connection ----------
def _check_smtp(addr: str, password: str) -> str:
    try:
        with smtplib.SMTP(SMTP_HOST, SMTP_PORT, timeout=TIMEOUT_S) as s:
            s.starttls()
            s.login(addr, password)
        return "ok"
    except smtplib.SMTPAuthenticationError:
        return "login_failed"
    except (OSError, TimeoutError, smtplib.SMTPConnectError, smtplib.SMTPServerDisconnected):
        return "blocked"  # could not even reach Google: the host does not allow outgoing SMTP
    except Exception:  # noqa: BLE001
        log.exception("unexpected error while testing SMTP")
        return "error"


def _check_imap(addr: str, password: str) -> str:
    try:
        box = imaplib.IMAP4_SSL(IMAP_HOST, IMAP_PORT, timeout=TIMEOUT_S)
        try:
            box.login(addr, password)
        finally:
            try:
                box.logout()
            except Exception:  # noqa: BLE001
                pass
        return "ok"
    except imaplib.IMAP4.error:
        return "login_failed"
    except (OSError, TimeoutError):
        return "unreachable"
    except Exception:  # noqa: BLE001
        log.exception("unexpected error while testing IMAP")
        return "error"


async def test_connection(addr: str, password: str) -> dict:
    """Try both doors and say what happened in plain words. Nothing is saved."""
    smtp, imap = await asyncio.gather(
        asyncio.to_thread(_check_smtp, addr, password), asyncio.to_thread(_check_imap, addr, password)
    )
    steps = [
        "In your Google account, turn on 2-step verification.",
        "Create an app password (Google Account > Security > App passwords) and paste it here.",
        "In Gmail, open Settings > See all settings > Forwarding and POP/IMAP and make sure IMAP is enabled.",
    ]
    result: dict = {"smtp": smtp, "imap": imap, "ok": False, "mode": None, "message": "", "steps": []}
    if smtp == "login_failed" or (smtp == "blocked" and imap == "login_failed"):
        result["message"] = "Google did not accept that address and app password. Check them and try again."
        result["steps"] = steps[:2]
    elif imap == "login_failed":
        result["message"] = "Google accepted the password for sending, but would not let us read the inbox. IMAP is probably switched off."
        result["steps"] = steps[2:]
    elif imap != "ok":
        result["message"] = "We could not reach Gmail to read replies just now. Please try again in a minute."
    elif smtp == "ok":
        result.update(ok=True, mode="smtp", message="Connected. Emails will be sent from this Gmail address, and replies will come back to it.")
    elif smtp == "blocked":
        result.update(
            ok=True,
            mode="relay",
            message=(
                "Connected for reading replies. Our hosting blocks sending straight through Gmail, so emails will go out through our email "
                "service instead, with this Gmail address as the reply address and a copy sent to it. Replies still land in your Gmail."
            ),
        )
    else:
        result["message"] = "Something unexpected stopped the test. Please try again."
    return result


# ---------- connecting ----------
async def connect(db: AsyncSession, actor: str, raw_address: str, raw_password: str) -> dict:
    """Test, and if it works, save (encrypted). Raises ValueError with a plain message when it does not work."""
    addr, password = valid_address(raw_address), clean_password(raw_password)
    if len(password) < 8:
        raise ValueError("Paste the app password Google gave you.")
    tested = await test_connection(addr, password)
    if not tested["ok"]:
        raise ConnectFailed(tested)
    row = await _row(db)
    value = {
        "address": addr,
        "password_enc": crypto.encrypt(password),
        "mode": tested["mode"],
        "connected_by": actor,
        "connected_at": utcnow().isoformat(),
        "checked_at": utcnow().isoformat(),
        "last_error": "",
        "last_polled_at": None,
    }
    if row is None:
        db.add(SystemSetting(key=KEY, value=value, updated_by=actor))
    else:
        row.value, row.updated_by, row.updated_at = value, actor, utcnow()
    audit(db, actor, "outreach.mailbox_connected", target_type="setting", target_id=KEY, detail={"address": addr, "mode": tested["mode"]})
    await db.commit()
    return tested


async def disconnect(db: AsyncSession, actor: str) -> None:
    row = await _row(db)
    if row is not None:
        addr = (row.value or {}).get("address")
        await db.delete(row)
        audit(db, actor, "outreach.mailbox_disconnected", target_type="setting", target_id=KEY, detail={"address": addr})
        await db.commit()


async def note_poll(db: AsyncSession, error: str = "") -> None:
    """Remember how the last look at the inbox went, so the back office can say so. Only for a connected (not environment) mailbox."""
    row = await _row(db)
    if row is None or not (row.value or {}).get("address"):
        return
    v = dict(row.value)
    v["last_error"], v["last_polled_at"] = error[:300], utcnow().isoformat()
    row.value = v
    await db.commit()


async def status(db: AsyncSession) -> dict:
    """What the back office shows. The password is never included."""
    s = get_settings()
    row = await _row(db)
    v = (row.value if row else None) or {}
    connected = bool(v.get("address") and v.get("password_enc"))
    env_address = s.outreach_mailbox.strip() or s.outreach_smtp_user.strip()
    mode = v.get("mode") if connected else ("smtp" if s.outreach_smtp_host.strip() else None)
    return {
        "connected": connected,
        "address": v.get("address") if connected else (env_address or None),
        "source": "back office" if connected else ("environment" if s.outreach_smtp_host.strip() else None),
        "mode": mode,
        "sends_via": {"smtp": "Gmail", "relay": "our email service, with a copy to your Gmail"}.get(mode or ""),
        "connected_by": v.get("connected_by") if connected else None,
        "connected_at": v.get("connected_at") if connected else None,
        "last_polled_at": v.get("last_polled_at") if connected else None,
        "last_error": v.get("last_error", "") if connected else "",
        "ready": await ready(db),
        "outreach_on": s.outreach_ai == "on",
    }
