"""Synthesia client: the secondary avatar provider (build spec section 9).

Synthesia does not output transparent video; it renders on a `green_screen` background, which the renderer keys
out (`RendererClient.chroma_key`). UNVERIFIED against the live API: endpoint paths, field names, statuses and the exact
green are from the public docs as remembered. Confirm in a spike before relying on it.
"""

import asyncio

import httpx

from app.config import VENDOR_POLICIES, get_settings
from app.integrations.avatar.base import AvatarProvider, AvatarRequest, AvatarResult, VoiceOption

BASE = "https://api.synthesia.io"
ASSUMED_COST_PER_MINUTE = 1.0  # placeholder until measured
KEYING_COST = 0.01  # the renderer's chroma-key pass, folded into this provider's estimate
DEFAULT_AVATAR = "anna_costume1_cameraA"  # placeholder id; set the real one per project/anchor


class SynthesiaProvider(AvatarProvider):
    name = "synthesia"

    def __init__(self, client: httpx.AsyncClient | None = None) -> None:
        self._client = client or httpx.AsyncClient(
            base_url=BASE, headers={"Authorization": get_settings().synthesia_api_key}, timeout=30
        )
        self._policy = VENDOR_POLICIES["avatar"]

    def estimate_cost(self, req: AvatarRequest) -> float:
        minutes = max(1, len(req.script_text.split())) / 2.5 / 60
        return round(minutes * ASSUMED_COST_PER_MINUTE + KEYING_COST, 4)

    async def list_voices(self) -> list[VoiceOption]:
        return []  # voice is part of the avatar choice in Synthesia; accents are not selectable separately

    async def generate(self, req: AvatarRequest) -> AvatarResult:
        body = {
            "test": False,
            "title": "newsagent anchor",
            "input": [
                {"scriptText": req.script_text, "avatar": req.avatar_id or DEFAULT_AVATAR, "background": "green_screen"}
            ],
        }
        r = await self._client.post("/v2/videos", json=body)
        r.raise_for_status()
        vid = r.json()["id"]
        waited = 0.0
        while waited < self._policy.timeout_s:
            s = await self._client.get(f"/v2/videos/{vid}")
            s.raise_for_status()
            d = s.json()
            if d["status"] == "complete":
                dur = float(d.get("duration") or 0)
                return AvatarResult(
                    video_url=d["download"],
                    duration_s=dur,
                    cost=round(dur / 60 * ASSUMED_COST_PER_MINUTE + KEYING_COST, 4),
                    vendor_video_id=vid,
                    needs_chroma_key=True,
                )
            if d["status"] in {"failed", "rejected"}:
                raise RuntimeError(f"Synthesia {d['status']}: {d.get('error', '')}")
            await asyncio.sleep(5)
            waited += 5
        raise TimeoutError("Synthesia render timed out")
