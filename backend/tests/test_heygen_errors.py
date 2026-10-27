import httpx
import pytest

from app.integrations.avatar.base import AvatarRequest
from app.integrations.avatar.heygen import HeyGenProvider
from app.integrations.errors import ProviderError


async def test_a_refused_video_keeps_heygens_reason(monkeypatch):
    def handler(request):
        return httpx.Response(
            400, json={"error": {"code": "invalid_parameter", "message": "avatar does not support webm"}}
        )

    real = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(handler), **kw))
    req = AvatarRequest(script_text="Hello   there\n world", avatar_id="a1", voice_accent="en", transparent=True)
    with pytest.raises(ProviderError) as e:
        await HeyGenProvider().submit(req)
    assert e.value.category == "invalid_input" and "avatar does not support webm" in e.value.user_message
