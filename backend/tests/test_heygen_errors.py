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


async def test_a_look_without_a_voice_gets_a_matching_english_one(monkeypatch):
    import json

    from app.integrations.avatar import heygen

    heygen._LOOKS.clear()
    heygen._VOICES.clear()
    sent = {}

    def handler(request):
        p = request.url.path
        if p == "/v3/avatars/looks/look1":
            return httpx.Response(200, json={"data": {"id": "look1", "gender": "Man", "default_voice_id": None}})
        if p == "/v3/voices":
            return httpx.Response(
                200,
                json={
                    "data": [
                        {"voice_id": "fr", "language": "French", "gender": "male"},
                        {"voice_id": "f-uk", "language": "English (UK)", "gender": "female"},
                        {"voice_id": "m-us", "language": "English (US)", "gender": "male"},
                        {"voice_id": "m-uk", "language": "English (UK)", "gender": "male"},
                    ],
                    "has_more": False,
                },
            )
        sent.update(json.loads(request.content))
        return httpx.Response(200, json={"data": {"video_id": "v1"}})

    real = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(handler), **kw))
    req = AvatarRequest(script_text="Hi", avatar_id="look1", voice_accent="british", transparent=True)
    assert await HeyGenProvider().submit(req) == "v1"
    assert sent["voice_id"] == "m-uk"


def test_a_look_with_no_gender_field_is_read_from_its_name():
    from app.integrations.avatar.heygen import _look_gender

    assert _look_gender({"name": "CF News Desk Anchor - man (sample)"}) == "male"
    assert _look_gender({"name": "Studio Woman 2"}) == "female"
    assert _look_gender({"name": "Dante"}) == "male"  # unknown: the house presenter is a man
    assert _look_gender({"name": "Dante", "gender": "female"}) == "female"
