"""The optional LiveKit room for the AI interview. No LiveKit server is contacted: tokens are checked with LiveKit's own verifier."""

import json

from livekit import api

from app.config import get_settings
from tests.conftest import OWNER
from tests.test_live_interview import live_project, start


def configure(monkeypatch):
    s = get_settings()
    monkeypatch.setattr(s, "livekit_url", "wss://example.livekit.cloud")
    monkeypatch.setattr(s, "livekit_api_key", "APIkeytest")
    monkeypatch.setattr(s, "livekit_api_secret", "s" * 40)


async def test_without_livekit_the_interview_runs_in_the_browser(client, workspace):
    pid = await live_project(client)
    token = (await start(client, pid)).json()["token"]
    assert (await client.post(f"/v1/interview/{token}/realtime")).status_code == 404
    caps = (await client.get("/v1/capabilities", headers=OWNER)).json()
    assert caps["interview_room"] == "browser"


async def test_the_join_token_is_for_this_room_and_starts_the_interviewer(client, workspace, monkeypatch):
    configure(monkeypatch)
    pid = await live_project(client)
    token = (await start(client, pid)).json()["token"]
    r = await client.post(f"/v1/interview/{token}/realtime")
    assert r.status_code == 200, r.text
    got = r.json()
    assert got["url"] == "wss://example.livekit.cloud" and got["room"] == f"interview-{pid}"
    claims = api.TokenVerifier("APIkeytest", "s" * 40).verify(
        got["token"]
    )  # LiveKit's own check of signature and expiry
    assert claims.video.room == got["room"] and claims.video.room_join and claims.video.can_publish_data
    dispatch = claims.room_config.agents[0]
    assert dispatch.agent_name == "cf-interviewer"
    meta = json.loads(dispatch.metadata)
    assert meta["token"] == token and meta["api"].startswith("http")  # how the agent reads the lines
    assert (await client.get("/v1/capabilities", headers=OWNER)).json()["interview_room"] == "livekit"


async def test_a_wrong_secret_does_not_verify(client, workspace, monkeypatch):
    configure(monkeypatch)
    pid = await live_project(client)
    token = (await start(client, pid)).json()["token"]
    got = (await client.post(f"/v1/interview/{token}/realtime")).json()
    try:
        api.TokenVerifier("APIkeytest", "x" * 40).verify(got["token"])
    except Exception:  # noqa: BLE001
        return
    raise AssertionError("a token signed with another secret must not verify")


async def test_the_agent_reads_plain_text_lines_with_no_spend(client, workspace):
    pid = await live_project(client)
    token = (await start(client, pid)).json()["token"]
    lines = (await client.get(f"/v1/interview/{token}/lines")).json()["lines"]
    assert lines["greeting"].startswith("Hi Tobi") and lines["q0"] and lines["closing"]
    assert (await client.get("/v1/interview/not-a-token/lines")).status_code in {401, 403, 404}
