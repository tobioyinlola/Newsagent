from abc import ABC, abstractmethod


class EmailProvider(ABC):
    @abstractmethod
    async def send(
        self,
        to: str,
        subject: str,
        text: str,
        html: str | None = None,
        *,
        reply_to: str | None = None,
        headers: dict[str, str] | None = None,
        cc: list[str] | None = None,
        bcc: list[str] | None = None,
    ) -> None:
        """Send one email. `reply_to` overrides the default reply address; `headers` adds mail headers (Message-ID, In-Reply-To);
        `cc` are copied and visible to the recipient, `bcc` are copied and hidden."""
