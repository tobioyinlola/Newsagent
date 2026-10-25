"""HeyGen v3 client for Option B (transparent WebM).

Per the build spec: POST /v3/videos with type "avatar" and output_format "webm"; do not send a
background object with webm; poll GET /v3/videos/{id} until completed. Request body fields
beyond those named in the spec are UNVERIFIED against the live API; confirm in the anchor spike.
"""

import asyncio

import httpx

from app.config import VENDOR_POLICIES, get_settings
from app.integrations.avatar.base import (
    AvatarPoll,
    AvatarProvider,
    AvatarRequest,
    AvatarResult,
    Presenter,
    VoiceOption,
)

BASE = "https://api.heygen.com"
# Measured once on 2026-10-25: a 3.0 s webm clip took the wallet from $15.00 to $14.88, i.e. about $0.04 per second.
# One sample on the account's default engine; there may be a minimum charge. Re-measure with a longer clip before pricing.
ASSUMED_COST_PER_MINUTE = 2.4


def _gender(v: str | None) -> str:
    """HeyGen labels looks "Woman" / "female" / "Man" / "male" / "Unspecified" inconsistently; offer female | male | ''."""
    v = (v or "").strip().lower()
    return {"woman": "female", "female": "female", "man": "male", "male": "male"}.get(v, "")


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
    MAX_LOOKS = 1200  # the account's catalogue is paged 50 at a time; stop somewhere sensible

    async def list_presenters(self) -> list[Presenter]:
        """The account's avatar looks (live API: `GET /v3/avatars/looks`, 50 per page, `next_token` to continue)."""
        out: list[Presenter] = []
        token: str | None = None
        async with httpx.AsyncClient(base_url=BASE, headers=self._headers, timeout=30) as c:
            while len(out) < self.MAX_LOOKS:
                r = await c.get("/v3/avatars/looks", params={"limit": 50, **({"token": token} if token else {})})
                r.raise_for_status()
                body = r.json()
                for it in body.get("data", []):
                    if it.get("status", "completed") != "completed":
                        continue
                    out.append(
                        Presenter(
                            id=it["id"],
                            name=it.get("name") or it["id"],
                            gender=_gender(it.get("gender")),
                            preview_image_url=it.get("preview_image_url"),
                            orientation=it.get("preferred_orientation"),
                        )
                    )
                token = body.get("next_token")
                if not body.get("has_more") or not token:
                    break
        return out

    async def submit(self, req: AvatarRequest) -> str:
        body: dict = {"type": "avatar", "avatar_id": req.avatar_id, "script": req.script_text}
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
