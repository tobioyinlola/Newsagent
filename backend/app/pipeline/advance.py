from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Asset, Project
from app.pipeline import steps
from app.services import state_machine as sm
from app.services import work_queue
from app.services.notifications import notify_owners


async def advance(session: AsyncSession, project_id: str) -> None:
    """Inspect project state and enqueue the next step. Safe to call repeatedly (steps are idempotent)."""
    project = await session.get(Project, project_id)
    if project is None:
        return
    state = project.state
    if (
        state == "script_approved"
        and project.interview_enabled
        and project.interview_mode == "live"
        and project.flow != "guided"
    ):
        sm.transition(project, "interviewing")  # nothing paid runs until the owner has been interviewed and proceeds
        await session.commit()
    elif state == "script_approved":
        sm.transition(project, "rendering_anchor")
        await session.commit()
        await work_queue.submit(session, "anchor_render", project_id)
    elif state == "rendering_anchor":
        await session.commit()
        await work_queue.submit(session, "anchor_render", project_id)
    elif state == "anchor_ready" and project.interview_enabled:
        if await steps.question_clips_complete(session, project):
            if project.interview_mode == "live" or await steps.answers_recorded(session, project):
                sm.transition(project, "merging")  # the interview is already recorded: put the video together
                await session.commit()
                await work_queue.submit(session, "merge_render", project_id)
                return
            sm.transition(project, "awaiting_founder")  # the owner now invites the founder
            await session.commit()
            await notify_owners(project_id, "ready_to_invite")
        else:
            await session.commit()
            await work_queue.submit(session, "question_clips", project_id)
    elif state == "merging":
        await session.commit()
        await work_queue.submit(session, "merge_render", project_id)
    elif state == "anchor_ready":
        await session.commit()
        has_preview = (
            await session.execute(select(Asset.id).where(Asset.project_id == project_id, Asset.type == "preview"))
        ).first()
        await work_queue.submit(session, "final_render" if has_preview else "preview_render", project_id)
    # awaiting_founder / processing_founder wait for the founder and the owner (API calls drive them).
