"""HeyGen v3 client for Option B (transparent WebM).

Per the build spec: POST /v3/videos with type "avatar" and output_format "webm"; do not send a
background object with webm; poll GET /v3/videos/{id} until completed. Request body fields
beyond those named in the spec are UNVERIFIED against the live API; confirm in the anchor spike.
"""

import asyncio
import logging

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
from app.integrations.errors import ProviderError

log = logging.getLogger("heygen")
_LOOKS: dict[str, dict] = {}
_VOICES: dict[tuple[str, str], str | None] = {}
BASE = "https://api.heygen.com"
# Measured twice on 2026-10-25: 3.0 s cost $0.12 and 3.4 s cost $0.11 (wallet deltas), about $0.03 to $0.04 a second.
# Two short samples on the account's default engine; there may be a minimum charge. Re-measure with a longer clip before pricing.
ASSUMED_COST_PER_MINUTE = 2.1


def _gender(v: str | None) -> str:
    """HeyGen labels looks "Woman" / "female" / "Man" / "male" / "Unspecified" inconsistently; offer female | male | ''."""
    v = (v or "").strip().lower()
    return {"woman": "female", "female": "female", "man": "male", "male": "male"}.get(v, "")


def _detail(r: httpx.Response) -> str:
    """HeyGen's error text from a failed response (shape differs between endpoints), trimmed and without any URLs' tokens."""
    try:
        j = r.json()
    except ValueError:
        return r.text[:300] or "no details"
    e = j.get("error") if isinstance(j, dict) else None
    if isinstance(e, dict):
        msg = e.get("message") or e.get("detail") or e.get("code")
    else:
        msg = e or (j.get("message") if isinstance(j, dict) else None)
    return str(msg or j)[:300]


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

    async def _look(self, c: httpx.AsyncClient, avatar_id: str) -> dict:
        """The look's own record (its default voice and gender), found once and remembered for the life of the process."""
        if avatar_id in _LOOKS:
            return _LOOKS[avatar_id]
        found: dict = {}
        r = await c.get(f"/v3/avatars/looks/{avatar_id}")
        if r.status_code == 200:
            d = r.json()
            found = d.get("data", d) if isinstance(d, dict) else {}
        if not found.get("id") and not found.get(
            "default_voice_id"
        ):  # no single-look endpoint: page through the catalogue
            token: str | None = None
            for _ in range(30):
                r = await c.get("/v3/avatars/looks", params={"limit": 50, **({"token": token} if token else {})})
                r.raise_for_status()
                page = r.json()
                hit = next((it for it in page.get("data", []) if it.get("id") == avatar_id), None)
                if hit:
                    found = hit
                    break
                token = page.get("next_token")
                if not page.get("has_more") or not token:
                    break
        _LOOKS[avatar_id] = found
        return found

    async def _voice_for(self, c: httpx.AsyncClient, avatar_id: str, accent: str) -> str | None:
        """A voice_id the video can use. The look's own default if it has one; otherwise the configured fallback; otherwise an
        English voice of the presenter's gender (British or American to match the project's accent when HeyGen says which)."""
        look = await self._look(c, avatar_id)
        if look.get("default_voice_id"):
            return look["default_voice_id"]
        if get_settings().heygen_default_voice_id:
            return get_settings().heygen_default_voice_id
        gender = _gender(look.get("gender"))
        key = (gender, accent)
        if key in _VOICES:
            return _VOICES[key]
        want_uk = accent.lower() in {"british", "uk", "english"}
        best: tuple[int, str] | None = None
        token: str | None = None
        for _ in range(10):
            r = await c.get("/v3/voices", params={**({"token": token} if token else {})})
            r.raise_for_status()
            page = r.json()
            for v in page.get("data", []):
                lang = str(v.get("language", "")).lower()
                if not lang.startswith("en") or not v.get("voice_id"):
                    continue
                score = 1 + (2 if gender and _gender(v.get("gender")) == gender else 0)
                uk = any(t in lang for t in ("uk", "british", "gb"))
                score += 1 if uk == want_uk else 0
                if best is None or score > best[0]:
                    best = (score, v["voice_id"])
            token = page.get("next_token")
            if not page.get("has_more") or not token:
                break
        _VOICES[key] = best[1] if best else None
        return _VOICES[key]

    async def submit(self, req: AvatarRequest) -> str:
        body: dict = {"type": "avatar", "avatar_id": req.avatar_id, "script": " ".join(req.script_text.split())}
        if req.transparent:
            body["output_format"] = "webm"  # never send "background" with webm
        async with httpx.AsyncClient(base_url=BASE, headers=self._headers, timeout=30) as c:
            if req.avatar_id:
                try:
                    voice = await self._voice_for(c, req.avatar_id, req.voice_accent)
                except httpx.HTTPError:  # the lookup is a convenience; HeyGen still decides whether the video is valid
                    voice = None
                if voice:
                    body["voice_id"] = voice
            r = await c.post("/v3/videos", json=body)
            if r.status_code in (
                400,
                422,
            ):  # keep HeyGen's own reason: the status line alone says nothing about what to fix
                detail = _detail(r)
                log.warning(
                    "heygen refused a video (%s): %s | avatar=%s transparent=%s words=%s",
                    r.status_code,
                    detail,
                    req.avatar_id,
                    req.transparent,
                    len(req.script_text.split()),
                )
                err = ProviderError(f"HeyGen refused the request ({r.status_code}): {detail}", "invalid_input")
                err.user_message = f"The video service refused this request: {detail}"
                raise err
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
