from app.integrations.renderer.base import (
    Analysis,
    KeyResult,
    ProcessRequest,
    ProcessResult,
    RendererClient,
    RenderRequest,
    RenderStatus,
)
from app.integrations.storage.base import StorageProvider

PLACEHOLDER_MP4 = b"\x00\x00\x00\x18ftypmp42PLACEHOLDER-NOT-A-REAL-VIDEO"


class MockRenderer(RendererClient):
    def __init__(self, storage: StorageProvider) -> None:
        self.storage = storage
        self._done: dict[str, list[str]] = {}
        self.duration_s = 0.0  # set from the last request so the mock "renders" the right length
        self.process_duration_s = 4.0  # what a processed founder take measures
        self.process_flags: list[str] = []  # tests set e.g. ["no_speech"] to simulate a bad take
        self.processed: list[ProcessRequest] = []
        self.keyed: list[tuple[str, str]] = []
        self.requests: list[RenderRequest] = []  # every render submitted, for assertions
        self.analysis_override: Analysis | None = None  # tests inject bad media

    def estimate_cost(self, req: RenderRequest) -> float:
        return 0.05 * len(req.outputs)

    async def chroma_key(self, url: str, output_key: str) -> KeyResult:
        self.keyed.append((url, output_key))
        await self.storage.put(output_key, b"mock-keyed-anchor", "video/webm")
        return KeyResult(output_key, 3.0)

    async def process(self, req: ProcessRequest) -> ProcessResult:
        vkey = f"{req.output_prefix}/answer.mp4" if req.kind == "video" else None
        akey = f"{req.output_prefix}/answer.mp3"
        if vkey:
            await self.storage.put(vkey, PLACEHOLDER_MP4, "video/mp4")
        await self.storage.put(akey, b"mock-audio", "audio/mpeg")
        self.processed.append(req)
        return ProcessResult(
            audio_key=akey,
            video_key=vkey,
            duration_s=self.process_duration_s,
            width=720,
            height=1280,
            flags=list(self.process_flags),
            stats={"speech_s": self.process_duration_s},
        )

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
        self.requests.append(req)
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
