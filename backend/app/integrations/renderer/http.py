import asyncio
import re
import time
from dataclasses import dataclass, field

import httpx

from app.config import VENDOR_POLICIES, get_settings
from app.integrations.errors import ProviderError
from app.integrations.renderer.base import (
    Analysis,
    KeyResult,
    ProcessRequest,
    ProcessResult,
    RendererClient,
    RenderRequest,
    RenderStatus,
)

COST_PER_OUTPUT = 0.05  # placeholder until docs/render-benchmarks.md has measured numbers


_NAME = re.compile(r"^[A-Za-z0-9_-]+$")
HEALTH_TTL_S = 2.0  # how long one answer from a renderer's /health is trusted when choosing where to send work
DOWN_FOR_S = 30.0  # a renderer that did not answer is left out for this long


def parse_renderer_urls(renderer_urls: str, single_url: str) -> list[tuple[str, str]]:
    """The renderers to use, as (name, url). RENDERER_URLS is a comma separated list, each `url` or `name=url`; unset means the one
    RENDERER_URL, exactly as before. Names go into render ids (`name:id`), so keep them stable when adding or removing renderers."""
    items = [x.strip() for x in (renderer_urls or "").split(",") if x.strip()]
    if not items:
        return [("r1", single_url)]
    out: list[tuple[str, str]] = []
    for i, item in enumerate(items, 1):
        name, _, url = item.partition("=") if "=" in item else (f"r{i}", "", item)
        name, url = name.strip(), url.strip().rstrip("/")
        if not _NAME.match(name) or not url.startswith(("http://", "https://")):
            raise ValueError(f"RENDERER_URLS entry {item!r} is not `url` or `name=url`")
        if name in {n for n, _ in out}:
            raise ValueError(f"RENDERER_URLS names must be different: {name!r} is used twice")
        out.append((name, url))
    return out


@dataclass
class _Instance:
    name: str
    url: str
    client: httpx.AsyncClient
    down_until: float = 0.0
    health: dict = field(default_factory=dict)
    health_at: float = 0.0


class HttpRenderer(RendererClient):
    def __init__(self) -> None:
        s = get_settings()
        headers = {"x-renderer-secret": s.renderer_shared_secret}
        self._instances = [
            _Instance(name, url, httpx.AsyncClient(base_url=url, headers=headers, timeout=30))
            for name, url in parse_renderer_urls(s.renderer_urls, s.renderer_url)
        ]
        self._headers = headers

    # The first renderer is the one the API has always used; tests and single-renderer setups reach it as `_client`.
    @property
    def _client(self) -> httpx.AsyncClient:
        return self._instances[0].client

    @_client.setter
    def _client(self, client: httpx.AsyncClient) -> None:
        self._instances[0].client = client

    def _ref(self, inst: _Instance, render_id: str) -> str:
        """The id the rest of the system holds for a render. With one renderer it is the renderer's own id, unchanged; with several it
        names the renderer (`r2:<id>`) so polling and cancelling reach the one that has the job."""
        return render_id if len(self._instances) == 1 else f"{inst.name}:{render_id}"

    def _split(self, render_id: str) -> tuple[_Instance, str]:
        name, sep, rest = render_id.partition(":")
        if sep:
            for inst in self._instances:
                if inst.name == name:
                    return inst, rest
        return self._instances[0], render_id  # an id from before several renderers were set up belongs to the first

    async def _load(self, inst: _Instance) -> dict | None:
        """The renderer's /health (cached for a moment), or None if it did not answer."""
        now = time.monotonic()
        if inst.down_until > now:
            return None
        if inst.health and now - inst.health_at < HEALTH_TTL_S:
            return inst.health
        try:
            r = await inst.client.get("/health", timeout=3)
            r.raise_for_status()
            inst.health, inst.health_at = r.json(), now
            return inst.health
        except (httpx.HTTPError, ValueError):
            inst.down_until, inst.health = now + DOWN_FOR_S, {}
            return None

    async def _pick(self, kind: str) -> _Instance:
        """Where to send new work. One renderer: that one, with no extra requests. Several: the least busy one that answers
        (`render` = long renders, `quick` = recording clean-up and the like). Quick work prefers the later renderers on a tie, so the
        first one stays free for renders; a renderer that is draining or not answering is left out."""
        if len(self._instances) == 1:
            return self._instances[0]
        scored: list[tuple[int, int, _Instance]] = []
        for i, inst in enumerate(self._instances):
            h = await self._load(inst)
            if h is None or h.get("draining"):
                continue
            lane = h.get("render" if kind == "render" else "quick") or {}
            scored.append(
                (int(lane.get("queued", 0)) * 1000 + int(lane.get("running", 0)), i if kind == "render" else -i, inst)
            )
        if not scored:
            return self._instances[0]  # nothing answered: try the first anyway, so the usual retry rules apply
        return min(scored, key=lambda t: (t[0], t[1]))[2]

    async def _post(
        self, path: str, payload: dict, max_wait_s: float = 900, inst: _Instance | None = None
    ) -> httpx.Response:
        """POST, waiting out 429 'busy' answers (the renderer's queue is full): that is expected under load and must
        not fail a customer's video. Gives up after max_wait_s."""
        waited = 0.0
        client = (inst or self._instances[0]).client
        while True:
            r = await client.post(path, json=payload)
            if r.status_code != 429:
                r.raise_for_status()
                return r
            delay = min(60.0, max(1.0, float(r.headers.get("retry-after", 5))))
            if waited + delay > max_wait_s:
                r.raise_for_status()
            await asyncio.sleep(delay)
            waited += delay

    async def _job(self, render_id: str) -> dict:
        """The renderer's account of one job. It keeps jobs in memory, so after a restart (a deploy) it answers 404: that job is
        gone and must be submitted again, which a retry does. It is not a rejected request."""
        inst, rid = self._split(render_id)
        r = await inst.client.get(f"/renders/{rid}")
        if r.status_code == 404:
            raise ProviderError("The renderer restarted and lost this job", "temporary", retry_after=5)
        r.raise_for_status()
        return r.json()

    async def cancel(self, render_id: str) -> None:
        inst, rid = self._split(render_id)
        try:
            await inst.client.delete(f"/renders/{rid}")
        except httpx.HTTPError:  # best effort: the render then just finishes unused
            pass

    def estimate_cost(self, req: RenderRequest) -> float:
        return COST_PER_OUTPUT * len(req.outputs)

    async def chroma_key(self, url: str, output_key: str) -> KeyResult:
        inst = await self._pick("quick")
        r = await self._post("/chromakey", {"url": url, "output_key": output_key}, inst=inst)
        rid = self._ref(inst, r.json()["render_id"])
        waited = 0.0
        while waited < VENDOR_POLICIES["renderer"].timeout_s:
            st = await self._job(rid)
            if st["status"] == "succeeded":
                return KeyResult(st["result"]["key"], st["result"]["duration_s"])
            if st["status"] == "failed":
                raise RuntimeError(st.get("error") or "chroma key failed")
            await asyncio.sleep(2)
            waited += 2
        raise TimeoutError("chroma key timed out")

    async def process(self, req: ProcessRequest) -> ProcessResult:
        inst = await self._pick("quick")
        r = await self._post(
            "/process",
            {"chunk_urls": req.chunk_urls, "kind": req.kind, "ext": req.ext, "output_prefix": req.output_prefix},
            inst=inst,
        )
        rid = self._ref(inst, r.json()["render_id"])
        waited = 0.0
        while waited < VENDOR_POLICIES["renderer"].timeout_s:
            st = await self._job(rid)
            if st["status"] == "succeeded":
                d = st["result"]
                return ProcessResult(
                    audio_key=d["audio_key"],
                    video_key=d.get("video_key"),
                    duration_s=d["duration_s"],
                    width=d.get("width"),
                    height=d.get("height"),
                    flags=d.get("flags", []),
                    stats=d.get("stats", {}),
                )
            if st["status"] == "failed":
                raise RuntimeError(st.get("error") or "processing failed")
            await asyncio.sleep(2)
            waited += 2
        raise TimeoutError("processing timed out")

    async def analyze(self, url: str) -> Analysis:
        inst = await self._pick("quick")
        r = await inst.client.post("/analyze", json={"url": url}, timeout=300)
        r.raise_for_status()
        d = r.json()
        return Analysis(
            duration_s=d["duration_s"],
            has_audio=d["has_audio"],
            video_duration_s=d.get("video_duration_s"),
            audio_duration_s=d.get("audio_duration_s"),
            loudness_lufs=d.get("loudness_lufs"),
            true_peak_db=d.get("true_peak_db"),
            width=d.get("width"),
            height=d.get("height"),
        )

    async def submit(self, req: RenderRequest) -> str:
        inst = await self._pick("render")
        r = await self._post(
            "/renders",
            {
                "composition": req.composition,
                "props": req.props,
                "outputs": req.outputs,
                "input_urls": req.input_urls,
                "output_prefix": req.output_prefix,
            },
            inst=inst,
        )
        return self._ref(inst, r.json()["render_id"])

    async def status(self, render_id: str) -> RenderStatus:
        d = await self._job(render_id)
        return RenderStatus(d["status"], d.get("progress", 0), d.get("output_keys", []), d.get("error"))
