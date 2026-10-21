"""Owner emails. A failed email must never fail or block the pipeline."""

import logging

from sqlalchemy import select

from app.config import get_settings
from app.db import session_maker
from app.integrations import registry
from app.models import Project, User

log = logging.getLogger("notifications")

MESSAGES = {
    "render_ready": ("Your video is ready", "Your video is ready to download and share."),
    "failed": (
        "We couldn't finish your video",
        "Something went wrong while making your video. Open the project and press Retry. Nothing extra was charged.",
    ),
    "limit_reached": (
        "Your video is paused: limit reached",
        "Your video is paused because a usage limit was reached. Once the limit is raised, press Retry to continue.",
    ),
}


async def notify_owners(project_id: str, kind: str) -> None:
    try:
        subject, body = MESSAGES[kind]
        async with session_maker()() as session:
            project = await session.get(Project, project_id)
            if project is None:
                return
            emails = (
                (await session.execute(select(User.email).where(User.workspace_id == project.workspace_id)))
                .scalars()
                .all()
            )
        link = f"{get_settings().app_base_url}/projects/{project_id}"
        text = f"{body}\n\nOpen your project: {link}\n"
        for to in emails:
            await registry.get_email().send(to, subject, text)
    except Exception:  # noqa: BLE001
        log.exception("notification %s failed for project %s", kind, project_id)
