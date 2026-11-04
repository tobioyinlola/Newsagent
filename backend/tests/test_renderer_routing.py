"""Several renderers: new work goes to the least busy one that answers, and a render stays with the renderer that has it."""

import httpx
import pytest

from app.config import get_settings
from app.integrations.renderer.base import ProcessRequest, RenderRequest
from app.integrations.renderer.http import HttpRenderer, parse_renderer_urls


def test_the_renderer_list_is_read_from_the_settings():
    assert parse_renderer_urls("", "http://localhost:4000") == [("r1", "http://localhost:4000")]  # unset: as before
    assert parse_renderer_urls("http://a:4000, http://b:4000/", "x") == [
        ("r1", "http://a:4000"),
        ("r2", "http://b:4000"),
    ]
    assert parse_renderer_urls("main=http://a, r2=http://b", "x") == [("main", "http://a"), ("r2", "http://b")]
    for bad in ("a=b", "x=http://a,x=http://b", "bad name=http://a", "ftp://a"):
        with pytest.raises(ValueError):
            parse_renderer_urls(bad, "x")


class Fake:
    """A pretend renderer: answers /health with the load it is given and records the calls it gets."""

    def __init__(self, name, render=(0, 0), quick=(0, 0), draining=False, healthy=True):
        self.name, self.calls, self.healthy = name, [], healthy
        self.render, self.quick, self.draining = render, quick, draining

    def handler(self, req: httpx.Request) -> httpx.Response:
        self.calls.append((req.method, req.url.path))
        if req.url.path == "/health":
            if not self.healthy:
                return httpx.Response(500)
            return httpx.Response(
                200,
                json={
                    "status": "ok",
                    "draining": self.draining,
                    "render": {"queued": self.render[0], "running": self.render[1]},
                    "quick": {"queued": self.quick[0], "running": self.quick[1]},
                },
            )
        if req.method == "POST":
            return httpx.Response(202, json={"render_id": f"{self.name}-job"})
        if req.method == "DELETE":
            return httpx.Response(200, json={})
        return httpx.Response(
            200,
            json={
                "status": "succeeded",
                "progress": 1,
                "output_keys": ["k"],
                "result": {"audio_key": "a.m4a", "duration_s": 1.0},
            },
        )


def build(monkeypatch, *fakes: Fake) -> HttpRenderer:
    monkeypatch.setattr(get_settings(), "renderer_urls", ",".join(f"{f.name}=http://{f.name}" for f in fakes))
    r = HttpRenderer()
    for inst, f in zip(r._instances, fakes, strict=True):
        inst.client = httpx.AsyncClient(base_url=f"http://{f.name}", transport=httpx.MockTransport(f.handler))
    return r


REQ = RenderRequest(composition="NewsStudio", props={}, outputs=[], input_urls={}, output_prefix="p")


async def test_one_renderer_behaves_exactly_as_before(monkeypatch):
    monkeypatch.setattr(get_settings(), "renderer_urls", "")
    f = Fake("only")
    r = HttpRenderer()
    r._client = httpx.AsyncClient(base_url="http://only", transport=httpx.MockTransport(f.handler))
    rid = await r.submit(REQ)
    assert rid == "only-job"  # the renderer's own id, no prefix
    assert ("GET", "/health") not in f.calls  # and no extra requests
    await r.status(rid)
    await r.cancel(rid)
    assert [c for c in f.calls if c[0] != "POST"] == [("GET", "/renders/only-job"), ("DELETE", "/renders/only-job")]


async def test_a_render_goes_to_the_least_busy_renderer_and_stays_with_it(monkeypatch):
    a, b = Fake("a", render=(1, 1)), Fake("b", render=(0, 1))
    r = build(monkeypatch, a, b)
    rid = await r.submit(REQ)
    assert rid == "b:b-job"  # b had the shorter line
    assert ("POST", "/renders") in b.calls and ("POST", "/renders") not in a.calls
    await r.status(rid)
    await r.cancel(rid)
    assert ("GET", "/renders/b-job") in b.calls and ("DELETE", "/renders/b-job") in b.calls
    assert not any(p.startswith("/renders/") for _, p in a.calls)  # a was never asked about it
    old = await r.status("legacy-id-from-before")  # an id with no renderer named belongs to the first renderer
    assert old.status == "succeeded" and ("GET", "/renders/legacy-id-from-before") in a.calls


async def test_a_renderer_that_is_down_or_draining_is_left_out(monkeypatch):
    a, b, c = Fake("a", healthy=False), Fake("b", render=(5, 1)), Fake("c", draining=True)
    r = build(monkeypatch, a, b, c)
    assert (await r.submit(REQ)) == "b:b-job"  # a is down and c is restarting, though b is busier than either would be
    health_a = sum(1 for call in a.calls if call[1] == "/health")
    await r.submit(REQ)
    assert (
        sum(1 for call in a.calls if call[1] == "/health") == health_a
    )  # a down renderer is not asked again straight away

    everyone_down = build(monkeypatch, Fake("a", healthy=False), Fake("b", healthy=False))
    assert (
        await everyone_down.submit(REQ)
    ) == "a:a-job"  # nothing answered: the first is tried, as it would be on its own


async def test_load_is_not_asked_for_on_every_render(monkeypatch):
    a, b = Fake("a"), Fake("b")
    r = build(monkeypatch, a, b)
    await r.submit(REQ)
    await r.submit(REQ)
    assert sum(1 for c in a.calls if c[1] == "/health") == 1 and sum(1 for c in b.calls if c[1] == "/health") == 1


async def test_quick_work_prefers_the_later_renderer_so_the_first_stays_free_for_renders(monkeypatch):
    a, b = Fake("a"), Fake("b")
    r = build(monkeypatch, a, b)
    res = await r.process(ProcessRequest(chunk_urls=["u"], kind="video", ext="webm", output_prefix="p"))
    assert res is not None
    assert ("POST", "/process") in b.calls and ("POST", "/process") not in a.calls
    a2, b2 = Fake("a"), Fake("b", quick=(3, 2))
    await build(monkeypatch, a2, b2).process(
        ProcessRequest(chunk_urls=["u"], kind="video", ext="webm", output_prefix="p")
    )
    assert ("POST", "/process") in a2.calls and ("POST", "/process") not in b2.calls  # b was busy, so a took it
