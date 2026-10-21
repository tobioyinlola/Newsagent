from abc import ABC, abstractmethod
from dataclasses import dataclass, field


@dataclass
class RenderRequest:
    composition: str
    props: dict
    outputs: list[dict]  # [{format, width, height}]
    input_urls: dict[str, str]
    output_prefix: str


@dataclass
class RenderStatus:
    status: str  # queued | running | succeeded | failed
    progress: float = 0.0
    output_keys: list[str] = field(default_factory=list)
    error: str | None = None


@dataclass
class Analysis:
    duration_s: float
    has_audio: bool
    video_duration_s: float | None = None
    audio_duration_s: float | None = None
    loudness_lufs: float | None = None
    true_peak_db: float | None = None


class RendererClient(ABC):
    @abstractmethod
    async def analyze(self, url: str) -> Analysis:
        """Measure a rendered file (duration, audio, loudness) for the quality gate."""

    @abstractmethod
    def estimate_cost(self, req: RenderRequest) -> float: ...

    @abstractmethod
    async def submit(self, req: RenderRequest) -> str: ...

    @abstractmethod
    async def status(self, render_id: str) -> RenderStatus: ...
