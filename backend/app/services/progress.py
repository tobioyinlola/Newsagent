"""What has been made, what is being made and what is stuck, per piece, for the progress panel."""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Asset, Job, Project, ProviderRequest, ScriptVersion, Take

ACTIVE = {"script_approved", "rendering_anchor", "anchor_ready", "merging"}
PERSON = {"interviewing", "awaiting_founder", "processing_founder"}


@dataclass
class Stage:
    key: str
    label: str
    status: str  # done | working | waiting | pending | failed | paused | cancelled
    detail: str | None = None


async def build(session: AsyncSession, project: Project) -> dict:
    script = (
        (
            await session.execute(
                select(ScriptVersion)
                .where(ScriptVersion.project_id == project.id, ScriptVersion.approved.is_(True))
                .order_by(ScriptVersion.version.desc())
            )
        )
        .scalars()
        .first()
    )
    assets = (await session.execute(select(Asset).where(Asset.project_id == project.id))).scalars().all()
    have = {(a.type, a.format) for a in assets}
    takes = (
        (await session.execute(select(Take).where(Take.project_id == project.id, Take.status != "superseded")))
        .scalars()
        .all()
    )
    jobs = (await session.execute(select(Job).where(Job.project_id == project.id))).scalars().all()
    inflight = {
        r.slot
        for r in (
            await session.execute(
                select(ProviderRequest).where(
                    ProviderRequest.project_id == project.id, ProviderRequest.status == "submitted"
                )
            )
        ).scalars()
    }
    questions = list(script.interview_questions) if script and project.interview_enabled else []
    has_outro = bool(script and any(s.get("kind") == "outro" for s in script.segments)) and project.interview_enabled

    # (key, label, done?, person-driven?)
    plan: list[tuple[str, str, bool, bool]] = [("script", "Script approved", script is not None, False)]
    if project.interview_enabled:
        got = {t.question_index for t in takes if t.status in {"ready", "needs_retake"}}
        plan.append(
            ("interview", f"Interview ({len(got)} of {len(questions)} answers)", len(got) >= len(questions), True)
        )
    plan.append(("presenter", "AI presenter: opening", ("anchor", "main") in have or ("anchor", None) in have, False))
    if has_outro:
        plan.append(("presenter_closing", "AI presenter: closing", ("anchor_outro", "outro") in have, False))
    from app.pipeline.steps import segment_texts  # local import: steps imports services

    parts = segment_texts(script) if script and project.interview_enabled else {}
    for part, label in (("explanation", "AI presenter: explanation"), ("analysis", "AI presenter: analysis")):
        if parts.get(part):
            plan.append((f"presenter_{part}", label, ("anchor", part) in have, False))
    for i in range(len(questions)):
        plan.append((f"question_{i}", f"AI presenter: question {i + 1}", ("question_clip", f"q{i}") in have, False))
    plan.append(("render", "Final video made and checked", project.state == "final_ready", False))

    stages: list[Stage] = []
    blocked = False  # the first unfinished piece takes the project's current condition; later ones are just pending
    for key, label, done, person in plan:
        if done:
            stages.append(Stage(key, label, "done"))
            continue
        if blocked:
            stages.append(Stage(key, label, "pending"))
            continue
        blocked = True
        s = project.state
        if s == "cancelled":
            stages.append(Stage(key, label, "cancelled", "Cancelled. Retry to continue."))
        elif s == "failed":
            stages.append(Stage(key, label, "failed", project.failure_reason))
        elif s == "limit_reached":
            stages.append(Stage(key, label, "paused", project.failure_reason))
        elif person and s in PERSON:
            stages.append(Stage(key, label, "waiting", "Waiting for the founder's answers."))
        elif s in ACTIVE:
            stages.append(Stage(key, label, "working"))
        else:
            stages.append(Stage(key, label, "pending"))
    failed_job = next((j for j in sorted(jobs, key=lambda j: j.created_at, reverse=True) if j.status == "failed"), None)
    done_n = sum(1 for st in stages if st.status == "done")
    return {
        "state": project.state,
        "percent": round(100 * done_n / len(stages)) if stages else 0,
        "stages": [st.__dict__ for st in stages],
        "retryable": project.state in {"failed", "limit_reached", "cancelled"} and project.failure_retryable,
        "cancellable": project.state
        in {
            "script_approved",
            "interviewing",
            "rendering_anchor",
            "anchor_ready",
            "awaiting_founder",
            "processing_founder",
            "merging",
        },
        "failure_category": failed_job.failure_category if failed_job and project.state == "failed" else None,
        "vendor_jobs_in_flight": len(inflight),
    }
