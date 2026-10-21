from app.integrations.renderer.base import Analysis, RendererClient, RenderRequest, RenderStatus
from app.integrations.storage.base import StorageProvider

PLACEHOLDER_MP4 = b"\x00\x00\x00\x18ftypmp42PLACEHOLDER-NOT-A-REAL-VIDEO"


class MockRenderer(RendererClient):
    def __init__(self, storage: StorageProvider) -> None:
        self.storage = storage
        self._done: dict[str, list[str]] = {}
        self.duration_s = 0.0  # set from the last request so the mock "renders" the right length
        self.analysis_override: Analysis | None = None  # tests inject bad media

    def estimate_cost(self, req: RenderRequest) -> float:
        return 0.05 * len(req.outputs)

    async def analyze(self, url: str) -> Analysis:
        return self.analysis_override or Analysis(
            duration_s=self.duration_s,
            has_audio=True,
            video_duration_s=self.duration_s,
            audio_duration_s=self.duration_s,
            loudness_lufs=-16.0,
            true_peak_db=-1.5,
        )

    async def submit(self, req: RenderRequest) -> str:
        self.duration_s = float(req.props.get("anchorDurationSeconds", 0))
        rid = f"mock-{len(self._done) + 1}"
        keys = []
        for o in req.outputs:
            ext = "png" if o.get("kind") == "thumbnail" else "mp4"
            key = f"{req.output_prefix}/{o.get('name') or o['format']}.{ext}"
            await self.storage.put(key, PLACEHOLDER_MP4, "image/png" if ext == "png" else "video/mp4")
            keys.append(key)
        self._done[rid] = keys
        return rid

    async def status(self, render_id: str) -> RenderStatus:
        return RenderStatus("succeeded", 1.0, self._done[render_id])
