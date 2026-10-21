from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Project
from app.pipeline.queue import enqueue
from app.services import state_machine as sm


async def advance(session: AsyncSession, project_id: str) -> None:
    """Inspect project state and enqueue the next step. Safe to call repeatedly (steps are idempotent)."""
    project = await session.get(Project, project_id)
    if project is None:
        return
    payload = {"project_id": project_id}
    state = project.state
    if state == "script_approved":
        sm.transition(project, "rendering_anchor")
        await session.commit()
        enqueue("anchor_render", payload)
    elif state == "rendering_anchor":
        await session.commit()
        enqueue("anchor_render", payload)
    elif state == "anchor_ready":
        await session.commit()
        enqueue("final_render", payload)
    # awaiting_founder / processing_founder / merging: Phase 2.
