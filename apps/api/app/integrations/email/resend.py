import httpx

from app.config import VENDOR_POLICIES, get_settings
from app.integrations.email.base import EmailProvider


class ResendEmail(EmailProvider):
    """Transactional email via Resend (https://resend.com/docs/api-reference/emails/send-email)."""

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        s = get_settings()
        self._from = s.email_from
        self._client = client or httpx.AsyncClient(
            base_url="https://api.resend.com",
            headers={"Authorization": f"Bearer {s.email_api_key}"},
            timeout=VENDOR_POLICIES["email"].timeout_s,
        )

    async def send(self, to: str, subject: str, text: str, html: str | None = None) -> None:
        body: dict = {"from": self._from, "to": [to], "subject": subject, "text": text}
        if html:
            body["html"] = html
        r = await self._client.post("/emails", json=body)
        r.raise_for_status()
