"""Periodic jobs (Celery beat): founder reminders, link expiry, raw-take retention, stuck-take sweeper."""

import logging
from datetime import UTC, datetime, timedelta

from sqlalchemy import or_, select

from app.config import get_settings
from app.db import session_maker
from app.integrations import registry
from app.models import InterviewSession, Job, Project, Take
from app.pipeline.steps import approved_script
from app.pipeline.takes import chunk_key, requeue_stuck
from app.services import crypto
from app.services import interview as iv
from app.services import state_machine as sm
from app.services.notifications import email_founder_invite

log = logging.getLogger("jobs")


def reminder_days() -> list[int]:
    return sorted(int(x) for x in get_settings().interview_reminder_days.split(",") if x.strip())


async def send_due_reminders(now: datetime | None = None) -> int:
    """Email founders who haven't submitted. Idempotent: reminders_sent only moves forward, and a long outage
    sends one reminder rather than a burst."""
    now = now or datetime.now(UTC)
    days = reminder_days()
    sent = 0
    async with session_maker()() as s:
        rows = (
            await s.execute(
                select(InterviewSession).where(
                    InterviewSession.revoked_at.is_(None),
                    InterviewSession.submitted_at.is_(None),
                    InterviewSession.founder_email.is_not(None),
                    InterviewSession.token_enc.is_not(None),
                )
            )
        ).scalars()
        for sess in rows:
            if iv.is_expired(sess.expiry, now) or sess.invited_at is None:
                continue
            project = await s.get(Project, sess.project_id)
            if project is None or project.state != "awaiting_founder":
                continue
            invited = sess.invited_at if sess.invited_at.tzinfo else sess.invited_at.replace(tzinfo=UTC)
            due = sum(1 for d in days if now >= invited + timedelta(days=d))
            if due <= sess.reminders_sent:
                continue
            script = await approved_script(s, project.id)
            company = (script.lower_thirds[0].get("title") if script.lower_thirds else "") or "your startup"
            left = max(1, (sess.expiry.replace(tzinfo=UTC) - now).days)
            ok = await email_founder_invite(
                sess.founder_email or "",
                sess.founder_name,
                company,
                crypto.decrypt(sess.token_enc or ""),
                left,
                reminder=True,
            )
            if ok:  # a failed send is retried on the next run
                sess.reminders_sent, sess.last_reminder_at = due, now
                sent += 1
        await s.commit()
    return sent


async def expire_sessions(now: datetime | None = None) -> int:
    """Drop the stored (encrypted) token once a link has expired; the hash alone can't re-create the link."""
    now = now or datetime.now(UTC)
    n = 0
    async with session_maker()() as s:
        for sess in (
            await s.execute(select(InterviewSession).where(InterviewSession.token_enc.is_not(None)))
        ).scalars():
            if iv.is_expired(sess.expiry, now):
                sess.token_enc = None
                n += 1
        await s.commit()
    return n


async def purge_old_raw_takes(now: datetime | None = None) -> int:
    """Delete founder raw chunks N days after the project finished, unless the owner chose to keep them."""
    now = now or datetime.now(UTC)
    cutoff = now - timedelta(days=get_settings().raw_take_retention_days)
    storage = registry.get_storage()
    purged = 0
    async with session_maker()() as s:
        projects = (
            await s.execute(
                select(Project).where(
                    Project.completed_at.is_not(None), Project.completed_at <= cutoff, Project.keep_raw_takes.is_(False)
                )
            )
        ).scalars()
        for project in projects:
            for t in (
                await s.execute(select(Take).where(Take.project_id == project.id, Take.raw_deleted_at.is_(None)))
            ).scalars():
                for idx in list(t.chunks or {}):
                    await storage.delete(chunk_key(project.id, t.id, int(idx)))
                t.chunks, t.raw_deleted_at = {}, now
                purged += 1
        await s.commit()
    return purged


STUCK_AFTER = timedelta(minutes=20)


def _aware(t: datetime) -> datetime:
    return t if t.tzinfo else t.replace(tzinfo=UTC)


async def reconcile_projects(now: datetime | None = None) -> int:
    """Re-drive projects the pipeline should be moving but isn't (a worker crashed, a queue message was lost, the
    process restarted). Safe to run any time: steps are idempotent and a fresh running job is left alone."""
    from app.pipeline.advance import advance

    now = now or datetime.now(UTC)
    cutoff = now - STUCK_AFTER
    from app.pipeline.runner import lease_for

    fixed: list[str] = []
    async with session_maker()() as s:
        # two queries for all stuck candidates (not one or two per project): those that have sat in an active step past the cutoff
        stale = or_(Project.state_changed_at.is_(None), Project.state_changed_at < cutoff)
        candidates = (
            await s.execute(
                select(Project.id, Project.state_changed_at, Project.created_at).where(
                    Project.state.in_(sm.ACTIVE), stale
                )
            )
        ).all()
        from app.models import WorkItem
        from app.services import work_queue

        in_line = (  # the dispatcher looks after these (when it is switched off, the sweep does)
            set((await s.execute(select(WorkItem.project_id))).scalars()) if work_queue.enabled() else set()
        )
        ids = [
            pid for pid, changed, created in candidates if pid not in in_line and _aware(changed or created) <= cutoff
        ]
        alive: set[str] = set()
        for i in range(0, len(ids), 500):
            rows = (
                await s.execute(
                    select(Job.project_id, Job.stage, Job.started_at).where(
                        Job.project_id.in_(ids[i : i + 500]), Job.status == "running"
                    )
                )
            ).all()
            alive |= {
                pid for pid, stage, started in rows if started and now - _aware(started) < lease_for(stage)
            }  # a worker still owns it
        fixed = [pid for pid in ids if pid not in alive]
    for pid in fixed:
        async with session_maker()() as s:
            log.warning("re-driving a stuck project", extra={"project_id": pid})
            await advance(s, pid)
    return len(fixed)


async def _requeue_outreach() -> int:
    from app.services import outreach, outreach_agent

    return await outreach_agent.requeue_unprocessed() if outreach.enabled() else 0


async def run_sweep() -> dict:
    """Every few minutes: re-send work whose queue message was lost (broker restart, failed publish, killed worker)."""
    from app.services.distribution import retry_confirmations
    from app.services.payments import reconcile_pending
    from app.services.transfer_reviews import deliver_notifications

    return {
        "stuck_projects": await reconcile_projects(),
        "requeued": await requeue_stuck(),
        "distribution_emails": await retry_confirmations(),
        "payments_reconciled": await reconcile_pending(),
        "transfer_emails": await deliver_notifications(),
        "outreach_replies_requeued": await _requeue_outreach(),
    }


async def run_hourly() -> dict:
    return {
        "stuck_projects": await reconcile_projects(),
        "reminders": await send_due_reminders(),
        "expired": await expire_sessions(),
        "requeued": await requeue_stuck(),
    }


async def run_daily() -> dict:
    from app.services.analytics import prune_events
    from app.services.site_visits import prune_marks

    return {
        "purged_takes": await purge_old_raw_takes(),
        "analytics_session_markers_pruned": await prune_events(),
        "site_visit_markers_pruned": await prune_marks(),
    }
