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
    "ready_to_invite": (
        "Your founder interview is ready to send",
        "The anchor's questions are ready. Open the project to create the private link for your founder.",
    ),
    "founder_submitted": (
        "Your founder has submitted their answers",
        "Your founder finished recording. Open the project to review the answers, choose a layout, and make the final video.",
    ),
    "limit_reached": (
        "Your video is paused: limit reached",
        "Your video is paused because a usage limit was reached. Once the limit is raised, press Retry to continue.",
    ),
}


async def send_email(to: str, subject: str, text: str) -> bool:
    """Send one email; never raises (a failed email must not break a pipeline or request)."""
    try:
        await registry.get_email().send(to, subject, text)
        return True
    except Exception:  # noqa: BLE001
        log.exception("email to a recipient failed: %s", subject)
        return False


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


_pending: set = set()


async def notify_operators(subject: str, text: str) -> None:
    try:
        ops = [e.strip() for e in get_settings().operator_emails.split(",") if e.strip()]
        for to in ops:
            await registry.get_email().send(to, subject, text)
        if not ops:
            log.warning("operator alert with no OPERATOR_EMAILS configured: %s", subject)
    except Exception:  # noqa: BLE001
        log.exception("operator notification failed: %s", subject)


def vendor_budget_alert(vendor: str, period: str, spent, limit) -> None:
    """Sync callback for SpendGuard; schedules the email without blocking the paid step."""
    import asyncio

    task = asyncio.get_running_loop().create_task(
        notify_operators(
            f"Budget alert: {vendor} at 80% for {period}",
            f"The {vendor} budget for {period} has reached {spent} of {limit}. "
            "Raise the limit in the operator console or expect steps to be refused at 100%.",
        )
    )
    _pending.add(task)  # keep a reference so the task isn't garbage collected mid-flight
    task.add_done_callback(_pending.discard)


def founder_link(token: str) -> str:
    return f"{get_settings().app_base_url}/i/{token}"


async def email_founder_invite(
    to: str, founder_name: str, company: str, token: str, days: int, reminder: bool = False
) -> bool:
    link = founder_link(token)
    subject = ("Reminder: " if reminder else "") + f"Record your interview for {company}"
    text = (
        f"Hi {founder_name or 'there'},\n\n"
        f"{company} is being featured in a short news-style video with an AI-generated anchor, and you have been "
        "asked to answer a few questions on camera.\n\n"
        "It takes about 10 minutes on your phone or computer. You can re-record any answer.\n\n"
        f"Your private link (no account needed, expires in {days} days):\n{link}\n\n"
        "If the button or link doesn't open, copy it into your browser. Please don't forward it: it is just for you.\n"
    )
    return await send_email(to, subject, text)


async def email_founder_retake(to: str, founder_name: str, company: str, token: str, note: str) -> bool:
    text = (
        f"Hi {founder_name or 'there'},\n\nThe team at {company} would like you to re-record an answer. {note}\n\n"
        f"Your private link:\n{founder_link(token)}\n"
    )
    return await send_email(to, f"Please re-record an answer for {company}", text)
