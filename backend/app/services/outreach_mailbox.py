"""Read replies from a mailbox over IMAP: the Gmail connected in the back office, or the OUTREACH_IMAP_* settings (also the fallback
when a provider cannot post inbound mail to the webhook)."""

import asyncio
import imaplib
import logging

from app.db import session_maker
from app.services import outreach_gmail

log = logging.getLogger("outreach")
Creds = tuple[str, int, str, str, str]  # host, port, user, password, folder


def _fetch_unseen(creds: Creds) -> list[tuple[bytes, bytes]]:
    """(id, raw message) of each unread message. They are marked read only after they are safely stored."""
    host, port, user, password, folder = creds
    box = imaplib.IMAP4_SSL(host, port)
    try:
        box.login(user, password)
        box.select(folder)
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


def _mark_seen(creds: Creds, nums: list[bytes]) -> None:
    host, port, user, password, folder = creds
    box = imaplib.IMAP4_SSL(host, port)
    try:
        box.login(user, password)
        box.select(folder)
        for n in nums:
            box.store(n.decode(), "+FLAGS", "\\Seen")
    finally:
        try:
            box.logout()
        except Exception:  # noqa: BLE001
            pass


async def configured() -> bool:
    from app.services import outreach

    if not outreach.enabled():
        return False
    async with session_maker()() as db:
        return await outreach_gmail.imap_credentials(db) is not None


async def poll_once() -> int:
    """Store new replies. Returns how many were kept. A message that fails stays unread and is tried again next time."""
    from app.services import (  # imported here: they import the distribution service
        outreach,
        outreach_agent,
        outreach_inbound,
    )

    if not outreach.enabled():
        return 0
    async with session_maker()() as db:
        creds = await outreach_gmail.imap_credentials(db)
    if creds is None:
        return 0
    try:
        messages = await asyncio.to_thread(_fetch_unseen, creds)
    except Exception as e:  # noqa: BLE001  a wrong or revoked password: say so in the back office instead of failing silently
        log.exception("could not read the outreach mailbox")
        async with session_maker()() as db:
            await outreach_gmail.note_poll(db, "We could not read the inbox. The app password may have been removed: connect again. " + type(e).__name__)
        return 0
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
        await asyncio.to_thread(_mark_seen, creds, done)
    async with session_maker()() as db:
        await outreach_gmail.note_poll(db, "")
    return kept
