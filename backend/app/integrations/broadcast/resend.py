import logging
from urllib.parse import quote

import httpx

from app.config import VENDOR_POLICIES, get_settings
from app.integrations.broadcast.base import BroadcastProvider
from app.integrations.email import resend as sender

log = logging.getLogger("resend.broadcast")


class ResendBroadcast(BroadcastProvider):
    """Resend Contacts, Segments and Broadcasts (https://resend.com/docs/api-reference/broadcasts/create-broadcast)."""

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        s = get_settings()
        self._from, self._reply_to = s.email_from, s.email_reply_to
        self._headers = {"Authorization": f"Bearer {s.email_api_key}"}
        self._injected = client

    async def _call(self, method: str, path: str, body: dict | None = None, *, ok_4xx: bool = False) -> dict:
        attempts = VENDOR_POLICIES["email"].max_attempts
        for attempt in range(1, attempts + 1):
            await sender._pace()  # Resend allows only a few API calls a second
            try:
                if self._injected is not None:
                    r = await self._injected.request(method, path, json=body)
                else:
                    async with httpx.AsyncClient(
                        base_url="https://api.resend.com", headers=self._headers, timeout=VENDOR_POLICIES["email"].timeout_s
                    ) as c:
                        r = await c.request(method, path, json=body)
            except (httpx.TransportError, httpx.TimeoutException):
                if attempt == attempts:
                    raise
                await sender._sleep(sender._backoff(attempt, None))
                continue
            if (r.status_code == 429 or r.status_code >= 500) and attempt < attempts:
                await sender._sleep(sender._backoff(attempt, r.headers.get("retry-after")))
                continue
            if r.status_code >= 400:
                log.error("resend %s %s refused (%s): %s", method, path.split("?")[0], r.status_code, r.text[:300])
                if ok_4xx and r.status_code < 500 and r.status_code != 429:
                    return {}
            r.raise_for_status()
            try:
                return r.json() if r.content else {}
            except ValueError:
                return {}
        return {}

    async def ensure_segment(self, name: str) -> str:
        data = await self._call("POST", "/segments", {"name": name})
        sid = str(data.get("id") or "")
        if not sid:
            raise RuntimeError("Resend did not return a segment id")
        return sid

    async def add_contact(self, email: str, first_name: str, segment_id: str) -> None:
        body = {"email": email, "unsubscribed": False}
        if first_name:
            body["first_name"] = first_name
        # a contact that already exists answers with an error that is fine to pass over; their unsubscribe is never touched
        await self._call("POST", "/contacts", body, ok_4xx=True)
        await self._call("POST", f"/contacts/{quote(email, safe='')}/segments/{quote(segment_id, safe='')}")

    async def remove_contact(self, email: str, segment_id: str) -> None:
        await self._call("DELETE", f"/contacts/{quote(email, safe='')}/segments/{quote(segment_id, safe='')}", ok_4xx=True)

    async def send(self, segment_id: str, name: str, subject: str, html: str, text: str) -> str:
        body: dict = {
            "segment_id": segment_id,
            "from": self._from,
            "name": name[:120],
            "subject": subject,
            "html": html,
            "text": text,
            "send": True,
        }
        if self._reply_to:
            body["reply_to"] = self._reply_to
        data = await self._call("POST", "/broadcasts", body)
        bid = str(data.get("id") or "")
        if not bid:
            raise RuntimeError("Resend did not return a broadcast id")
        return bid

    async def status(self, broadcast_id: str) -> str:
        data = await self._call("GET", f"/broadcasts/{quote(broadcast_id, safe='')}")
        return str(data.get("status") or "")


