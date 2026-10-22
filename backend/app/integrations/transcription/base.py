from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class Transcript:
    text: str
    srt: str
    has_speech: bool


class TranscriptionProvider(ABC):
    @abstractmethod
    async def transcribe(self, media_url: str) -> Transcript: ...
