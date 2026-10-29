"""The guided flow: details -> AI interview -> written story -> video.

Nothing paid runs until the owner has reviewed the story. The only vendor spend after that is the presenter speaking a short
opening, a hand-over line plus a question for each of the answers that are featured, and the standard sign-off.
"""

from datetime import UTC, datetime

from fastapi import HTTPException
from pydantic import ValidationError
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations import registry
from app.integrations.llm.base import ScriptSegment
from app.models import Project, ScriptVersion, User, Workspace
from app.services import interview as iv
from app.services import presenters
from app.services import script_polish as polish
from app.services import state_machine as sm
from app.services.claims import detect_claims
from app.services.safety import find_banned

MAX_FEATURED = iv.MAX_QUESTIONS  # every answer can be in the video; each one costs a presenter question clip
PRESENTER_WORDS = 65  # the opening the presenter speaks; every second of it is paid for

TYPES = {
    "product_launch": "Product launch",
    "funding_round": "Funding round",
    "partnership": "Partnership",
    "hiring": "Hiring",
    "milestone": "Milestone",
    "other": "Other news",
}


def _distinct(questions: list[str]) -> list[str]:
    """The same question asked twice reads as a glitch: keep the first of any that say the same thing."""
    out: list[str] = []
    for q in questions:
        if q.strip() and not any(polish.same_thing(q, kept) for kept in out):
            out.append(q)
    return out


def _unrepeated_sections(sections: list[dict]) -> list[dict]:
    """The press release never says a sentence twice: later repeats are dropped, and a paragraph or section left empty goes."""
    flat = [p for sec in sections for p in sec["paragraphs"]]
    cleaned = iter(polish.remove_repeats(flat))
    out = []
    for sec in sections:
        paragraphs = [c for _ in sec["paragraphs"] if (c := next(cleaned)).strip()]
        if paragraphs:
            out.append({**sec, "paragraphs": paragraphs})
    return out


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
            interview_questions=_distinct(draft.interview_questions)[: iv.MAX_QUESTIONS],
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

    plan = saved or default_plan(count, "full")
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
    out: list[dict] = []
    used = 0
    for s in segments:
        if s.kind not in {"intro", "body"}:
            continue
        kept: list[str] = []
        for sentence in s.text.replace("\n", " ").split(". "):
            if not any(ch.isalnum() for ch in sentence):  # blank or stray punctuation: nothing to say
                continue
            n = len(sentence.split())
            if used + n > budget and (kept or out):
                break
            kept.append(sentence.rstrip("."))
            used += n
        if kept:
            out.append({"kind": s.kind, "text": ". ".join(kept).strip() + "."})
    return out


async def press_release_details(session: AsyncSession, project: Project, company: str) -> dict:
    """What the press release needs besides the writing: the dateline (the business's city and country, today's date) and the
    media contact. All of it comes from what was given at sign-up and on the details page; nothing is made up."""
    ws = await session.get(Workspace, project.workspace_id)
    owner = (
        (await session.execute(select(User).where(User.workspace_id == project.workspace_id).order_by(User.created_at)))
        .scalars()
        .first()
    )
    now = datetime.now(UTC)
    place = ", ".join(x.strip() for x in (ws.city if ws else None, ws.country if ws else None) if x and x.strip())
    date = f"{now:%B} {now.day}, {now.year}"
    contact = {
        "name": project.founder_name or "",
        "title": project.founder_title or "",
        "company": company,
        "email": owner.email if owner else "",
        "website": (project.brief.website_url if project.brief else None) or "",
    }
    return {"dateline": f"{place.upper()} — {date}" if place else date, "contact": contact}


async def write_story(
    session: AsyncSession, project: Project, plan_script: ScriptVersion, answers: list[dict]
) -> ScriptVersion:
    """After the interview: the news story + social post + the short presenter script, as an unapproved script version."""
    llm = registry.get_llm()
    facts = {
        **((project.brief.structured_facts if project.brief else None) or {}),
        "founder_name": project.founder_name,
        "founder_title": project.founder_title,
        "website": project.brief.website_url if project.brief else None,
    }
    draft = None
    for attempt in range(2):  # the writer occasionally returns a malformed draft: one more try, then say so plainly
        try:
            draft = await llm.write_story(facts, project.announcement_type or "other", answers)
            break
        except ValidationError:
            if attempt:
                raise HTTPException(
                    502, "We couldn't finish writing your story just now. Please press “Produce my story” again."
                ) from None
    assert draft is not None
    segments = _trim_words(draft.segments, PRESENTER_WORDS)
    if (
        not segments
    ):  # the writer gave no usable opening: build one from the story itself so the presenter always has words
        lead = [draft.dek] + [p for sec in draft.sections[:2] for p in sec.paragraphs[:1]]
        segments = _trim_words([ScriptSegment(kind="intro", text=" ".join(x for x in lead if x))], PRESENTER_WORDS)
    if segments and segments[0]["kind"] != "intro":
        segments[0]["kind"] = "intro"
    segments.append({"kind": "outro", "text": draft.outro.strip() or presenters.STANDARD_OUTRO})
    cleaned = polish.remove_repeats(
        [s["text"] for s in segments]
    )  # nothing said twice, from the opening to the sign-off
    segments = [{**s, "text": t} for s, t in zip(segments, cleaned, strict=True) if t]
    company = str(facts.get("company") or "")
    ws = await session.get(Workspace, project.workspace_id)
    company = company or (ws.name if ws else "")
    sections = _unrepeated_sections([s.model_dump() for s in draft.sections])
    story = {
        **await press_release_details(session, project, company),
        "about": draft.about.strip(),
        "company": company,
        "headline": draft.headline,
        "dek": draft.dek,
        "sections": sections,
        "social": draft.social.model_dump(),
        "unverified": draft.unverified,
        # the headline bar for each answer, keyed by question number (answers arrive in question order)
        "chyrons": {
            str(a.get("index", i)): c for i, (a, c) in enumerate(zip(answers, draft.chyrons, strict=False)) if c
        },
    }
    text = "\n".join(  # one line per piece, so a claim is quoted whole and each sentence is checked on its own
        [s["text"] for s in segments]
        + [draft.headline, draft.dek, draft.about]
        + [p for sec in sections for p in sec["paragraphs"]]
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
