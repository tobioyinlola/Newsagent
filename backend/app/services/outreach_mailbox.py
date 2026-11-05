"""Read replies from a mailbox over IMAP (the fallback when a provider cannot post inbound mail to the webhook)."""

import asyncio
import imaplib
import logging

from app.config import get_settings
from app.db import session_maker
from app.services import outreach, outreach_agent, outreach_inbound

log = logging.getLogger("outreach")


def configured() -> bool:
    s = get_settings()
    return bool(outreach.enabled() and s.outreach_imap_host and s.outreach_imap_user and s.outreach_imap_password)


def _fetch_unseen() -> list[tuple[bytes, bytes]]:
    """(id, raw message) of each unread message. They are marked read only after they are safely stored."""
    s = get_settings()
    box = imaplib.IMAP4_SSL(s.outreach_imap_host, s.outreach_imap_port)
    try:
        box.login(s.outreach_imap_user, s.outreach_imap_password)
        box.select(s.outreach_imap_folder)
        _, found = box.search(None, "UNSEEN")
        out = []
        for num in (found[0] or b"").split()[:50]:
            _, data = box.fetch(num.decode(), "(BODY.PEEK[])")
            if data and isinstance(data[0], tuple):
                out.append((num, data[0][1]))
        return out
    finally:
        try:
            box.logout()
        except Exception:  # noqa: BLE001
            pass


def _mark_seen(nums: list[bytes]) -> None:
    s = get_settings()
    box = imaplib.IMAP4_SSL(s.outreach_imap_host, s.outreach_imap_port)
    try:
        box.login(s.outreach_imap_user, s.outreach_imap_password)
        box.select(s.outreach_imap_folder)
        for n in nums:
            box.store(n.decode(), "+FLAGS", "\\Seen")
    finally:
        try:
            box.logout()
        except Exception:  # noqa: BLE001
            pass


async def poll_once() -> int:
    """Store new replies. Returns how many were kept. A message that fails stays unread and is tried again next time."""
    if not configured():
        return 0
    messages = await asyncio.to_thread(_fetch_unseen)
    done: list[bytes] = []
    kept = 0
    for num, raw in messages:
        try:
            mail = outreach_inbound.parse_rfc822(raw)
            async with session_maker()() as db:
                result = await outreach_inbound.receive(db, mail)
                await db.commit()
                if result["result"] == "stored" and await outreach_agent.will_handle(db, result["thread_id"]):
                    outreach_agent.schedule(result["thread_id"], result["message_id"])
            kept += result["result"] == "stored"
            done.append(num)
        except Exception:  # noqa: BLE001
            log.exception("could not store an inbound email; it stays unread")
    if done:
        await asyncio.to_thread(_mark_seen, done)
    return kept
