"""Editing a finished interview video scene by scene: only what changed is made again."""

from sqlalchemy import select

from app.integrations import registry
from app.integrations.avatar.mock import MockAvatarProvider
from app.models import Project, ScriptVersion, User, Workspace
from app.pipeline.queue import get_queue
from tests.conftest import OWNER
from tests.helpers import record
from tests.test_live_interview import interviewed_project, state
from tests.test_scene_plan import SEGMENTS


class Counting(MockAvatarProvider):
    def __init__(self):
        super().__init__()
        self.texts: list[str] = []

    async def generate(self, req):
        self.texts.append(req.script_text)
        return await super().generate(req)


async def finished_video(client):
    ai = Counting()
    registry.override(avatar=ai)
    pid, token = await interviewed_project(client, answers=(0, 1), segments=SEGMENTS)
    for q in (2, 3):
        await record(client, token, q)
    await client.post(f"/v1/interview/{token}/submit")
    await client.post(f"/v1/projects/{pid}/interview/merge", headers=OWNER)
    await get_queue().drain()
    assert await state(client, pid) == "final_ready"
    return pid, ai


async def scenes(client, pid):
    r = await client.get(f"/v1/projects/{pid}/scenes", headers=OWNER)
    assert r.status_code == 200, r.text
    return r.json()


def by_type(sc, t):
    return [s for s in sc["scenes"] if s["type"] == t]


async def apply(client, pid):
    r = await client.post(f"/v1/projects/{pid}/revise", headers=OWNER)
    assert r.status_code == 200, r.text
    await get_queue().drain()
    return await state(client, pid)


async def test_the_scenes_say_what_can_be_edited(client, workspace):
    pid, _ai = await finished_video(client)
    sc = await scenes(client, pid)
    assert sc["can_revise"] and not sc["revision_pending"] and sc["plan_hash"]
    assert by_type(sc, "anchor_explanation")[0]["editable"] == ["narration"]
    assert by_type(sc, "anchor_question")[0]["editable"] == []  # the founder answered THAT question
    assert by_type(sc, "founder_column")[0]["editable"] == ["layout", "include", "trim"]
    assert by_type(sc, "founder_column")[0]["trim_start_s"] == 0


async def test_changing_the_words_of_one_part_makes_only_that_clip_again(client, workspace, maker):
    pid, ai = await finished_video(client)
    made = len(ai.texts)
    before = (await scenes(client, pid))["plan_hash"]
    sid = by_type(await scenes(client, pid), "anchor_explanation")[0]["id"]
    r = await client.patch(
        f"/v1/projects/{pid}/scenes/{sid}",
        json={"narration": "Acme links farmers and buyers on one app."},
        headers=OWNER,
    )
    assert r.status_code == 200 and r.json()["revision_pending"] and "presenter clip" in r.json()["regenerates"][0]
    assert (await scenes(client, pid))["revision_pending"]
    assert await apply(client, pid) == "final_ready"
    assert ai.texts[made:] == ["Acme links farmers and buyers on one app."], "only the changed part was paid for again"
    sc = await scenes(client, pid)
    assert sc["plan_hash"] != before and not sc["revision_pending"]
    assert by_type(sc, "anchor_explanation")[0]["narration"] == "Acme links farmers and buyers on one app."
    async with maker() as s:
        versions = (await s.execute(select(ScriptVersion).where(ScriptVersion.project_id == pid))).scalars().all()
    assert max(v.version for v in versions) == len(versions) and max(versions, key=lambda v: v.version).approved
    assert (await client.get(f"/v1/projects/{pid}/downloads", headers=OWNER)).json()["items"]  # still deliverable


async def test_edits_get_the_same_checks_as_the_first_approval(client, workspace):
    pid, _ai = await finished_video(client)
    sid = by_type(await scenes(client, pid), "anchor_analysis")[0]["id"]
    claim = "Acme raised $5 million in funding last year."
    r = await client.patch(f"/v1/projects/{pid}/scenes/{sid}", json={"narration": claim}, headers=OWNER)
    assert r.status_code == 422 and r.json()["detail"]["error"] == "claims_unconfirmed"
    confirmed = r.json()["detail"]["claims"][0]["text"]
    ok = await client.patch(
        f"/v1/projects/{pid}/scenes/{sid}", json={"narration": claim, "confirmed_claims": [confirmed]}, headers=OWNER
    )
    assert ok.status_code == 200, ok.text
    banned = await client.patch(
        f"/v1/projects/{pid}/scenes/{sid}", json={"narration": "As CNN reported, Acme is great."}, headers=OWNER
    )
    assert banned.status_code == 422 and banned.json()["detail"]["error"] == "banned_network_name"
    bad = await client.patch(
        f"/v1/projects/{pid}/scenes/{sid}", json={"narration": "We are selling cocaine to students"}, headers=OWNER
    )
    assert bad.status_code == 422


async def test_a_layout_change_costs_a_render_not_a_presenter_clip(client, workspace):
    pid, ai = await finished_video(client)
    made = len(ai.texts)
    answers = by_type(await scenes(client, pid), "founder_column")
    r = await client.patch(f"/v1/projects/{pid}/scenes/{answers[1]['id']}", json={"layout": "full"}, headers=OWNER)
    assert r.status_code == 200 and "not touched" in r.json()["regenerates"][0]
    assert await apply(client, pid) == "final_ready"
    assert len(ai.texts) == made, "no presenter clip was made again"
    kinds = [s["type"] for s in (await scenes(client, pid))["scenes"] if s["type"].startswith("founder_")]
    assert kinds == ["founder_column", "founder_fullscreen", "founder_column", "founder_column"]
    rendered = [s for s in registry.get_renderer().requests[-1].props["scenes"] if s["type"] == "answer"]
    assert [a["layout"] for a in rendered] == ["column", "full", "column", "column"]


async def test_an_answer_can_be_dropped_trimmed_and_put_back(client, workspace):
    pid, _ai = await finished_video(client)
    sc = await scenes(client, pid)
    second = by_type(sc, "founder_column")[1]
    assert (
        await client.patch(f"/v1/projects/{pid}/scenes/{second['id']}", json={"include": False}, headers=OWNER)
    ).status_code == 200
    assert await apply(client, pid) == "final_ready"
    sc = await scenes(client, pid)
    assert (
        len(by_type(sc, "founder_column")) == 3
        and sc["excluded_answers"][0]["question_index"] == second["question_index"]
    )
    back = await client.patch(
        f"/v1/projects/{pid}/scenes/answer-{second['question_index']}", json={"include": True}, headers=OWNER
    )
    assert back.status_code == 200, back.text
    assert await apply(client, pid) == "final_ready"
    assert len(by_type(await scenes(client, pid), "founder_column")) == 4
    first = by_type(await scenes(client, pid), "founder_column")[0]
    trim = await client.patch(f"/v1/projects/{pid}/scenes/{first['id']}", json={"trim_start_s": 0.5}, headers=OWNER)
    assert trim.status_code == 200
    too_much = await client.patch(f"/v1/projects/{pid}/scenes/{first['id']}", json={"trim_start_s": 900}, headers=OWNER)
    assert too_much.status_code == 422 and too_much.json()["detail"]["error"] == "invalid_plan"


async def test_only_allowed_edits_are_accepted(client, workspace):
    pid, _ai = await finished_video(client)
    sc = await scenes(client, pid)
    q = by_type(sc, "anchor_question")[0]["id"]
    assert (
        await client.patch(f"/v1/projects/{pid}/scenes/{q}", json={"narration": "Changed"}, headers=OWNER)
    ).status_code == 422
    ans = by_type(sc, "founder_column")[0]["id"]
    assert (
        await client.patch(
            f"/v1/projects/{pid}/scenes/{ans}", json={"narration": "Words in their mouth"}, headers=OWNER
        )
    ).status_code == 422
    assert (
        await client.patch(f"/v1/projects/{pid}/scenes/{ans}", json={"layout": "sideways"}, headers=OWNER)
    ).status_code == 422
    assert (
        await client.patch(f"/v1/projects/{pid}/scenes/nope", json={"include": False}, headers=OWNER)
    ).status_code == 404


async def test_revising_needs_changes_and_a_finished_video(client, workspace):
    pid, _ai = await finished_video(client)
    assert (await client.post(f"/v1/projects/{pid}/revise", headers=OWNER)).status_code == 409  # nothing changed
    plain = (
        await client.post("/v1/projects", json={"brief_text": "Acme sells maize across Ghana."}, headers=OWNER)
    ).json()["id"]
    assert (await client.get(f"/v1/projects/{plain}/scenes", headers=OWNER)).status_code == 404
    assert (
        await client.patch(f"/v1/projects/{plain}/scenes/s1", json={"include": False}, headers=OWNER)
    ).status_code == 409


async def test_edits_are_private_to_the_owner(client, workspace, maker):
    pid, _ai = await finished_video(client)
    async with maker() as s:
        ws = Workspace(name="Other")
        s.add(ws)
        await s.flush()
        s.add(User(email="someone@else.test", workspace_id=ws.id))
        await s.commit()
    theirs = {"Authorization": "Bearer dev:someone@else.test"}
    sid = by_type(await scenes(client, pid), "founder_column")[0]["id"]
    assert (await client.get(f"/v1/projects/{pid}/scenes", headers=theirs)).status_code == 404
    assert (
        await client.patch(f"/v1/projects/{pid}/scenes/{sid}", json={"include": False}, headers=theirs)
    ).status_code == 404
    assert (await client.post(f"/v1/projects/{pid}/revise", headers=theirs)).status_code == 404
    assert (await client.get(f"/v1/projects/{pid}/scenes")).status_code == 401


async def test_a_failed_revision_can_be_retried_and_keeps_the_footage(client, workspace, maker):
    pid, ai = await finished_video(client)
    sid = by_type(await scenes(client, pid), "news_closing")[0]["id"]
    await client.patch(
        f"/v1/projects/{pid}/scenes/{sid}", json={"narration": "That was Acme. Over to you."}, headers=OWNER
    )

    class Down(Counting):
        async def generate(self, req):
            raise RuntimeError("avatar vendor is down")

    registry.override(avatar=Down())
    assert await apply(client, pid) == "failed"
    registry.override(avatar=ai)
    assert (await client.post(f"/v1/projects/{pid}/retry", headers=OWNER)).status_code == 200
    await get_queue().drain()
    assert await state(client, pid) == "final_ready"
    assert ai.texts[-1] == "That was Acme. Over to you."
    async with maker() as s:
        assert (await s.get(Project, pid)).completed_at is not None
