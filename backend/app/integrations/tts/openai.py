"""The interviewer's voice through any OpenAI-compatible `/audio/speech` endpoint (OpenAI by default)."""

import httpx

from app.config import VENDOR_POLICIES, get_settings
from app.integrations.tts.base import TTSProvider

# OpenAI's list price for tts-1 is about $15 per million characters; a whole interview is ~1,000 characters.
USD_PER_CHAR = 0.000015
MAX_CHARS = 600


class OpenAITTS(TTSProvider):
    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        s = get_settings()
        self._model, self._voice = s.tts_model, s.tts_voice
        key = s.tts_api_key or s.transcription_api_key
        self._client = client or httpx.AsyncClient(
            base_url=s.tts_api_url.rstrip("/"),
            headers={"Authorization": f"Bearer {key}"},
            timeout=VENDOR_POLICIES["tts"].timeout_s,
        )

    def estimate_cost(self, text: str) -> float:
        return round(min(len(text), MAX_CHARS) * USD_PER_CHAR, 6)

    async def synthesize(self, text: str) -> bytes | None:
        r = await self._client.post(
            "/audio/speech",
            json={"model": self._model, "voice": self._voice, "input": text[:MAX_CHARS], "response_format": "mp3"},
        )
        r.raise_for_status()
        return r.content or None
