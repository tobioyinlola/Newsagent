from app.integrations.broll.base import BrollProvider, BrollResult

PLACEHOLDER_MP4 = b"\x00\x00\x00\x18ftypmp42MOCK-BROLL-NOT-A-REAL-VIDEO"


class MockBrollProvider(BrollProvider):
    """Local runs and tests: returns a placeholder, never a real generated clip."""

    name = "mock"

    def __init__(self) -> None:
        self.calls: list[tuple[str, float]] = []

    def estimate_cost(self, prompt: str, seconds: float) -> float:
        return round(seconds * 0.02, 4)

    async def generate(self, prompt: str, seconds: float) -> BrollResult:
        self.calls.append((prompt, seconds))
        return BrollResult(PLACEHOLDER_MP4, "video/mp4", seconds, self.estimate_cost(prompt, seconds))
