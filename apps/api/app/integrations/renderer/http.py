import httpx

from app.config import get_settings
from app.integrations.renderer.base import Analysis, RendererClient, RenderRequest, RenderStatus

COST_PER_OUTPUT = 0.05  # placeholder until docs/render-benchmarks.md has measured numbers


class HttpRenderer(RendererClient):
    def __init__(self) -> None:
        s = get_settings()
        self._client = httpx.AsyncClient(
            base_url=s.renderer_url, headers={"x-renderer-secret": s.renderer_shared_secret}, timeout=30
        )

    def estimate_cost(self, req: RenderRequest) -> float:
        return COST_PER_OUTPUT * len(req.outputs)

    async def analyze(self, url: str) -> Analysis:
        r = await self._client.post("/analyze", json={"url": url}, timeout=300)
        r.raise_for_status()
        d = r.json()
        return Analysis(
            duration_s=d["duration_s"],
            has_audio=d["has_audio"],
            video_duration_s=d.get("video_duration_s"),
            audio_duration_s=d.get("audio_duration_s"),
            loudness_lufs=d.get("loudness_lufs"),
            true_peak_db=d.get("true_peak_db"),
        )

    async def submit(self, req: RenderRequest) -> str:
        r = await self._client.post(
            "/renders",
            json={
                "composition": req.composition,
                "props": req.props,
                "outputs": req.outputs,
                "input_urls": req.input_urls,
                "output_prefix": req.output_prefix,
            },
        )
        r.raise_for_status()
        return r.json()["render_id"]

    async def status(self, render_id: str) -> RenderStatus:
        r = await self._client.get(f"/renders/{render_id}")
        r.raise_for_status()
        d = r.json()
        return RenderStatus(d["status"], d.get("progress", 0), d.get("output_keys", []), d.get("error"))
