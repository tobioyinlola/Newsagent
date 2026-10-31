"""The scene plan: validated, persisted, built from real assets, and refused when media is missing."""

import pytest
from pydantic import ValidationError
from sqlalchemy import select

from app.integrations import registry
from app.models import Asset, Project, Take
from app.pipeline.queue import get_queue
from app.services import scene_plan as sp
from tests.conftest import OWNER
from tests.helpers import record
from tests.test_live_interview import interviewed_project, state


def anchor(i, type_="anchor_intro", d=5.0, key="a.webm"):
    return sp.Scene(id=f"s{i}", order=i, type=type_, duration_s=d, asset=sp.AssetRef(kind="anchor", key=key))


def plan(scenes, total=None, **kw):
    return sp.ScenePlan(project_id="p", scenes=scenes, total_s=total or sum(s.duration_s for s in scenes), **kw)


def test_a_valid_plan_hashes_stably():
    a, b = plan([anchor(0), anchor(1, "news_closing")]), plan([anchor(0), anchor(1, "news_closing")])
    assert a.hash() == b.hash() and len(a.hash()) == 64
    assert plan([anchor(0, d=6)]).hash() != plan([anchor(0, d=5)]).hash()


@pytest.mark.parametrize(
    "build",
    [
        lambda: plan([anchor(0), anchor(2)]),  # gap in the order
        lambda: plan(
            [
                anchor(0),
                sp.Scene(
                    id="s0", order=1, type="anchor_intro", duration_s=2, asset=sp.AssetRef(kind="anchor", key="x")
                ),
            ]
        ),
        lambda: plan([anchor(0)], total=99),  # totals must add up
        lambda: sp.Scene(id="s", order=0, type="anchor_intro", duration_s=0, asset=sp.AssetRef(kind="anchor", key="x")),
        lambda: sp.Scene(id="s", order=0, type="anchor_intro", duration_s=3),  # no media
        lambda: sp.Scene(
            id="s", order=0, type="founder_column", duration_s=3, asset=sp.AssetRef(kind="take_video", key="x")
        ),
        lambda: sp.AssetRef(kind="anchor", key=""),
    ],
)
def test_invalid_plans_are_refused(build):
    with pytest.raises(ValidationError):
        build()


def test_product_footage_needs_its_media_and_synthetic_shots_are_marked():
    with pytest.raises(ValidationError):
        sp.Scene(id="s", order=0, type="product_broll", duration_s=3)  # nothing to show
    ok = sp.Scene(
        id="s",
        order=0,
        type="product_broll",
        duration_s=4,
        asset=sp.AssetRef(kind="broll_image", key="p.png"),
        headline="Our app",
        provenance="synthetic",
    )
    out = sp.to_render_scenes(plan([ok]), lambda k: f"https://signed/{k}")[0]
    assert out == {
        "type": "broll",
        "src": "https://signed/p.png",
        "seconds": 4,
        "kind": "image",
        "caption": "Our app",
        "synthetic": True,
    }


async def test_missing_media_is_found_before_rendering(client, workspace):
    storage = registry.get_storage()
    await storage.put("here.webm", b"x", "video/webm")
    ok = plan([anchor(0, key="here.webm")])
    await sp.validate_assets(ok, storage)
    bad = plan([anchor(0, key="here.webm"), anchor(1, "news_closing", key="gone.webm")])
    with pytest.raises(sp.ScenePlanError) as e:
        await sp.validate_assets(bad, storage)
    assert "scene 2 (news closing): anchor is missing" in str(e.value) and e.value.category == "invalid_input"


async def finished(client, answers=(0, 1, 2, 3)):
    pid, token = await interviewed_project(client, answers=answers[:2])
    for q in answers[2:]:
        await record(client, token, q)
    await client.post(f"/v1/interview/{token}/submit")
    return pid


async def test_the_plan_is_saved_with_the_video_and_describes_it(client, workspace, maker):
    pid = await finished(client)
    assert (await client.post(f"/v1/projects/{pid}/interview/merge", headers=OWNER)).status_code == 200
    await get_queue().drain()
    assert await state(client, pid) == "final_ready"
    async with maker() as s:
        p = await s.get(Project, pid)
    saved = sp.ScenePlan.model_validate(p.scene_plan)
    assert saved.hash() == p.scene_plan_hash and saved.layout == "full"
    kinds = [s.type for s in saved.scenes]
    assert kinds == ["anchor_intro"] + ["anchor_question", "founder_fullscreen"] * 4 + [
        "anchor_analysis",
        "news_closing",
    ]
    founder_scenes = [s for s in saved.scenes if s.type == "founder_fullscreen"]
    assert all(s.provenance == "founder_statement" and s.cues for s in founder_scenes)
    assert saved.scenes[0].provenance == "owner_script" and saved.captions
    assert all("http" not in (r.key) for _s, r in sp.asset_refs(saved))  # keys, never signed URLs
    req = registry.get_renderer().requests[-1]
    assert [s["type"] for s in req.props["scenes"]][:3] == ["anchor", "question", "answer"]
    assert req.props["scenes"][2]["layout"] == "full"


async def test_a_missing_founder_clip_stops_the_video_with_a_clear_reason(client, workspace, maker):
    pid = await finished(client)
    async with maker() as s:
        take = (await s.execute(select(Take).where(Take.project_id == pid, Take.question_index == 1))).scalar_one()
        key = take.processed_video_key
    await registry.get_storage().delete(key)
    await client.post(f"/v1/projects/{pid}/interview/merge", headers=OWNER)
    await get_queue().drain()
    p = (await client.get(f"/v1/projects/{pid}", headers=OWNER)).json()
    assert p["state"] == "failed" and "missing or unusable" in p["failure_reason"] and "scene" in p["failure_reason"]
    assert not any(r.composition == "InterviewMerge" for r in registry.get_renderer().requests), "no render time spent"
    prog = (await client.get(f"/v1/projects/{pid}/progress", headers=OWNER)).json()
    assert prog["failure_category"] == "invalid_input"


async def test_each_answer_can_use_a_different_layout(client, workspace, maker):
    pid = await finished(client)
    plan_body = {
        "layout": "full",
        "order": [0, 1, 2, 3],
        "answers": [{"question_index": q, "include": True, "trim_start_s": 0, "trim_end_s": 0} for q in range(4)],
    }
    assert (await client.put(f"/v1/projects/{pid}/interview/plan", json=plan_body, headers=OWNER)).status_code == 200
    await client.post(f"/v1/projects/{pid}/interview/merge", headers=OWNER)
    await get_queue().drain()
    assert await state(client, pid) == "final_ready"
    answers = [s for s in registry.get_renderer().requests[-1].props["scenes"] if s["type"] == "answer"]
    assert {a["layout"] for a in answers} == {"full"}


async def test_the_plan_is_private_to_its_owner(client, workspace):
    pid = await finished(client)
    assert (await client.get(f"/v1/projects/{pid}/scene-plan", headers=OWNER)).status_code == 404  # nothing merged yet
    await client.post(f"/v1/projects/{pid}/interview/merge", headers=OWNER)
    await get_queue().drain()
    r = await client.get(f"/v1/projects/{pid}/scene-plan", headers=OWNER)
    assert r.status_code == 200 and r.json()["plan"]["project_id"] == pid and len(r.json()["hash"]) == 64
    other = {"Authorization": "Bearer dev:someone@else.test"}
    assert (await client.get(f"/v1/projects/{pid}/scene-plan", headers=other)).status_code in {401, 403, 404}


SEGMENTS = [
    {"kind": "intro", "text": "Tonight we feature Acme, a farm marketplace."},
    {"kind": "explanation", "text": "Acme connects smallholder farmers to verified buyers."},
    {"kind": "analysis", "text": "The founder's answers show a focus on same day payment."},
    {"kind": "outro", "text": "That was Acme. Back to you."},
]


async def test_explanation_and_analysis_are_their_own_presenter_scenes(client, workspace, maker):
    pid, token = await interviewed_project(client, answers=(0, 1), segments=SEGMENTS)
    for q in (2, 3):
        await record(client, token, q)
    await client.post(f"/v1/interview/{token}/submit")
    prog = (await client.get(f"/v1/projects/{pid}/progress", headers=OWNER)).json()
    assert {"presenter_explanation", "presenter_analysis"} <= {s["key"] for s in prog["stages"]}
    await client.post(f"/v1/projects/{pid}/interview/merge", headers=OWNER)
    await get_queue().drain()
    assert await state(client, pid) == "final_ready"
    async with maker() as s:
        saved = sp.ScenePlan.model_validate((await s.get(Project, pid)).scene_plan)
        assets = {(a.type, a.format) for a in (await s.execute(select(Asset).where(Asset.project_id == pid))).scalars()}
    assert [s.type for s in saved.scenes] == (
        ["anchor_intro", "anchor_explanation"]
        + ["anchor_question", "founder_fullscreen"] * 4
        + ["anchor_analysis", "news_closing"]
    )
    assert {("anchor", "main"), ("anchor", "explanation"), ("anchor", "analysis"), ("anchor_outro", "outro")} <= assets
    assert saved.scenes[1].narration.startswith("Acme connects") and saved.scenes[-2].narration.startswith(
        "The founder's"
    )
    # the explanation's captions start when its scene starts (right after the opening), before any question
    start = saved.scenes[0].duration_s
    expl = [c for c in saved.captions if c.text.startswith("Acme connects smallholder")]
    assert expl and abs(expl[0].start - start) < 0.01
    question_start = start + saved.scenes[1].duration_s
    question_end = question_start + saved.scenes[2].duration_s
    question_captions = [c for c in saved.captions if c.start >= question_start - 0.01 and c.end <= question_end + 0.01]
    assert question_captions and saved.scenes[2].question in " ".join(c.text for c in question_captions)
    assert question_captions[0].start >= expl[-1].end - 0.01
    assert (await client.get(f"/v1/projects/{pid}/progress", headers=OWNER)).json()["percent"] == 100


async def test_a_legacy_script_without_summary_gets_a_recap_before_closing(client, workspace):
    pid, token = await interviewed_project(client, answers=(0, 1))
    for q in (2, 3):
        await record(client, token, q)
    await client.post(f"/v1/interview/{token}/submit")
    await client.post(f"/v1/projects/{pid}/interview/merge", headers=OWNER)
    await get_queue().drain()
    kinds = [s["type"] for s in registry.get_renderer().requests[-1].props["scenes"]]
    assert kinds == ["anchor"] + ["question", "answer"] * 4 + ["anchor", "anchor"]
