import httpx
import pytest

from app.integrations.renderer.base import ProcessRequest
from app.integrations.renderer.http import HttpRenderer
from app.integrations.transcription.whisper_api import WhisperApiTranscription, srt_to_text

SRT = "1\n00:00:00,000 --> 00:00:02,000\nHello from Lagos.\n\n2\n00:00:02,000 --> 00:00:04,000\nWe build tools.\n"


def test_srt_to_text():
    assert srt_to_text(SRT) == "Hello from Lagos. We build tools."
    assert srt_to_text("") == ""


def _download(content=b"audio-bytes"):
    return httpx.AsyncClient(transport=httpx.MockTransport(lambda r: httpx.Response(200, content=content)))


async def test_whisper_api_request_shape_and_result():
    seen = {}

    def api(req: httpx.Request) -> httpx.Response:
        seen["url"], seen["auth"], seen["body"] = str(req.url), req.headers.get("authorization"), req.read()
        return httpx.Response(200, text=SRT)

    client = httpx.AsyncClient(
        base_url="https://api.example.com/v1", headers={"Authorization": "Bearer k"}, transport=httpx.MockTransport(api)
    )
    t = await WhisperApiTranscription(client, _download()).transcribe("https://storage/x.mp3")
    assert seen["url"] == "https://api.example.com/v1/audio/transcriptions" and seen["auth"] == "Bearer k"
    assert b'name="model"' in seen["body"] and b"audio-bytes" in seen["body"] and b"srt" in seen["body"]
    assert t.has_speech and t.text.startswith("Hello from Lagos.")


async def test_whisper_empty_result_means_no_speech():
    client = httpx.AsyncClient(
        base_url="https://x/v1", transport=httpx.MockTransport(lambda r: httpx.Response(200, text=""))
    )
    t = await WhisperApiTranscription(client, _download()).transcribe("https://storage/x.mp3")
    assert not t.has_speech and t.srt == ""


async def test_whisper_rejects_oversized_audio():
    client = httpx.AsyncClient(
        base_url="https://x/v1", transport=httpx.MockTransport(lambda r: httpx.Response(200, text=SRT))
    )
    big = _download(b"x" * (25 * 1024 * 1024))
    with pytest.raises(ValueError, match="too large"):
        await WhisperApiTranscription(client, big).transcribe("https://storage/x.mp3")


async def test_http_renderer_process_polls_until_done(monkeypatch):
    calls = []

    def handler(req: httpx.Request) -> httpx.Response:
        calls.append((req.method, req.url.path))
        if req.method == "POST":
            return httpx.Response(202, json={"render_id": "r1"})
        done = sum(1 for m, _ in calls if m == "GET") >= 2
        if not done:
            return httpx.Response(200, json={"status": "running"})
        return httpx.Response(
            200,
            json={
                "status": "succeeded",
                "result": {
                    "audio_key": "a.mp3",
                    "video_key": "v.mp4",
                    "duration_s": 5.5,
                    "flags": ["dark_video"],
                    "stats": {"speech_s": 4},
                },
            },
        )

    async def no_sleep(_):
        return None

    monkeypatch.setattr("app.integrations.renderer.http.asyncio.sleep", no_sleep)
    r = HttpRenderer()
    r._client = httpx.AsyncClient(base_url="http://renderer", transport=httpx.MockTransport(handler))
    res = await r.process(ProcessRequest(chunk_urls=["u1"], kind="video", ext="webm", output_prefix="p"))
    assert res.video_key == "v.mp4" and res.flags == ["dark_video"] and res.duration_s == 5.5
    assert calls[0] == ("POST", "/process")


async def test_http_renderer_process_surfaces_failure(monkeypatch):
    def handler(req: httpx.Request) -> httpx.Response:
        if req.method == "POST":
            return httpx.Response(202, json={"render_id": "r1"})
        return httpx.Response(200, json={"status": "failed", "error": "chunk download failed: 404"})

    r = HttpRenderer()
    r._client = httpx.AsyncClient(base_url="http://renderer", transport=httpx.MockTransport(handler))
    with pytest.raises(RuntimeError, match="chunk download failed"):
        await r.process(ProcessRequest(chunk_urls=["u1"], kind="video", ext="webm", output_prefix="p"))


async def test_http_renderer_waits_out_429_busy_then_succeeds(monkeypatch):
    from app.integrations.renderer.base import RenderRequest

    sleeps, posts = [], []

    def handler(req: httpx.Request) -> httpx.Response:
        posts.append(1)
        if len(posts) <= 2:
            return httpx.Response(429, headers={"retry-after": "7"}, json={"error": "renderer busy"})
        return httpx.Response(202, json={"render_id": "r9"})

    async def fake_sleep(s):
        sleeps.append(s)

    monkeypatch.setattr("app.integrations.renderer.http.asyncio.sleep", fake_sleep)
    r = HttpRenderer()
    r._client = httpx.AsyncClient(base_url="http://renderer", transport=httpx.MockTransport(handler))
    rid = await r.submit(
        RenderRequest(composition="NewsStudio", props={}, outputs=[], input_urls={}, output_prefix="p")
    )
    assert rid == "r9" and sleeps == [7.0, 7.0] and len(posts) == 3


async def test_http_renderer_gives_up_if_busy_for_too_long(monkeypatch):

    async def fake_sleep(s):
        return None

    monkeypatch.setattr("app.integrations.renderer.http.asyncio.sleep", fake_sleep)
    r = HttpRenderer()
    r._client = httpx.AsyncClient(
        base_url="http://x", transport=httpx.MockTransport(lambda q: httpx.Response(429, headers={"retry-after": "60"}))
    )
    with pytest.raises(httpx.HTTPStatusError):
        await r._post("/renders", {}, max_wait_s=120)
