"""Data-subject rights: purge a project, export a workspace's data, delete a workspace, erase a founder's recordings."""

from datetime import UTC, datetime

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.integrations import registry
from app.models import (
    Asset,
    BrandAsset,
    BrandKit,
    Brief,
    Checkout,
    CreditTransaction,
    InterviewSession,
    Invite,
    Job,
    ModerationCase,
    Project,
    ScriptVersion,
    ShareLink,
    Take,
    User,
    Workspace,
)
from app.pipeline.takes import chunk_key

IN_FLIGHT = {"script_approved", "rendering_anchor", "anchor_ready", "merging"}


async def purge_takes(session: AsyncSession, project_id: str, *, keep_rows: bool = False) -> int:
    """Delete a project's founder recordings (raw chunks, processed files, photo). Returns takes removed."""
    storage = registry.get_storage()
    n = 0
    for t in (await session.execute(select(Take).where(Take.project_id == project_id))).scalars():
        for idx in list(t.chunks or {}):
            await storage.delete(chunk_key(project_id, t.id, int(idx)))
        for k in (t.processed_video_key, t.processed_audio_key):
            if k:
                await storage.delete(k)
        n += 1
    for s in (
        await session.execute(select(InterviewSession).where(InterviewSession.project_id == project_id))
    ).scalars():
        if s.photo_key:
            await storage.delete(s.photo_key)
            s.photo_key = None
    if not keep_rows:
        await session.execute(delete(Take).where(Take.project_id == project_id))
        await session.execute(delete(Asset).where(Asset.project_id == project_id, Asset.type == "founder_take"))
    return n


async def purge_project(session: AsyncSession, project: Project) -> None:
    """Remove a project: files first, then every row that belongs to it."""
    storage = registry.get_storage()
    for a in (await session.execute(select(Asset).where(Asset.project_id == project.id))).scalars():
        await storage.delete(a.storage_key)
    await purge_takes(session, project.id)
    for model in (Take, Asset, Job, ScriptVersion, ShareLink, InterviewSession, ModerationCase):
        await session.execute(delete(model).where(model.project_id == project.id))
    await session.execute(delete(Brief).where(Brief.project_id == project.id))
    await session.delete(project)


async def delete_workspace(session: AsyncSession, ws: Workspace) -> None:
    """Erase everything about a workspace except what the law or our books require: the credit ledger and
    checkouts stay (financial records) but no longer point at a named customer; the audit log stays."""
    storage = registry.get_storage()
    for p in (await session.execute(select(Project).where(Project.workspace_id == ws.id))).scalars().all():
        await purge_project(session, p)
    for a in (await session.execute(select(BrandAsset).where(BrandAsset.workspace_id == ws.id))).scalars():
        await storage.delete(a.key)
    await session.execute(delete(BrandAsset).where(BrandAsset.workspace_id == ws.id))
    ws.brand_kit_id = None
    await session.execute(delete(BrandKit).where(BrandKit.workspace_id == ws.id))
    await session.execute(delete(Invite).where(Invite.workspace_id == ws.id))
    await session.execute(delete(User).where(User.workspace_id == ws.id))
    await session.execute(delete(ModerationCase).where(ModerationCase.workspace_id == ws.id))
    ws.name, ws.suspended, ws.deleted_at = f"deleted-{ws.id[:8]}", True, datetime.now(UTC)


async def export_workspace(session: AsyncSession, ws: Workspace, user: User) -> dict:
    """Everything we hold about this workspace, as JSON (media is listed as short-lived download links)."""
    storage = registry.get_storage()

    def dt(x):
        return x.isoformat() if x else None

    projects = []
    for p in (
        await session.execute(select(Project).where(Project.workspace_id == ws.id).order_by(Project.created_at))
    ).scalars():
        brief = (await session.execute(select(Brief).where(Brief.project_id == p.id))).scalar_one_or_none()
        scripts = (
            (
                await session.execute(
                    select(ScriptVersion).where(ScriptVersion.project_id == p.id).order_by(ScriptVersion.version)
                )
            )
            .scalars()
            .all()
        )
        sessions = (
            (await session.execute(select(InterviewSession).where(InterviewSession.project_id == p.id))).scalars().all()
        )
        takes = (
            (await session.execute(select(Take).where(Take.project_id == p.id).order_by(Take.created_at)))
            .scalars()
            .all()
        )
        assets = (await session.execute(select(Asset).where(Asset.project_id == p.id))).scalars().all()
        projects.append(
            {
                "id": p.id,
                "state": p.state,
                "created_at": dt(p.created_at),
                "completed_at": dt(p.completed_at),
                "voice_accent": p.voice_accent,
                "interview": p.interview_enabled,
                "cost_total": str(p.cost_total),
                "brief": {"text": brief.raw_text, "website": brief.website_url} if brief else None,
                "scripts": [
                    {
                        "version": s.version,
                        "segments": s.segments,
                        "ticker_lines": s.ticker_lines,
                        "lower_thirds": s.lower_thirds,
                        "interview_questions": s.interview_questions,
                        "approved": s.approved,
                        "approved_by": s.approved_by,
                        "approved_at": dt(s.approved_at),
                    }
                    for s in scripts
                ],
                "founder_interviews": [
                    {
                        "founder_name": s.founder_name,
                        "founder_title": s.founder_title,
                        "founder_email": s.founder_email,
                        "invited_at": dt(s.invited_at),
                        "consent_at": dt(s.consent_at),
                        "consent_version": s.consent_version,
                        "submitted_at": dt(s.submitted_at),
                    }
                    for s in sessions
                ],
                "founder_answers": [
                    {
                        "question": t.question_index,
                        "status": t.status,
                        "duration_s": str(t.duration_s) if t.duration_s else None,
                        "transcript": t.transcript,
                        "raw_deleted_at": dt(t.raw_deleted_at),
                    }
                    for t in takes
                ],
                "files": [
                    {"type": a.type, "format": a.format, "download_url": storage.presign_get(a.storage_key, 3600)}
                    for a in assets
                    if a.type in {"render", "thumbnail", "caption", "preview"}
                ],
            }
        )
    ledger_rows = (
        (
            await session.execute(
                select(CreditTransaction)
                .where(CreditTransaction.workspace_id == ws.id)
                .order_by(CreditTransaction.created_at)
            )
        )
        .scalars()
        .all()
    )
    checkouts = (await session.execute(select(Checkout).where(Checkout.workspace_id == ws.id))).scalars().all()
    kits = (
        (await session.execute(select(BrandKit).where(BrandKit.workspace_id == ws.id).order_by(BrandKit.version)))
        .scalars()
        .all()
    )
    return {
        "exported_at": datetime.now(UTC).isoformat(),
        "account": {"email": user.email, "role": user.role, "created_at": dt(user.created_at)},
        "workspace": {
            "id": ws.id,
            "name": ws.name,
            "region": ws.region,
            "plan": ws.plan,
            "credit_balance": str(ws.credit_balance),
        },
        "brand_kits": [
            {
                "version": k.version,
                "primary_color": k.primary_color,
                "accent_color": k.accent_color,
                "tone": k.tone,
                "fonts": k.fonts,
                "pronunciation_glossary": k.pronunciation_glossary,
                "source_url": k.source_url,
            }
            for k in kits
        ],
        "projects": projects,
        "credit_ledger": [
            {
                "at": dt(t.created_at),
                "kind": t.kind,
                "credits": str(t.amount),
                "balance_after": str(t.balance_after),
                "project_id": t.project_id,
                "stage": t.stage,
                "description": t.description,
            }
            for t in ledger_rows
        ],
        "purchases": [
            {
                "id": c.id,
                "credits": str(c.credits),
                "usd": str(c.amount_usd),
                "status": c.status,
                "paid_at": dt(c.paid_at),
            }
            for c in checkouts
        ],
    }
