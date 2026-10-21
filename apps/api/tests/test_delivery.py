from decimal import Decimal

from app.routes import delivery
from app.services.captions import DISCLOSURE, build_srt
from tests.conftest import OPS, OWNER
from tests.helpers import make_final_ready


def test_srt_is_well_formed_and_covers_duration():
    srt = build_srt([{"text": "one two three four five six seven eight nine ten"}], 10.0, max_words=5)
    blocks = srt.strip().split("\n\n")
    assert len(blocks) == 2
    assert blocks[0].startswith("1\n00:00:00,000 --> 00:00:05,000")
    assert "00:00:10,000" in blocks[1]


async def test_downloads_signed_urls_and_disclosure(client, workspace):
    pid = await make_final_ready(client)
    d = (await client.get(f"/v1/projects/{pid}/downloads", headers=OWNER)).json()
    kinds = {(i["type"], i["format"]) for i in d["items"]}
    assert {("render", "16x9"), ("render", "9x16"), ("thumbnail", "16x9"), ("caption", None)} <= kinds
    assert d["disclosure"] == DISCLOSURE
    assert all(i["expires_in_s"] <= 900 and i["url"] for i in d["items"])


async def test_downloads_are_private_to_workspace(client, workspace, maker):
    from app.models import User, Workspace

    pid = await make_final_ready(client)
    async with maker() as s:
        ws = Workspace(name="Other")
        s.add(ws)
        await s.flush()
        s.add(User(email="other@example.com", workspace_id=ws.id))
        await s.commit()
    other = {"Authorization": "Bearer dev:other@example.com"}
    for path in ("", "/downloads", "/captions", "/costs"):
        assert (await client.get(f"/v1/projects/{pid}{path}", headers=other)).status_code == 404


async def test_captions_always_carry_disclosure(client, workspace):
    pid = await make_final_ready(client)
    caps = (await client.get(f"/v1/projects/{pid}/captions", headers=OWNER)).json()
    assert set(caps["captions"]) == {"linkedin", "instagram", "x"}
    assert all(DISCLOSURE in c for c in caps["captions"].values())


async def test_share_lifecycle_and_revoke(client, workspace):
    pid = await make_final_ready(client)
    url = (await client.post(f"/v1/projects/{pid}/share", headers=OWNER)).json()["url"]
    token = url.rsplit("/s/", 1)[1]
    pub = await client.get(f"/v1/share/{token}")  # no auth header
    assert pub.status_code == 200
    body = pub.json()
    assert body["tag"] == "Featured" and body["disclosure"] == DISCLOSURE and body["video_url"]
    assert (await client.delete(f"/v1/projects/{pid}/share", headers=OWNER)).status_code == 200
    assert (await client.get(f"/v1/share/{token}")).status_code == 404
    assert (await client.get("/v1/share/not-a-token")).status_code == 404


async def test_share_requires_ready_video(client, workspace):
    pid = (await client.post("/v1/projects", json={"brief_text": "x" * 30}, headers=OWNER)).json()["id"]
    assert (await client.post(f"/v1/projects/{pid}/share", headers=OWNER)).status_code == 409


async def test_operator_can_disable_share_links(client, workspace):
    pid = await make_final_ready(client)
    token = (await client.post(f"/v1/projects/{pid}/share", headers=OWNER)).json()["url"].rsplit("/s/", 1)[1]
    await client.patch(f"/v1/admin/workspaces/{workspace}", json={"share_disabled": True}, headers=OPS)
    assert (await client.get(f"/v1/share/{token}")).status_code == 404
    assert (await client.post(f"/v1/projects/{pid}/share", headers=OWNER)).status_code == 403


async def test_share_token_stored_hashed(client, workspace, maker):
    from sqlalchemy import select

    from app.models import ShareLink

    pid = await make_final_ready(client)
    token = (await client.post(f"/v1/projects/{pid}/share", headers=OWNER)).json()["url"].rsplit("/s/", 1)[1]
    async with maker() as s:
        row = (await s.execute(select(ShareLink))).scalar_one()
    assert token not in row.token_hash and len(row.token_hash) == 64


async def test_costs_breakdown(client, workspace):
    pid = await make_final_ready(client)
    c = (await client.get(f"/v1/projects/{pid}/costs", headers=OWNER)).json()
    assert {line["stage"] for line in c["lines"]} == {"anchor_render", "preview_render", "final_render"}
    assert Decimal(c["total"]) == sum(Decimal(line["cost"]) for line in c["lines"]) > 0


async def test_events_stream_emits_final_state(client, workspace):
    pid = await make_final_ready(client)
    delivery.SSE_POLL_S = 0.01
    r = await client.get(f"/v1/projects/{pid}/events", headers=OWNER)
    assert r.headers["content-type"].startswith("text/event-stream")
    assert 'event: state\ndata: {"state": "final_ready"' in r.text


async def test_list_projects(client, workspace):
    pid = await make_final_ready(client)
    assert [p["id"] for p in (await client.get("/v1/projects", headers=OWNER)).json()] == [pid]


async def test_failure_and_limit_emails_are_plain_language(client, workspace, maker):
    from app.integrations import registry
    from app.models import Workspace

    async with maker() as s:
        (await s.get(Workspace, workspace)).credit_balance = Decimal("0")
        await s.commit()
    await make_final_ready(client)
    subjects = {m["subject"] for m in registry.get_email().sent}
    assert subjects == {"Your video is paused: limit reached"}
    assert all("Traceback" not in m["text"] and "Exception" not in m["text"] for m in registry.get_email().sent)


async def test_email_failure_does_not_break_pipeline(client, workspace):
    from app.integrations import registry
    from app.integrations.email.mock import MockEmail

    class Broken(MockEmail):
        async def send(self, *a, **k):
            raise RuntimeError("smtp down")

    registry.reset_providers(email=Broken())
    pid = await make_final_ready(client)
    assert (await client.get(f"/v1/projects/{pid}", headers=OWNER)).json()["state"] == "final_ready"


async def test_real_network_names_blocked_before_any_spend(client, workspace, maker):
    from app.models import Workspace
    from app.services.safety import find_banned

    assert find_banned("As seen on BBC and cnn") == ["bbc", "cnn"]
    assert find_banned("a bbcode parser") == []
    r = await client.post("/v1/projects", json={"brief_text": "Acme helps farmers sell produce online."}, headers=OWNER)
    pid = r.json()["id"]
    script = (await client.post(f"/v1/projects/{pid}/script/generate", headers=OWNER)).json()
    body = {k: script[k] for k in ("segments", "ticker_lines", "lower_thirds", "interview_questions")}
    body["segments"] = [{"kind": "intro", "text": "Tonight we feature Acme."}]
    body["ticker_lines"] = ["BREAKING on CNN: Acme launches"]
    await client.put(f"/v1/projects/{pid}/script", json=body, headers=OWNER)
    r = await client.post(f"/v1/projects/{pid}/script/approve", headers=OWNER)
    assert r.status_code == 422 and r.json()["detail"]["terms"] == ["cnn"]
    async with maker() as s:
        assert (await s.get(Workspace, workspace)).credit_balance == Decimal("10")
