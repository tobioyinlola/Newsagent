import logging

import httpx

from app.config import VENDOR_POLICIES, get_settings
from app.integrations.email.base import EmailProvider

log = logging.getLogger("resend")


class ResendEmail(EmailProvider):
    """Transactional email via Resend (https://resend.com/docs/api-reference/emails/send-email)."""

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        s = get_settings()
        self._from = s.email_from
        self._headers = {"Authorization": f"Bearer {s.email_api_key}"}
        self._injected = client  # tests; in production each send opens its own client (the background worker runs each task in a new event loop, and a client kept from an earlier loop fails with "Event loop is closed")

    async def send(self, to: str, subject: str, text: str, html: str | None = None) -> None:
        body: dict = {"from": self._from, "to": [to], "subject": subject, "text": text}
        if html:
            body["html"] = html
        if get_settings().email_reply_to:
            body["reply_to"] = get_settings().email_reply_to
        if self._injected is not None:
            r = await self._injected.post("/emails", json=body)
        else:
            async with httpx.AsyncClient(
                base_url="https://api.resend.com", headers=self._headers, timeout=VENDOR_POLICIES["email"].timeout_s
            ) as c:
                r = await c.post("/emails", json=body)
        if (
            r.status_code >= 400
        ):  # Resend says why (unverified domain, restricted key, ...) in the body; the status line alone does not
            log.error("resend refused an email (%s) from %s: %s", r.status_code, self._from, r.text[:400])
        r.raise_for_status()
