"""Speech-to-text through any OpenAI-compatible `/audio/transcriptions` endpoint (OpenAI, Groq, self-hosted)."""

import re

import httpx

from app.config import VENDOR_POLICIES, get_settings
from app.integrations.transcription.base import Transcript, TranscriptionProvider

MAX_AUDIO_BYTES = 24 * 1024 * 1024  # most hosted endpoints cap uploads at 25 MB


def srt_to_text(srt: str) -> str:
    lines = [ln.strip() for ln in srt.splitlines() if ln.strip() and not ln.strip().isdigit() and "-->" not in ln]
    return re.sub(r"\s+", " ", " ".join(lines)).strip()


class WhisperApiTranscription(TranscriptionProvider):
    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        s = get_settings()
        self._model = s.transcription_model
        self._client = client or httpx.AsyncClient(
            base_url=s.transcription_api_url.rstrip("/"),
            headers={"Authorization": f"Bearer {s.transcription_api_key}"},
            timeout=VENDOR_POLICIES["transcription"].timeout_s,
        )

    async def transcribe(self, media_url: str) -> Transcript:
        async with httpx.AsyncClient(timeout=60) as dl:
            audio = await dl.get(media_url)
            audio.raise_for_status()
        if len(audio.content) > MAX_AUDIO_BYTES:
            raise ValueError("audio too large to transcribe")
        r = await self._client.post(
            "/audio/transcriptions",
            data={"model": self._model, "response_format": "srt", "language": "en"},
            files={"file": ("answer.mp3", audio.content, "audio/mpeg")},
        )
        r.raise_for_status()
        srt = r.text
        text = srt_to_text(srt)
        return Transcript(text=text, srt=srt if text else "", has_speech=bool(text))
