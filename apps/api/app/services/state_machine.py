from app.models import Project


class IllegalTransition(Exception):
    pass


STATES = {
    "draft",
    "script_ready",
    "script_approved",
    "rendering_anchor",
    "anchor_ready",
    "awaiting_founder",
    "processing_founder",
    "merging",
    "final_ready",
    "failed",
    "limit_reached",
}

ALLOWED: dict[str, set[str]] = {
    "draft": {"script_ready"},
    "script_ready": {"script_ready", "script_approved"},
    "script_approved": {"rendering_anchor"},
    "rendering_anchor": {"anchor_ready"},
    "anchor_ready": {"awaiting_founder", "final_ready"},
    "awaiting_founder": {"processing_founder"},
    "processing_founder": {"merging", "awaiting_founder"},  # retake request goes back
    "merging": {"final_ready"},
    "final_ready": set(),
    "limit_reached": set(),  # resumed explicitly via resume_from_limit
    "failed": set(),  # resumed explicitly via retry
}


def transition(project: Project, to: str) -> None:
    if to == "failed" or to == "limit_reached":
        if project.state in {"final_ready", "failed"}:
            raise IllegalTransition(f"{project.state} -> {to}")
        project.failed_from = project.state
        project.state = to
        return
    if to not in ALLOWED.get(project.state, set()):
        raise IllegalTransition(f"{project.state} -> {to}")
    project.state = to


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
    if project.state not in {"failed", "limit_reached"} or not project.failed_from:
        raise IllegalTransition(f"cannot resume from {project.state}")
    project.state = project.failed_from
    project.failure_reason = None
    project.failed_from = None
