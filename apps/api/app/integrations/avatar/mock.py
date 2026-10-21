from app.integrations.avatar.base import AvatarProvider, AvatarRequest, AvatarResult, VoiceOption

WORDS_PER_SECOND = 2.5
MOCK_COST_PER_MINUTE = 1.0


class MockAvatarProvider(AvatarProvider):
    name = "mock"

    def _duration(self, req: AvatarRequest) -> float:
        return max(1.0, len(req.script_text.split()) / WORDS_PER_SECOND)

    def estimate_cost(self, req: AvatarRequest) -> float:
        return round(self._duration(req) / 60 * MOCK_COST_PER_MINUTE, 4)

    async def list_voices(self) -> list[VoiceOption]:
        accents = ["nigerian", "ghanaian", "kenyan", "south_african", "british", "american"]
        return [VoiceOption(id=f"mock-{a}", accent=a) for a in accents]

    async def generate(self, req: AvatarRequest) -> AvatarResult:
        d = self._duration(req)
        return AvatarResult(
            video_url="mock://anchor.webm" if req.transparent else "mock://anchor.mp4",
            duration_s=d,
            cost=self.estimate_cost(req),
            vendor_video_id="mock-video",
        )
