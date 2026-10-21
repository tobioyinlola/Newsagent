"""Anchor spike, Option B: request a transparent WebM from HeyGen and report the result.

Needs HEYGEN_API_KEY and HEYGEN_AVATAR_ID (an avatar trained with matting; Cinematic Avatar does not
support webm). Run: HEYGEN_API_KEY=... HEYGEN_AVATAR_ID=... uv run --project apps/api python scripts/anchor_spike.py
Prints per-video latency, duration, and whether the output has an alpha channel.
Field names beyond those in the build spec are unverified; adjust after reading the live API reference.
"""
import asyncio
import os
import subprocess
import sys
import time
from pathlib import Path

sys.path.insert(0, str(Path(__file__).resolve().parents[1] / "apps" / "api"))
os.environ.setdefault("USE_MOCKS", "false")

import httpx  # noqa: E402

from app.integrations.avatar.base import AvatarRequest  # noqa: E402
from app.integrations.avatar.heygen import HeyGenProvider  # noqa: E402

SCRIPT = ("Tonight's featured startup builds payment tools for market traders across West Africa. "
          "Here is how they are changing the way small businesses get paid.")


async def main() -> None:
    if not os.environ.get("HEYGEN_API_KEY"):
        sys.exit("HEYGEN_API_KEY is not set; spike not run.")
    provider = HeyGenProvider()
    for i in range(3):
        t = time.monotonic()
        res = await provider.generate(AvatarRequest(
            script_text=SCRIPT, voice_accent="nigerian", avatar_id=os.environ["HEYGEN_AVATAR_ID"], transparent=True))
        wall = time.monotonic() - t
        out = Path(f"anchor-spike-{i}.webm")
        async with httpx.AsyncClient(follow_redirects=True) as c:
            out.write_bytes((await c.get(res.video_url)).content)
        probe = subprocess.run(["ffprobe", "-v", "error", "-show_entries", "stream_tags=alpha_mode:stream=pix_fmt,codec_name",
                                "-of", "default=nw=1", str(out)], capture_output=True, text=True).stdout
        print(f"video {i}: wall={wall:.0f}s media={res.duration_s:.1f}s cost~{res.cost} probe={probe.strip()!r}")


asyncio.run(main())
