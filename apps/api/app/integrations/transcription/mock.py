from app.integrations.transcription.base import Transcript, TranscriptionProvider


class MockTranscription(TranscriptionProvider):
    async def transcribe(self, media_url: str) -> Transcript:
        return Transcript("mock transcript", "1\n00:00:00,000 --> 00:00:02,000\nmock transcript\n", True)
