"""Editing a finished video: change one scene's narration, layout, trim or caption, then re-make only what changed.
Presenter clips are paid for again only when their text changed (clips are cached by what they say); the render is
repeated; the founder's recordings are never touched."""

from datetime import UTC, datetime

from fastapi import HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Project, ScriptVersion
from app.pipeline.steps import EXTRA_KINDS, approved_script
from app.services import moderation_flow
from app.services.claims import detect_claims
from app.services.moderation import fingerprint, script_text
from app.services.safety import find_banned

WORDS_PER_SECOND = 2.5
# which part of the script each presenter scene speaks (question scenes are fixed: the founder answered THAT question)
NARRATION_KIND = {
    "anchor_intro": "intro",
    "anchor_explanation": "explanation",
    "anchor_analysis": "analysis",
    "news_closing": "outro",
}
EDITABLE = {
    "anchor_intro": ["narration"],
    "anchor_explanation": ["narration"],
    "anchor_analysis": ["narration"],
    "news_closing": ["narration"],
    "anchor_question": [],
    "presenter_clip": [],
    "product_broll": ["caption", "seconds", "include"],
    "founder_picture_in_picture": ["layout", "include", "trim"],
    "founder_split": ["layout", "include", "trim"],
    "founder_column": ["layout", "include", "trim"],
    "founder_fullscreen": ["layout", "include", "trim"],
}


async def revise_narration(
    session: AsyncSession, project: Project, scene_type: str, text: str, confirmed_claims: list[str]
) -> ScriptVersion:
    """A new approved script version with one part replaced. Every check the first approval applied applies again."""
    kind = NARRATION_KIND.get(scene_type)
    if kind is None:
        raise HTTPException(422, "That scene's words can't be edited.")
    text = text.strip()
    if not text or len(text) > 2000:
        raise HTTPException(422, "Write between 1 and 2000 characters.")
    prev = await approved_script(session, project.id)
    if kind == "intro":  # the opening is intro + body (+ anything else that isn't a named part): one piece of text
        keep = [s for s in prev.segments if s.get("kind") in {"outro", *EXTRA_KINDS}]
        segments = [{"kind": "intro", "text": text}, *keep]
    else:
        segments = [s for s in prev.segments if s.get("kind") != kind]
        segments.append({"kind": kind, "text": text})
    order = ["intro", "body", "explanation", "analysis", "outro"]
    segments.sort(key=lambda s: order.index(s["kind"]) if s.get("kind") in order else 1)
    flags = [c.model_dump() for c in detect_claims(" ".join(s["text"] for s in segments))]
    for f in flags:
        f["confirmed"] = f["text"] in confirmed_claims
    if any(not f["confirmed"] for f in flags):  # hard rule 3, as at first approval
        raise HTTPException(
            422,
            {
                "error": "claims_unconfirmed",
                "message": "Please confirm each flagged claim before applying this change.",
                "claims": [f for f in flags if not f["confirmed"]],
            },
        )
    banned = find_banned(text)
    if banned:  # hard rule 1
        raise HTTPException(
            422,
            {"error": "banned_network_name", "message": "Please remove real news network names: " + ", ".join(banned)},
        )
    brief_text = project.brief.raw_text if project.brief else ""
    full = script_text(brief_text, segments, prev.ticker_lines, prev.lower_thirds, prev.interview_questions)
    await moderation_flow.enforce(
        session,
        project_id=project.id,
        workspace_id=project.workspace_id,
        stage="script",
        subject_id=fingerprint(full),
        text=full,
    )
    words = sum(len(s["text"].split()) for s in segments)
    from app.models import Workspace

    ws = await session.get(Workspace, project.workspace_id)
    if ws and words / WORDS_PER_SECOND > ws.max_video_seconds:
        raise HTTPException(422, "That would make the video longer than your plan allows.")
    sv = ScriptVersion(
        project_id=project.id,
        version=prev.version + 1,
        segments=segments,
        ticker_lines=prev.ticker_lines,
        lower_thirds=prev.lower_thirds,
        interview_questions=prev.interview_questions,
        claim_flags=flags,
        approved=True,
        approved_by=prev.approved_by,
        approved_at=prev.approved_at or datetime.now(UTC),  # a revision is not a new video for the daily limit
    )
    session.add(sv)
    return sv
