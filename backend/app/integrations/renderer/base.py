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
    width: int | None = None
    height: int | None = None


@dataclass
class ProcessRequest:
    chunk_urls: list[str]
    kind: str  # video | audio
    ext: str
    output_prefix: str


@dataclass
class ProcessResult:
    audio_key: str
    duration_s: float
    video_key: str | None = None
    width: int | None = None
    height: int | None = None
    flags: list[str] = field(default_factory=list)
    stats: dict = field(default_factory=dict)


@dataclass
class KeyResult:
    key: str
    duration_s: float


class RendererClient(ABC):
    @abstractmethod
    async def chroma_key(self, url: str, output_key: str) -> KeyResult:
        """Turn a green-screen video into a transparent WebM stored at output_key."""

    @abstractmethod
    async def process(self, req: ProcessRequest) -> ProcessResult:
        """Join uploaded chunks, clean up and trim the audio, flag problems, write results to storage."""

    @abstractmethod
    async def analyze(self, url: str) -> Analysis:
        """Measure a rendered file (duration, audio, loudness) for the quality gate."""

    @abstractmethod
    def estimate_cost(self, req: RenderRequest) -> float: ...

    @abstractmethod
    async def submit(self, req: RenderRequest) -> str: ...

    @abstractmethod
    async def status(self, render_id: str) -> RenderStatus: ...
