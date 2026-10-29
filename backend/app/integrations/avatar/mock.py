import time

from app.config import get_settings
from app.integrations.avatar.base import AvatarPoll, AvatarProvider, AvatarRequest, AvatarResult, Presenter, VoiceOption

WORDS_PER_SECOND = 2.5
MOCK_COST_PER_MINUTE = 1.0


class MockAvatarProvider(AvatarProvider):
    name = "mock"

    def __init__(self, name: str = "mock", green_screen: bool = False) -> None:
        self.name = name  # lets tests play "heygen" / "synthesia" and bill the right vendor budget
        self.green_screen = green_screen

    @property
    def supports_async(self) -> bool:  # type: ignore[override]
        return get_settings().mock_vendor_latency_s > 0

    async def submit(self, req: AvatarRequest) -> str:
        return f"sim-{time.time():.3f}"

    async def poll(self, vendor_id: str, req: AvatarRequest) -> AvatarPoll:
        if time.time() < float(vendor_id.removeprefix("sim-")) + get_settings().mock_vendor_latency_s:
            return AvatarPoll("pending")
        return AvatarPoll("completed", await self.generate(req))

    def _duration(self, req: AvatarRequest) -> float:
        return max(1.0, len(req.script_text.split()) / WORDS_PER_SECOND)

    def estimate_cost(self, req: AvatarRequest) -> float:
        return round(self._duration(req) / 60 * MOCK_COST_PER_MINUTE, 4)

    async def list_voices(self) -> list[VoiceOption]:
        accents = ["nigerian", "ghanaian", "kenyan", "south_african", "british", "american"]
        return [VoiceOption(id=f"mock-{a}", accent=a) for a in accents]

    async def list_presenters(self) -> list[Presenter]:
        return [
            Presenter("stand-in-woman", "Stand-in presenter (woman)", "female", None, "landscape"),
            Presenter("stand-in-man", "Stand-in presenter (man)", "male", None, "landscape"),
        ]

    async def generate(self, req: AvatarRequest) -> AvatarResult:
        d = self._duration(req)
        return AvatarResult(
            video_url="mock://green.mp4"
            if self.green_screen
            else ("mock://anchor.webm" if req.transparent else "mock://anchor.mp4"),
            duration_s=d,
            cost=self.estimate_cost(req),
            vendor_video_id="mock-video",
            needs_chroma_key=self.green_screen,
        )
