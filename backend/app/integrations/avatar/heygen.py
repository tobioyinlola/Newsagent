"""HeyGen v3 client for Option B (transparent WebM).

Per the build spec: POST /v3/videos with type "avatar" and output_format "webm"; do not send a
background object with webm; poll GET /v3/videos/{id} until completed. Request body fields
beyond those named in the spec are UNVERIFIED against the live API; confirm in the anchor spike.
"""

import asyncio

import httpx

from app.config import VENDOR_POLICIES, get_settings
from app.integrations.avatar.base import AvatarPoll, AvatarProvider, AvatarRequest, AvatarResult, VoiceOption

BASE = "https://api.heygen.com"
# Placeholder pricing, replace with the measured per-minute cost from the spike.
ASSUMED_COST_PER_MINUTE = 1.0


class HeyGenProvider(AvatarProvider):
    name = "heygen"

    def __init__(self) -> None:
        self._headers = {"x-api-key": get_settings().heygen_api_key}
        self._policy = VENDOR_POLICIES["avatar"]

    def estimate_cost(self, req: AvatarRequest) -> float:
        minutes = max(1, len(req.script_text.split())) / 2.5 / 60
        return round(minutes * ASSUMED_COST_PER_MINUTE, 4)

    async def list_voices(self) -> list[VoiceOption]:
        async with httpx.AsyncClient(base_url=BASE, headers=self._headers, timeout=30) as c:
            r = await c.get("/v3/voices")  # verified live: paginated ({data, has_more, next_token})
            r.raise_for_status()
            items = r.json().get("data", [])
        return [
            VoiceOption(
                id=v["voice_id"],
                accent=v.get("accent") or v.get("language", ""),
                preview_url=v.get("preview_audio_url") or v.get("preview"),
            )
            for v in items
        ]

    supports_async = True

    async def submit(self, req: AvatarRequest) -> str:
        avatar_id = req.avatar_id or get_settings().heygen_avatar_id
        if not avatar_id:
            raise RuntimeError("No presenter is set: put your custom presenter's HeyGen id in HEYGEN_AVATAR_ID.")
        body: dict = {"type": "avatar", "avatar_id": avatar_id, "script": req.script_text}
        voice_id = req.voice_id or get_settings().heygen_voice_id
        if voice_id:
            body["voice_id"] = voice_id  # field name unverified against the live API: confirm on the first real run
        if req.transparent:
            body["output_format"] = "webm"  # never send "background" with webm
        async with httpx.AsyncClient(base_url=BASE, headers=self._headers, timeout=30) as c:
            r = await c.post("/v3/videos", json=body)
            r.raise_for_status()
            return r.json()["data"]["video_id"]

    async def poll(self, vendor_id: str, req: AvatarRequest) -> AvatarPoll:
        async with httpx.AsyncClient(base_url=BASE, headers=self._headers, timeout=30) as c:
            s = await c.get(f"/v3/videos/{vendor_id}")
            s.raise_for_status()
            data = s.json()["data"]
        if data["status"] == "completed":
            dur = float(data.get("duration", 0))
            return AvatarPoll(
                "completed",
                AvatarResult(
                    video_url=data["video_url"],
                    duration_s=dur,
                    cost=round(dur / 60 * ASSUMED_COST_PER_MINUTE, 4),
                    vendor_video_id=vendor_id,
                ),
            )
        if data["status"] == "failed":
            return AvatarPoll("failed", error=str(data.get("error"))[:300])
        return AvatarPoll("pending")

    async def generate(self, req: AvatarRequest) -> AvatarResult:
        """Submit and wait, for callers that don't track the vendor id themselves (the pipeline uses submit/poll)."""
        vid = await self.submit(req)
        elapsed = 0.0
        while elapsed < self._policy.timeout_s:
            p = await self.poll(vid, req)
            if p.status == "completed" and p.result:
                return p.result
            if p.status == "failed":
                raise RuntimeError(f"HeyGen failed: {p.error}")
            await asyncio.sleep(5)
            elapsed += 5
        raise TimeoutError("HeyGen render timed out")
