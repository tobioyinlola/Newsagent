"""The guided flow: details -> AI interview -> written story -> video.

Nothing paid runs until the owner has reviewed the story. The only vendor spend after that is the presenter speaking a short
opening, a hand-over line plus a question for each of the (at most two) answers that are featured, and the standard sign-off.
"""

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations import registry
from app.integrations.llm.base import ScriptSegment
from app.models import Project, ScriptVersion
from app.services import interview as iv
from app.services import presenters
from app.services import state_machine as sm
from app.services.claims import detect_claims
from app.services.safety import find_banned

MAX_FEATURED = 2  # answers shown in the video; each one costs a presenter question clip
PRESENTER_WORDS = 55  # the opening the presenter speaks; every second of it is paid for

TYPES = {
    "product_launch": "Product launch",
    "funding_round": "Funding round",
    "partnership": "Partnership",
    "hiring": "Hiring",
    "milestone": "Milestone",
    "other": "Other news",
}


def brief_from_details(kind: str | None, details: str) -> str:
    return f"{details.strip()}\n\nAnnouncement type: {TYPES.get(kind or 'other', 'Other news')}."


async def start(session: AsyncSession, project: Project) -> None:
    """Understand the details, write the interview questions (the only text made before the interview), open the interview."""
    if project.flow != "guided" or project.state != "draft" or project.brief is None:
        raise HTTPException(409, "This video can't start its interview.")
    banned = find_banned(project.brief.raw_text)
    if banned:
        raise HTTPException(
            422,
            {"error": "banned_network_name", "message": "Please remove real news network names: " + ", ".join(banned)},
        )
    llm = registry.get_llm()
    brief = project.brief
    brief.structured_facts = await llm.parse_brief(brief.raw_text, brief.website_url)
    facts = {
        **brief.structured_facts,
        "founder_name": project.founder_name,
        "founder_title": project.founder_title,
        "announcement_type": project.announcement_type,
    }
    draft = await llm.write_script(facts, "confident")
    session.add(
        ScriptVersion(
            project_id=project.id,
            version=1,
            segments=[s.model_dump() for s in draft.segments],
            ticker_lines=draft.ticker_lines,
            lower_thirds=draft.lower_thirds,
            interview_questions=draft.interview_questions[: iv.MAX_QUESTIONS],
            claim_flags=[],
            approved=True,  # the interview plan; the story that is published is a later version the owner approves
            approved_by="system",
        )
    )
    project.interview_enabled, project.interview_mode = True, "live"
    sm.transition(project, "script_ready")
    sm.transition(project, "script_approved")
    sm.transition(project, "interviewing")
    await session.commit()


def featured_plan(saved: dict | None, answered: list[int], count: int) -> dict:
    """The merge plan with at most MAX_FEATURED answers included. With no choice saved yet, the first answers that exist."""
    from app.pipeline.steps import default_plan

    plan = saved or default_plan(count, "column")
    chosen = [
        a["question_index"] for a in plan["answers"] if a.get("include", True) and a["question_index"] in answered
    ]
    if saved is None:
        chosen = [q for q in plan["order"] if q in answered][:MAX_FEATURED]
        for a in plan["answers"]:
            a["include"] = a["question_index"] in chosen
    if len(chosen) > MAX_FEATURED:
        raise HTTPException(
            422,
            {"error": "too_many_answers", "message": f"Feature at most {MAX_FEATURED} answers in the video."},
        )
    return plan


def _trim_words(segments: list[ScriptSegment], budget: int) -> list[dict]:
    out, used = [], 0
    for s in segments:
        if s.kind not in {"intro", "body"}:
            continue
        kept: list[str] = []
        for sentence in s.text.replace("\n", " ").split(". "):
            n = len(sentence.split())
            if used + n > budget and (kept or out):
                break
            kept.append(sentence.rstrip("."))
            used += n
        if kept:
            out.append({"kind": s.kind, "text": ". ".join(kept).strip() + "."})
    return out


async def write_story(
    session: AsyncSession, project: Project, plan_script: ScriptVersion, answers: list[dict]
) -> ScriptVersion:
    """After the interview: the news story + social post + the short presenter script, as an unapproved script version."""
    llm = registry.get_llm()
    facts = {
        **((project.brief.structured_facts if project.brief else None) or {}),
        "founder_name": project.founder_name,
        "founder_title": project.founder_title,
    }
    draft = await llm.write_story(facts, project.announcement_type or "other", answers)
    segments = _trim_words(draft.segments, PRESENTER_WORDS)
    segments.append({"kind": "outro", "text": presenters.STANDARD_OUTRO})
    story = {
        "headline": draft.headline,
        "dek": draft.dek,
        "sections": [s.model_dump() for s in draft.sections],
        "social": draft.social.model_dump(),
        "unverified": draft.unverified,
    }
    text = " ".join(
        [s["text"] for s in segments]
        + [draft.headline, draft.dek]
        + [p for sec in draft.sections for p in sec.paragraphs]
        + [draft.social.post]
    )
    prev = (
        (
            await session.execute(
                select(ScriptVersion)
                .where(ScriptVersion.project_id == project.id)
                .order_by(ScriptVersion.version.desc())
            )
        )
        .scalars()
        .first()
    )
    sv = ScriptVersion(
        project_id=project.id,
        version=(prev.version + 1) if prev else 1,
        segments=segments,
        ticker_lines=draft.ticker_lines[:3],
        lower_thirds=draft.lower_thirds[:1],
        interview_questions=list(plan_script.interview_questions),  # the recorded answers belong to these questions
        claim_flags=[c.model_dump() for c in detect_claims(text)],
        story=story,
    )
    session.add(sv)
    return sv
