import asyncio
import smtplib
from email.message import EmailMessage

from app.config import get_settings
from app.integrations.email.base import EmailProvider


class SmtpEmail(EmailProvider):
    """SMTP delivery (Mailpit locally). The production transactional vendor is a Decision needed."""

    def __init__(self, host: str = "localhost", port: int = 1025) -> None:
        self.host, self.port = host, port

    async def send(self, to: str, subject: str, text: str, html: str | None = None) -> None:
        msg = EmailMessage()
        msg["From"], msg["To"], msg["Subject"] = get_settings().email_from, to, subject
        msg.set_content(text)
        if html:
            msg.add_alternative(html, subtype="html")

        def _send() -> None:
            with smtplib.SMTP(self.host, self.port) as s:
                s.send_message(msg)

        await asyncio.to_thread(_send)
