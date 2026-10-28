from datetime import UTC, datetime

from app.models import Project


class IllegalTransition(Exception):
    pass


STATES = {
    "draft",
    "script_ready",
    "script_approved",
    "interviewing",
    "rendering_anchor",
    "anchor_ready",
    "awaiting_founder",
    "processing_founder",
    "merging",
    "final_ready",
    "failed",
    "limit_reached",
    "cancelled",
}

ALLOWED: dict[str, set[str]] = {
    "draft": {"script_ready"},
    "script_ready": {
        "script_ready",
        "script_approved",
        "interviewing",
    },  # guided: back to the interview to change answers
    "script_approved": {"rendering_anchor", "interviewing"},
    # live interview: the owner is interviewed first; proceeding starts the paid pipeline
    # guided flow: answering the interview leads to the written story (script_ready), which the owner reviews
    "interviewing": {"rendering_anchor", "script_ready"},
    "rendering_anchor": {"anchor_ready"},
    "anchor_ready": {"awaiting_founder", "final_ready", "merging"},  # merging: live interview already recorded
    # awaiting_founder -> merging is the owner choosing to skip the interview (anchor-only cut)
    "awaiting_founder": {"processing_founder", "merging"},
    "processing_founder": {"merging", "awaiting_founder"},  # retake request goes back
    "merging": {"final_ready"},
    "final_ready": {"rendering_anchor"},  # revising a finished video re-makes only what changed
    "limit_reached": set(),  # resumed explicitly via resume_from_limit
    "failed": set(),  # resumed explicitly via retry
    "cancelled": set(),  # the owner stopped it; resumed explicitly via retry
}

# States where work is in flight or waiting on a person, so an owner may cancel
CANCELLABLE = {
    "script_approved",
    "interviewing",
    "rendering_anchor",
    "anchor_ready",
    "awaiting_founder",
    "processing_founder",
    "merging",
}
# States where the pipeline itself should be making progress (a person is not the one we are waiting for)
ACTIVE = {"script_approved", "rendering_anchor", "anchor_ready", "merging"}


def transition(project: Project, to: str) -> None:
    if to in {"failed", "limit_reached", "cancelled"}:
        if project.state in {"final_ready", "failed", "cancelled"}:
            raise IllegalTransition(f"{project.state} -> {to}")
        if to == "cancelled" and project.state not in CANCELLABLE:
            raise IllegalTransition(f"{project.state} -> {to}")
        project.failed_from = project.state
        project.state = to
        project.state_changed_at = datetime.now(UTC)
        return
    if to not in ALLOWED.get(project.state, set()):
        raise IllegalTransition(f"{project.state} -> {to}")
    project.state = to
    project.state_changed_at = datetime.now(UTC)


def fail(project: Project, reason: str, retryable: bool) -> None:
    transition(project, "failed")
    project.failure_reason = reason
    project.failure_retryable = retryable


def limit_reached(project: Project, reason: str) -> None:
    transition(project, "limit_reached")
    project.failure_reason = reason
    project.failure_retryable = True


def resume(project: Project) -> None:
    """Return a failed/limit_reached project to the state it was in, so advance() re-runs the step."""
    if project.state not in {"failed", "limit_reached", "cancelled"} or not project.failed_from:
        raise IllegalTransition(f"cannot resume from {project.state}")
    project.state = project.failed_from
    project.state_changed_at = datetime.now(UTC)
    project.failure_reason = None
    project.failed_from = None
