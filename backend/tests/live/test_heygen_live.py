"""LIVE test against the real HeyGen API. It spends real credit and is skipped unless explicitly enabled:

    HEYGEN_LIVE=1 HEYGEN_API_KEY=... HEYGEN_TEST_AVATAR_ID=... pytest tests/live -q -s

Nothing in the ordinary suite touches HeyGen: those tests use mocks and are labelled as such."""

import asyncio
import os

import pytest

pytestmark = pytest.mark.skipif(
    os.environ.get("HEYGEN_LIVE") != "1" or not os.environ.get("HEYGEN_API_KEY"),
    reason="live HeyGen test: set HEYGEN_LIVE=1, HEYGEN_API_KEY and HEYGEN_TEST_AVATAR_ID",
)


async def test_real_generation_submits_polls_and_returns_a_downloadable_clip():
    from app.config import get_settings
    from app.integrations.avatar.base import AvatarRequest
    from app.integrations.avatar.heygen import HeyGenProvider

    get_settings.cache_clear()
    hg = HeyGenProvider()
    req = AvatarRequest(
        script_text="This is a short test of the newsroom presenter.",
        voice_accent="british",
        avatar_id=os.environ.get("HEYGEN_TEST_AVATAR_ID"),
        transparent=True,
    )
    vid = await hg.submit(req)
    assert vid
    for _ in range(120):  # up to ten minutes
        p = await hg.poll(vid, req)
        if p.status == "completed":
            assert p.result and p.result.video_url.startswith("http") and p.result.duration_s > 0
            print(f"HeyGen video {vid}: {p.result.duration_s}s, cost estimate {p.result.cost}")
            return
        assert p.status != "failed", p.error
        await asyncio.sleep(5)
    pytest.fail("HeyGen did not finish within ten minutes")
