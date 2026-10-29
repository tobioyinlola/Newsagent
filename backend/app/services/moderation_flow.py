"""Glue between moderation verdicts, review cases, and the API. Keeps the routes thin."""

import logging
from datetime import UTC, datetime

from fastapi import HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.integrations import registry
from app.models import ModerationCase, SystemSetting, User
from app.services.moderation import Verdict, excerpt, screen_text
from app.services.notifications import notify_operators, send_email

log = logging.getLogger("moderation")


async def mode(session: AsyncSession) -> str:
    row = await session.get(SystemSetting, "moderation")
    return (row.value.get("mode") if row else None) or "enforce"  # enforce | log_only


async def llm_enabled(session: AsyncSession) -> bool:
    row = await session.get(SystemSetting, "moderation")
    if row and "llm" in row.value:
        return bool(row.value["llm"])
    st = get_settings()
    if st.use_mocks:
        return False
    if st.llm_provider == "openai":
        return bool(st.llm_api_key or st.tts_api_key or st.transcription_api_key)
    return bool(st.anthropic_api_key)


async def evaluate(session: AsyncSession, text: str) -> Verdict:
    v = screen_text(text)
    if await llm_enabled(session) or get_settings().use_mocks:  # the mock LLM always says allow, so this is cheap
        try:
            r = await registry.get_llm().moderate(text)
            v = v.merge(Verdict(r["level"], [f"llm:{x}" for x in r.get("reasons", [])], [], "llm"))
        except Exception:  # noqa: BLE001 - an LLM outage must not make unsafe content publishable: hold for a human
            log.exception("llm moderation failed; holding for review")
            v = v.merge(
                Verdict(
                    "review",
                    ["llm_unavailable"],
                    ["Our automatic check is unavailable, so our team will check this."],
                    "llm",
                )
            )
    return v


async def case_for(session: AsyncSession, project_id: str, stage: str, subject_id: str) -> ModerationCase | None:
    return (
        (
            await session.execute(
                select(ModerationCase)
                .where(
                    ModerationCase.project_id == project_id,
                    ModerationCase.stage == stage,
                    ModerationCase.subject_id == subject_id,
                )
                .order_by(ModerationCase.created_at.desc())
            )
        )
        .scalars()
        .first()
    )


async def enforce(
    session: AsyncSession, *, project_id: str, workspace_id: str, stage: str, subject_id: str, text: str
) -> None:
    """Raise 422 (blocked) or 409 (held for review) unless the content is allowed or an operator approved it."""
    v = await evaluate(session, text)
    if v.level == "allow":
        return
    if v.level == "review" and not get_settings().moderation_hold_for_review:
        log.warning("moderation (no hold): %s %s", stage, v.categories)
        return
    if await mode(session) == "log_only":
        log.warning("moderation (log only): %s %s %s", stage, v.level, v.categories)
        return
    existing = await case_for(session, project_id, stage, subject_id)
    if v.level == "block":
        if existing is None or existing.status != "blocked":
            session.add(
                ModerationCase(
                    project_id=project_id,
                    workspace_id=workspace_id,
                    stage=stage,
                    subject_id=subject_id,
                    status="blocked",
                    reasons=v.categories,
                    excerpt=excerpt(text),
                )
            )
            await session.commit()
        raise HTTPException(
            422,
            {
                "error": "content_blocked",
                "message": " ".join(v.messages) or "This content can't be used.",
                "categories": v.categories,
            },
        )
    # review
    if existing is not None and existing.status == "approved":
        return
    if existing is not None and existing.status == "rejected":
        raise HTTPException(
            422,
            {
                "error": "content_rejected",
                "message": "Our team couldn't approve this content."
                + (f" {existing.note}" if existing.note else "")
                + " Please edit it and try again.",
            },
        )
    if existing is None or existing.status != "pending":
        session.add(
            ModerationCase(
                project_id=project_id,
                workspace_id=workspace_id,
                stage=stage,
                subject_id=subject_id,
                status="pending",
                reasons=v.categories,
                excerpt=excerpt(text),
            )
        )
        await session.commit()
        await notify_operators(
            "Content needs review",
            f"A {stage} is waiting in the review queue ({', '.join(v.categories)}).\n{get_settings().app_base_url}/admin\n",
        )
    raise HTTPException(
        409,
        {
            "error": "in_review",
            "message": "A member of our team is checking this before it is made. This is usually quick; we'll email you.",
            "categories": v.categories,
        },
    )


async def decide(session: AsyncSession, case: ModerationCase, decision: str, note: str, reviewer: str) -> None:
    case.status = "approved" if decision == "approve" else "rejected"
    case.note, case.reviewed_by, case.reviewed_at = note or None, reviewer, datetime.now(UTC)
    emails = (await session.execute(select(User.email).where(User.workspace_id == case.workspace_id))).scalars().all()
    await session.flush()
    if case.status == "approved":
        subject, body = (
            "Your content was approved",
            "Our team approved your content. Open your project and continue where you left off.",
        )
    else:
        subject, body = (
            "We couldn't approve your content",
            "Our team couldn't approve this content." + (f" {note}" if note else "") + " Please edit it and try again.",
        )
    for to in emails:
        await send_email(
            to,
            subject,
            body,
            link=("Open your project", f"{get_settings().app_base_url}/ai-newsroom/{case.project_id}"),
        )
