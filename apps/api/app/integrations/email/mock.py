from app.integrations.email.base import EmailProvider


class MockEmail(EmailProvider):
    """Records messages in memory. Local dev may use SmtpEmail against Mailpit instead."""

    def __init__(self) -> None:
        self.sent: list[dict] = []

    async def send(self, to: str, subject: str, text: str, html: str | None = None) -> None:
        self.sent.append({"to": to, "subject": subject, "text": text})
