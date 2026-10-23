from abc import ABC, abstractmethod


class TTSProvider(ABC):
    """Text to speech for the AI interviewer's voice."""

    @abstractmethod
    def estimate_cost(self, text: str) -> float: ...

    @abstractmethod
    async def synthesize(self, text: str) -> bytes | None:
        """MP3 bytes, or None when this provider has no audio (the browser then uses its own voice)."""
