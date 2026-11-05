import asyncio
import logging
import random
import threading
import time

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

    async def send(
        self,
        to: str,
        subject: str,
        text: str,
        html: str | None = None,
        *,
        reply_to: str | None = None,
        headers: dict[str, str] | None = None,
    ) -> None:
        body: dict = {"from": self._from, "to": [to], "subject": subject, "text": text}
        if html:
            body["html"] = html
        if reply_to or get_settings().email_reply_to:
            body["reply_to"] = reply_to or get_settings().email_reply_to
        if headers:
            body["headers"] = headers
        attempts = VENDOR_POLICIES["email"].max_attempts
        for attempt in range(1, attempts + 1):
            await (
                _pace()
            )  # a burst (many sign-ups at once) is spread out, so the provider's per-second limit is not hit
            try:
                r = await self._post(body)
            except (httpx.TransportError, httpx.TimeoutException):
                if attempt == attempts:
                    raise
                await _sleep(_backoff(attempt, None))
                continue
            if (
                r.status_code == 429 or r.status_code >= 500
            ):  # rate limited, or the provider is having a moment: try again
                if attempt < attempts:
                    log.warning("resend asked us to wait (%s); attempt %s of %s", r.status_code, attempt, attempts)
                    await _sleep(_backoff(attempt, r.headers.get("retry-after")))
                    continue
            if (
                r.status_code >= 400
            ):  # Resend says why (unverified domain, restricted key, ...) in the body; the status line alone does not
                log.error("resend refused an email (%s) from %s: %s", r.status_code, self._from, r.text[:400])
            r.raise_for_status()
            return

    async def _post(self, body: dict) -> httpx.Response:
        if self._injected is not None:
            return await self._injected.post("/emails", json=body)
        async with httpx.AsyncClient(
            base_url="https://api.resend.com", headers=self._headers, timeout=VENDOR_POLICIES["email"].timeout_s
        ) as c:
            return await c.post("/emails", json=body)


# --- pacing and retries (shared by every send in this process; no event-loop-bound objects, since each task has its own loop) ---
_lock = threading.Lock()
_next_slot = 0.0
_sleep = asyncio.sleep


async def _pace() -> None:
    """Hand out send slots at most EMAIL_MAX_PER_SECOND apart (0 = no pacing)."""
    global _next_slot
    rate = get_settings().email_max_per_second
    if rate <= 0:
        return
    with _lock:
        now = time.monotonic()
        slot = max(now, _next_slot)
        _next_slot = slot + 1.0 / rate
    if slot > now:
        await _sleep(slot - now)


def _backoff(attempt: int, retry_after: str | None) -> float:
    """How long to wait before the next try: the provider's Retry-After if it gave one, else 0.5 s, 1 s, 2 s ... with jitter, at most 10 s."""
    try:
        if retry_after:
            return min(10.0, max(0.5, float(retry_after)))
    except ValueError:
        pass
    return min(10.0, 0.5 * 2 ** (attempt - 1)) * random.uniform(0.8, 1.4)  # noqa: S311 (spreading retries, not security)
