"""Behaviour checks for Video Rulebook rules that had no test of their own before the rulebook existed."""

from sqlalchemy import select

from app.models import Project, Take
from app.pipeline import steps
from app.pipeline.queue import get_queue
from app.video_rules import value
from tests.conftest import OWNER
from tests.test_broll import add_image
from tests.test_guided_flow import interviewed
from tests.test_live_interview import state


async def _approve(client, pid):
    script = (await client.get(f"/v1/projects/{pid}/script", headers=OWNER)).json()
    body = {k: script[k] for k in ("segments", "ticker_lines", "lower_thirds", "interview_questions")}
    body["confirmed_claims"] = [c["text"] for c in script["claim_flags"]]
    assert (await client.put(f"/v1/projects/{pid}/script", json=body, headers=OWNER)).status_code == 200
    r = await client.post(f"/v1/projects/{pid}/script/approve", json={}, headers=OWNER)
    assert r.status_code == 200, r.text
    await get_queue().drain()
    assert await state(client, pid) == "final_ready"


async def test_an_answer_trimmed_below_the_shortest_length_is_refused_and_never_rendered(client, workspace, maker):
    # covers("BIV-SCN-003")
    pid = await interviewed(client)
    async with maker() as db:
        takes = (await db.execute(select(Take).where(Take.project_id == pid))).scalars().all()
        length = {t.question_index: float(t.duration_s or 0) for t in takes}
    shortest = value("BIV-SCN-003")
    plan = {
        "layout": "full",
        "order": [0, 1, 2, 3],
        "answers": [{"question_index": q, "trim_start_s": length[1] - shortest / 2 if q == 1 else 0} for q in range(4)],
    }
    r = await client.put(f"/v1/projects/{pid}/interview/plan", json=plan, headers=OWNER)
    assert r.status_code == 422 and "shorter than 1 second" in r.json()["detail"]["message"]
    # and if one ever reached the render step, the step itself leaves it out (with its question)
    async with maker() as db:
        take = (await db.execute(select(Take).where(Take.project_id == pid, Take.question_index == 1))).scalars().first()
        take.duration_s = shortest / 2
        await db.commit()
    assert (await client.post(f"/v1/projects/{pid}/interview/merge", headers=OWNER)).status_code == 200
    await _approve(client, pid)
    async with maker() as db:
        scenes = (await db.get(Project, pid)).scene_plan["scenes"]
    asked = [s["question_index"] for s in scenes if s["type"] == "anchor_question"]
    answered = [s["question_index"] for s in scenes if s.get("founder")]
    assert 1 not in asked and 1 not in answered and len(answered) == 3


async def test_pictures_in_the_guided_flow_go_with_the_story_not_into_the_video(client, workspace, maker):
    # covers("BIV-SCN-007")
    pid = await interviewed(client)
    assert (await client.post(f"/v1/projects/{pid}/interview/merge", headers=OWNER)).status_code == 200
    keys = [await add_image(client) for _ in range(2)]
    items = [{"key": k, "caption": f"Picture {i + 1}", "seconds": 3} for i, k in enumerate(keys)]
    assert (await client.put(f"/v1/projects/{pid}/broll", json={"items": items}, headers=OWNER)).status_code == 200
    await _approve(client, pid)
    async with maker() as db:
        scenes = (await db.get(Project, pid)).scene_plan["scenes"]
    assert not [s for s in scenes if s["type"] == "product_broll"]


def test_a_render_missing_any_file_fails_the_quality_check():
    # covers("BIV-QC-005")
    result = {
        "props": {"tickerLines": ["x"], "lowerThirds": [], "anchorDurationSeconds": 10.0},
        "output_keys": ["only-one.mp4"],
        "analyses": {},
    }
    assert "missing output formats" in steps.quality_gate(result, outputs=3)
    assert "missing output formats" not in steps.quality_gate({**result, "output_keys": ["a", "b", "c"]}, outputs=3)


def test_presenter_clips_are_made_a_few_at_a_time():
    # covers("BIV-COST-003")
    assert steps.PARALLEL_CLIPS == value("BIV-COST-003") == 3
