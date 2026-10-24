"""Edit a finished interview video scene by scene, then re-render only what changed."""

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import Principal, current_principal
from app.db import get_session
from app.models import Project
from app.pipeline.advance import advance
from app.pipeline.steps import approved_script, latest_takes
from app.schemas.api import ProjectOut, SceneOut, ScenePatch, ScenePatchOut, ScenesOut
from app.services import interview as iv
from app.services import revisions
from app.services import scene_plan as sp
from app.services import state_machine as sm

router = APIRouter(prefix="/v1/projects/{project_id}", tags=["scenes"])

LABELS = {
    "anchor_intro": "Presenter: opening",
    "anchor_explanation": "Presenter: explanation",
    "anchor_analysis": "Presenter: analysis",
    "anchor_question": "Presenter asks",
    "news_closing": "Presenter: closing",
    "presenter_clip": "Presenter footage",
    "product_broll": "Product footage",
}


async def _owned(session: AsyncSession, project_id: str, p: Principal) -> Project:
    project = await session.get(Project, project_id)
    if project is None or project.workspace_id != p.workspace.id:
        raise HTTPException(404, "Project not found")
    return project


def _label(s: sp.Scene) -> str:
    if s.type in LABELS:
        return LABELS[s.type] if s.type != "presenter_clip" else f"Presenter footage ({s.headline or 'clip'})"
    return f"Your answer {s.question_number or ''}".strip()


@router.get("/scenes", response_model=ScenesOut)
async def scenes(
    project_id: str, p: Principal = Depends(current_principal), session: AsyncSession = Depends(get_session)
) -> ScenesOut:
    project = await _owned(session, project_id, p)
    if not project.scene_plan:
        raise HTTPException(404, "This video has no editable scenes yet")
    plan = sp.ScenePlan.model_validate(project.scene_plan)
    mp = project.merge_plan or {}
    answers = {a["question_index"]: a for a in mp.get("answers", [])}
    out = []
    for s in plan.scenes:
        a = answers.get(s.question_index) if s.type in revisions.EDITABLE and s.type.startswith("founder_") else None
        out.append(
            SceneOut(
                id=s.id,
                order=s.order,
                type=s.type,
                label=_label(s),
                duration_s=s.duration_s,
                narration=s.narration if s.type in revisions.NARRATION_KIND else None,
                caption=s.headline if s.type == "product_broll" else None,
                layout=sp.FOUNDER_LAYOUT.get(s.type),
                question_index=s.question_index,
                trim_start_s=a["trim_start_s"] if a else None,
                trim_end_s=a["trim_end_s"] if a else None,
                synthetic=s.provenance == "synthetic",
                editable=revisions.EDITABLE.get(s.type, []),
            )
        )
    script = await approved_script(session, project_id)
    excluded = [
        {"question_index": a["question_index"], "question": script.interview_questions[a["question_index"]]}
        for a in mp.get("answers", [])
        if not a.get("include", True) and a["question_index"] < len(script.interview_questions)
    ]
    return ScenesOut(
        plan_hash=project.scene_plan_hash,
        revision_pending=project.revision_pending,
        scenes=out,
        excluded_answers=excluded,
        can_revise=project.state == "final_ready",
    )


@router.patch("/scenes/{scene_id}", response_model=ScenePatchOut)
async def patch_scene(
    project_id: str,
    scene_id: str,
    body: ScenePatch,
    p: Principal = Depends(current_principal),
    session: AsyncSession = Depends(get_session),
) -> ScenePatchOut:
    project = await _owned(session, project_id, p)
    if project.state != "final_ready" or not project.scene_plan:
        raise HTTPException(409, "Scenes can be edited once the video is finished.")
    plan = sp.ScenePlan.model_validate(project.scene_plan)
    changes = body.model_dump(exclude_none=True, exclude={"confirmed_claims"})
    if scene_id.startswith("answer-"):  # an answer that was left out: the only edit is to put it back
        q = int(scene_id.removeprefix("answer-")) if scene_id.removeprefix("answer-").isdigit() else -1
        scene = None
        allowed = ["include"]
        scene_type = "founder_column"
    else:
        scene = next((s for s in plan.scenes if s.id == scene_id), None)
        if scene is None:
            raise HTTPException(404, "Scene not found")
        q, scene_type, allowed = (
            scene.question_index if scene.question_index is not None else -1,
            scene.type,
            revisions.EDITABLE.get(scene.type, []),
        )
    wanted = {
        "narration": "narration",
        "layout": "layout",
        "include": "include",
        "caption": "caption",
        "seconds": "seconds",
    }
    for field in changes:
        group = "trim" if field.startswith("trim_") else wanted.get(field, field)
        if group not in allowed:
            raise HTTPException(422, f"That scene doesn't allow changing its {field.replace('_', ' ')}.")
    regenerates: list[str] = []

    if "narration" in changes:
        await revisions.revise_narration(session, project, scene_type, changes["narration"], body.confirmed_claims)
        regenerates.append(f"the presenter's {revisions.NARRATION_KIND[scene_type]} (a new presenter clip)")
    if scene_type.startswith("founder_") and set(changes) & {"layout", "include", "trim_start_s", "trim_end_s"}:
        script = await approved_script(session, project_id)
        takes = await latest_takes(session, project_id)
        plan_now = project.merge_plan or {}
        answers = [dict(a) for a in plan_now.get("answers", [])]
        target = next((a for a in answers if a["question_index"] == q), None)
        if target is None:
            raise HTTPException(404, "Answer not found")
        for k in ("layout", "include", "trim_start_s", "trim_end_s"):
            if k in changes:
                target[k] = changes[k]
        try:
            project.merge_plan = iv.validate_plan(
                {**plan_now, "answers": answers},
                len(script.interview_questions),
                {i: float(t.duration_s or 0) for i, t in takes.items()},
            )
        except iv.InvalidPlan as e:
            raise HTTPException(422, {"error": "invalid_plan", "message": str(e)}) from None
        regenerates.append("the video (your recording is not touched)")
    if scene_type == "product_broll" and set(changes) & {"caption", "seconds", "include"}:
        items = [dict(i) for i in (project.broll or [])]
        item = next((i for i in items if scene and scene.asset and i["key"] == scene.asset.key), None)
        if item is None:
            raise HTTPException(404, "Footage not found")
        if changes.get("include") is False:
            items.remove(item)
        else:
            if "caption" in changes:
                item["caption"] = changes["caption"].strip()
            if "seconds" in changes:
                item["seconds"] = changes["seconds"]
        project.broll = items
        regenerates.append("the video")
    project.revision_pending = True
    await session.commit()
    return ScenePatchOut(regenerates=regenerates, revision_pending=True)


@router.post("/revise", response_model=ProjectOut)
async def revise(
    project_id: str, p: Principal = Depends(current_principal), session: AsyncSession = Depends(get_session)
) -> ProjectOut:
    """Apply the edits: presenter clips whose words changed are made again (and paid for), everything else is reused,
    and the video is rendered again. While this runs the previous video stays where it is."""
    from app.routes.projects import _out

    project = await _owned(session, project_id, p)
    if project.state != "final_ready" or not project.revision_pending:
        raise HTTPException(409, "There are no changes to apply.")
    sm.transition(project, "rendering_anchor")
    project.revision_pending = False
    project.completed_at = None
    await session.commit()
    await advance(session, project_id)
    await session.refresh(project)
    return await _out(session, project)
