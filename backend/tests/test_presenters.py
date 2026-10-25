"""Choosing an AI presenter, and the HeyGen catalogue adapter (HTTP is mocked: no real HeyGen call)."""

import httpx
import pytest

from app.config import get_settings
from app.integrations.avatar.heygen import HeyGenProvider
from app.services import presenters
from tests.conftest import OWNER
from tests.helpers import BRIEF


@pytest.fixture(autouse=True)
def fresh():
    presenters.reset()
    yield
    presenters.reset()


def look(i, name, gender="male", status="completed"):
    return {
        "id": i,
        "name": name,
        "gender": gender,
        "status": status,
        "preview_image_url": f"https://cdn.test/{i}.jpg",
        "preferred_orientation": "landscape",
    }


def fake_heygen(monkeypatch, pages):
    seen = []

    def handler(req: httpx.Request) -> httpx.Response:
        seen.append(dict(req.url.params))
        n = len(seen) - 1
        return httpx.Response(200, json={"data": pages[n], "has_more": n < len(pages) - 1, "next_token": f"t{n + 1}"})

    real = httpx.AsyncClient
    monkeypatch.setattr(httpx, "AsyncClient", lambda **kw: real(transport=httpx.MockTransport(handler), **kw))
    return seen


async def test_the_heygen_catalogue_is_read_across_pages(monkeypatch):
    seen = fake_heygen(
        monkeypatch,
        [
            [look("a", "Dante Office 1")],
            [look("b", "Aya Studio 2", "Woman"), look("c", "Broken", status="processing")],
        ],
    )
    hg = HeyGenProvider.__new__(HeyGenProvider)
    hg._headers = {"x-api-key": "test"}
    found = await hg.list_presenters()
    assert [p.id for p in found] == ["a", "b"]  # a look still being made is not offered
    assert (
        found[0].gender == "male"
        and found[1].gender == "female"
        and found[1].preview_image_url == "https://cdn.test/b.jpg"
    )
    assert seen[0] == {"limit": "50"} and seen[1] == {"limit": "50", "token": "t1"}  # the API allows 50 per page


async def test_presenters_can_be_searched_and_need_a_sign_in(client, workspace):
    assert (await client.get("/v1/presenters")).status_code == 401
    r = await client.get("/v1/presenters", headers=OWNER)
    assert r.status_code == 200 and [p["id"] for p in r.json()] == ["stand-in-woman", "stand-in-man"]
    assert [p["id"] for p in (await client.get("/v1/presenters?q=WOMAN", headers=OWNER)).json()] == ["stand-in-woman"]
    assert [p["id"] for p in (await client.get("/v1/presenters?gender=male", headers=OWNER)).json()] == ["stand-in-man"]


async def test_a_project_remembers_its_presenter_and_refuses_unknown_ones(client, workspace):
    ok = await client.post("/v1/projects", json={**BRIEF, "anchor_id": "stand-in-man"}, headers=OWNER)
    assert ok.status_code == 200 and ok.json()["anchor_id"] == "stand-in-man"
    bad = await client.post("/v1/projects", json={**BRIEF, "anchor_id": "someone-elses-avatar"}, headers=OWNER)
    assert bad.status_code == 422 and bad.json()["detail"]["error"] == "unknown_presenter"
    none = await client.post("/v1/projects", json=BRIEF, headers=OWNER)
    assert none.status_code == 200 and none.json()["anchor_id"] is None  # demo mode needs no presenter


async def test_a_real_run_without_a_presenter_is_refused_not_sent_to_the_vendor(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "use_mocks", False)
    monkeypatch.setattr(s, "heygen_default_avatar_id", "")
    with pytest.raises(Exception) as e:
        await presenters.resolve(None)
    assert "presenter_required" in str(e.value.detail)
    monkeypatch.setattr(s, "heygen_default_avatar_id", "look-123")
    assert await presenters.resolve(None) == "look-123"


async def test_the_chosen_presenter_is_what_the_vendor_is_asked_for(client, workspace):
    from app.integrations import registry
    from app.integrations.avatar.mock import MockAvatarProvider
    from app.pipeline.queue import get_queue

    class Spy(MockAvatarProvider):
        def __init__(self):
            super().__init__()
            self.avatars: list[str | None] = []

        async def generate(self, req):
            self.avatars.append(req.avatar_id)
            return await super().generate(req)

    spy = Spy()
    registry.override(avatar=spy)
    pid = (await client.post("/v1/projects", json={**BRIEF, "anchor_id": "stand-in-woman"}, headers=OWNER)).json()["id"]
    script = (await client.post(f"/v1/projects/{pid}/script/generate", headers=OWNER)).json()
    body = {k: script[k] for k in ("segments", "ticker_lines", "lower_thirds", "interview_questions")}
    await client.put(f"/v1/projects/{pid}/script", json=body, headers=OWNER)
    await client.post(f"/v1/projects/{pid}/script/approve", headers=OWNER)
    await get_queue().drain()
    assert spy.avatars and set(spy.avatars) == {"stand-in-woman"}


async def test_a_look_that_brings_its_own_studio_is_shown_full_frame(client, workspace, monkeypatch):
    from app.integrations import registry
    from app.integrations.avatar.mock import MockAvatarProvider
    from app.pipeline.queue import get_queue

    class Spy(MockAvatarProvider):
        def __init__(self):
            super().__init__()
            self.transparent: list[bool] = []

        async def generate(self, req):
            self.transparent.append(req.transparent)
            return await super().generate(req)

    monkeypatch.setattr(get_settings(), "heygen_fullframe_avatar_ids", "stand-in-woman, other-look")
    spy = Spy()
    registry.override(avatar=spy)

    async def make(anchor):
        pid = (await client.post("/v1/projects", json={**BRIEF, "anchor_id": anchor}, headers=OWNER)).json()["id"]
        script = (await client.post(f"/v1/projects/{pid}/script/generate", headers=OWNER)).json()
        body = {k: script[k] for k in ("segments", "ticker_lines", "lower_thirds", "interview_questions")}
        await client.put(f"/v1/projects/{pid}/script", json=body, headers=OWNER)
        await client.post(f"/v1/projects/{pid}/script/approve", headers=OWNER)
        await get_queue().drain()
        req = [r for r in registry.get_renderer().requests if r.output_prefix.startswith(f"projects/{pid}/")][-1]
        return pid, req

    _pid, req = await make("stand-in-woman")
    assert spy.transparent == [False] and req.props["anchorFullFrame"] is True
    assert req.input_urls["anchor"].split("?")[0].endswith("anchor.mp4")
    spy.transparent.clear()
    _pid, req = await make("stand-in-man")
    assert spy.transparent == [True] and req.props["anchorFullFrame"] is False
    assert req.input_urls["anchor"].split("?")[0].endswith("anchor.webm")


def test_plain_fullframe_look_skips_the_screen_covers(monkeypatch):
    from app.pipeline import steps

    monkeypatch.setattr(get_settings(), "heygen_fullframe_avatar_ids", "lady, man:plain")

    class P:
        anchor_id = "man"

    assert steps.is_fullframe(P()) and steps.fullframe_covers(P()) is False
    P.anchor_id = "lady"
    assert steps.is_fullframe(P()) and steps.fullframe_covers(P()) is True
    P.anchor_id = "other"
    assert not steps.is_fullframe(P())


async def test_the_standard_sign_off_is_paid_for_once_and_reused(client, workspace):
    """The closing line is the same words every time, so its presenter clip is bought once and copied to later videos."""
    from app.integrations import registry
    from app.integrations.avatar.mock import MockAvatarProvider
    from app.pipeline.queue import get_queue

    class Spy(MockAvatarProvider):
        def __init__(self):
            super().__init__()
            self.texts: list[str] = []

        async def generate(self, req):
            self.texts.append(req.script_text)
            return await super().generate(req)

    spy = Spy()
    registry.override(avatar=spy)

    async def make(company):
        pid = (await client.post("/v1/projects", json=BRIEF, headers=OWNER)).json()["id"]
        script = (await client.post(f"/v1/projects/{pid}/script/generate", headers=OWNER)).json()
        outro = [s for s in script["segments"] if s["kind"] == "outro"]
        assert outro and outro[0]["text"] == presenters.STANDARD_OUTRO  # generated scripts end the standard way
        body = {k: script[k] for k in ("segments", "ticker_lines", "lower_thirds", "interview_questions")}
        body["segments"] = [
            {"kind": "intro", "text": f"Tonight we feature {company}."},
            {"kind": "body", "text": f"{company} sells things."},
            outro[0],
        ]
        await client.put(f"/v1/projects/{pid}/script", json=body, headers=OWNER)
        r = await client.post(f"/v1/projects/{pid}/script/approve", json={"with_interview": True}, headers=OWNER)
        assert r.status_code == 200, r.text
        await get_queue().drain()
        return pid

    await make("Acme")
    await make("Beta")
    assert spy.texts.count(presenters.STANDARD_OUTRO) == 1  # bought once, copied for the second video
