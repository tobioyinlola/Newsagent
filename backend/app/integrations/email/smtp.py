import asyncio
import smtplib
from email.message import EmailMessage

from app.config import get_settings
from app.integrations.email.base import EmailProvider


class SmtpEmail(EmailProvider):
    """SMTP delivery: Mailpit locally, or a real mailbox (Gmail / Google Workspace with an app password) with login and STARTTLS."""

    def __init__(
        self,
        host: str = "localhost",
        port: int = 1025,
        user: str = "",
        password: str = "",
        starttls: bool = False,
        sender: str | None = None,
    ) -> None:
        self.host, self.port, self.user, self.password, self.starttls, self.sender = (
            host,
            port,
            user,
            password,
            starttls,
            sender,
        )

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
        msg = EmailMessage()
        msg["From"], msg["To"], msg["Subject"] = self.sender or get_settings().email_from, to, subject
        if reply_to:
            msg["Reply-To"] = reply_to
        for name, value in (headers or {}).items():
            msg[name] = value
        msg.set_content(text)
        if html:
            msg.add_alternative(html, subtype="html")

        def _send() -> None:
            with smtplib.SMTP(self.host, self.port, timeout=30) as s:
                if self.starttls:
                    s.starttls()
                if self.user:
                    s.login(self.user, self.password)
                s.send_message(msg)

        await asyncio.to_thread(_send)
