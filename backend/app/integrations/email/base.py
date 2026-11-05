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
    ) -> None:
        """Send one email. `reply_to` overrides the default reply address; `headers` adds mail headers (Message-ID, In-Reply-To)."""
