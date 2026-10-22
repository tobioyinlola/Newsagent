"""Append-only audit trail for operator and sensitive actions."""

from fastapi import Request
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import AuditLog
from app.services.ratelimit import client_ip


def audit(
    session: AsyncSession,
    actor: str,
    action: str,
    *,
    target_type: str | None = None,
    target_id: str | None = None,
    detail: dict | None = None,
    request: Request | None = None,
) -> None:
    """Stage an audit row in the caller's transaction (so the action and its record commit together)."""
    session.add(
        AuditLog(
            actor=actor,
            action=action,
            target_type=target_type,
            target_id=target_id,
            detail=detail or {},
            ip=client_ip(request) if request else None,
        )
    )
