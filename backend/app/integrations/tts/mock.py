from app.integrations.tts.base import TTSProvider


class MockTTS(TTSProvider):
    """No audio: the dashboard falls back to the browser's built-in voice, so the interview works locally with no keys."""

    def __init__(self) -> None:
        self.calls: list[str] = []

    def estimate_cost(self, text: str) -> float:
        return 0.001

    async def synthesize(self, text: str) -> bytes | None:
        self.calls.append(text)
        return None
