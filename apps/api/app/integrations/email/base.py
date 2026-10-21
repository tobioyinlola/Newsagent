from abc import ABC, abstractmethod


class EmailProvider(ABC):
    @abstractmethod
    async def send(self, to: str, subject: str, text: str, html: str | None = None) -> None: ...
