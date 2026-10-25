"""The guided flow: details -> AI interview -> written story -> pictures -> video, spending as little as possible."""

from decimal import Decimal

from sqlalchemy import select

from app.integrations import registry
from app.integrations.avatar.mock import MockAvatarProvider
from app.models import Asset, Job, Project, ScriptVersion, Workspace
from app.pipeline.queue import get_queue
from app.services import presenters
from tests.conftest import OWNER
from tests.helpers import record
from tests.test_broll import add_image
from tests.test_live_interview import start, state

DETAILS = {
    "brief_text": "Acme Farms raised a seed round to help farmers sell produce online.\n\nAnnouncement type: Funding round.",
    "founder_name": "Tobi Oyinlola",
    "founder_title": "CEO, Acme",
    "flow": "guided",
    "announcement_type": "funding_round",
}


async def guided_project(client):
    pid = (await client.post("/v1/projects", json=DETAILS, headers=OWNER)).json()["id"]
    r = await client.post(f"/v1/projects/{pid}/guided/start", headers=OWNER)
    assert r.status_code == 200, r.text
    return pid


async def interviewed(client, answers=(0, 1, 2, 3)):
    pid = await guided_project(client)
    token = (await start(client, pid)).json()["token"]
    for q in answers:
        await record(client, token, q)
    return pid


async def test_details_open_the_interview_and_spend_nothing(client, workspace, maker):
    pid = await guided_project(client)
    p = (await client.get(f"/v1/projects/{pid}", headers=OWNER)).json()
    assert p["state"] == "interviewing" and p["flow"] == "guided" and p["announcement_type"] == "funding_round"
    async with maker() as s:
        assert (await s.execute(select(Job).where(Job.project_id == pid))).scalars().all() == []
        assert (await s.get(Workspace, workspace)).credit_balance == Decimal("10")
        plan = (await s.execute(select(ScriptVersion).where(ScriptVersion.project_id == pid))).scalars().one()
        assert plan.approved and len(plan.interview_questions) == 4


async def test_finishing_the_interview_writes_the_story_for_review(client, workspace, maker):
    pid = await interviewed(client)
    r = await client.post(f"/v1/projects/{pid}/interview/merge", headers=OWNER)
    assert r.status_code == 200, r.text
    assert await state(client, pid) == "script_ready"
    story = (await client.get(f"/v1/projects/{pid}/story", headers=OWNER)).json()
    assert story["headline"] and story["sections"] and story["social"]["hook"] and story["social"]["post"]
    script = (await client.get(f"/v1/projects/{pid}/script", headers=OWNER)).json()
    assert script["segments"][-1] == {"kind": "outro", "text": presenters.STANDARD_OUTRO}
    assert len(script["interview_questions"]) == 4 and not script["approved"] and script["story"]["headline"]
    async with maker() as s:  # nothing from the presenter vendor yet: the owner reviews the story first
        stages = {j.stage for j in (await s.execute(select(Job).where(Job.project_id == pid))).scalars()}
        assert stages <= {"process_take"}
        assert len([a for a in (await s.get(Project, pid)).merge_plan["answers"] if a["include"]]) == 2


async def test_editing_the_story_keeps_the_questions_and_the_article(client, workspace):
    pid = await interviewed(client)
    await client.post(f"/v1/projects/{pid}/interview/merge", headers=OWNER)
    script = (await client.get(f"/v1/projects/{pid}/script", headers=OWNER)).json()
    body = {k: script[k] for k in ("segments", "ticker_lines", "lower_thirds")} | {"interview_questions": ["changed?"]}
    r = await client.put(f"/v1/projects/{pid}/script", json=body, headers=OWNER)
    assert r.status_code == 200
    assert r.json()["interview_questions"] == script["interview_questions"] and r.json()["story"] == script["story"]


async def test_three_featured_answers_are_refused(client, workspace):
    pid = await interviewed(client)
    plan = {"layout": "column", "answers": [{"question_index": q, "include": q < 3} for q in range(4)]}
    assert (await client.put(f"/v1/projects/{pid}/interview/plan", json=plan, headers=OWNER)).status_code == 200
    r = await client.post(f"/v1/projects/{pid}/interview/merge", headers=OWNER)
    assert r.status_code == 422 and r.json()["detail"]["error"] == "too_many_answers"


async def test_approval_needs_two_or_three_pictures_then_makes_the_video_cheaply(client, workspace, maker):
    class Spy(MockAvatarProvider):
        def __init__(self):
            super().__init__()
            self.texts: list[str] = []

        async def generate(self, req):
            self.texts.append(req.script_text)
            return await super().generate(req)

    spy = Spy()
    registry.override(avatar=spy)
    pid = await interviewed(client)
    await client.post(f"/v1/projects/{pid}/interview/merge", headers=OWNER)
    script = (await client.get(f"/v1/projects/{pid}/script", headers=OWNER)).json()
    body = {k: script[k] for k in ("segments", "ticker_lines", "lower_thirds", "interview_questions")}
    body["confirmed_claims"] = [c["text"] for c in script["claim_flags"]]
    await client.put(f"/v1/projects/{pid}/script", json=body, headers=OWNER)

    r = await client.post(f"/v1/projects/{pid}/script/approve", json={}, headers=OWNER)
    assert r.status_code == 422 and r.json()["detail"]["error"] == "pictures_needed"
    keys = [await add_image(client) for _ in range(2)]
    items = [{"key": k, "caption": f"Picture {i + 1}", "seconds": 3} for i, k in enumerate(keys)]
    assert (await client.put(f"/v1/projects/{pid}/broll", json={"items": items}, headers=OWNER)).status_code == 200

    r = await client.post(f"/v1/projects/{pid}/script/approve", json={}, headers=OWNER)
    assert r.status_code == 200, r.text
    await get_queue().drain()
    assert await state(client, pid) == "final_ready"
    lead = "Let's hear from the founder."
    assert len([t for t in spy.texts if t.startswith(lead)]) == 1  # one hand-over, on the first featured question
    assert len(spy.texts) == 4  # opening, two featured questions, the standard sign-off: nothing for the other answers
    assert spy.texts.count(presenters.STANDARD_OUTRO) == 1
    async with maker() as s:
        kinds = {(a.type, a.format) for a in (await s.execute(select(Asset).where(Asset.project_id == pid))).scalars()}
        assert ("question_clip", "q0") in kinds and ("question_clip", "q1") in kinds
        assert ("question_clip", "q2") not in kinds and ("question_clip", "q3") not in kinds
