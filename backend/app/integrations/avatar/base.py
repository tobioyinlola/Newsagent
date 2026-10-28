from abc import ABC, abstractmethod
from dataclasses import dataclass


@dataclass
class AvatarRequest:
    script_text: str
    voice_accent: str
    avatar_id: str | None = None
    pronunciation: dict[str, str] | None = None
    transparent: bool = False  # Option B: transparent WebM for Remotion compositing
    extra: dict | None = (
        None  # vendor-specific request fields for this clip (e.g. an expression setting for the sign-off)
    )


@dataclass
class AvatarResult:
    video_url: str
    duration_s: float
    cost: float  # actual vendor cost in credits (USD)
    vendor_video_id: str
    needs_chroma_key: bool = False  # green-screen output that must be keyed to transparent before compositing


@dataclass
class AvatarPoll:
    status: str  # pending | completed | failed
    result: "AvatarResult | None" = None
    error: str | None = None


@dataclass
class Presenter:
    """One selectable look of a presenter (a person in a setting)."""

    id: str  # what the vendor wants as avatar_id
    name: str
    gender: str = ""
    preview_image_url: str | None = None
    orientation: str | None = None


@dataclass
class VoiceOption:
    id: str
    accent: str
    preview_url: str | None = None


class AvatarProvider(ABC):
    name: str
    # True when the vendor job can be submitted and polled separately. The pipeline then records the vendor's id the
    # moment it is issued, so a crash or retry resumes the same paid video instead of buying another.
    supports_async: bool = False

    async def list_presenters(self) -> list[Presenter]:
        """The looks a customer may pick from. Empty when the vendor has no catalogue to offer."""
        return []

    async def submit(self, req: AvatarRequest) -> str:
        raise NotImplementedError

    async def poll(self, vendor_id: str, req: AvatarRequest) -> AvatarPoll:
        raise NotImplementedError

    @abstractmethod
    def estimate_cost(self, req: AvatarRequest) -> float: ...

    @abstractmethod
    async def list_voices(self) -> list[VoiceOption]: ...

    @abstractmethod
    async def generate(self, req: AvatarRequest) -> AvatarResult:
        """Submit and wait for completion. Raises on vendor failure."""
