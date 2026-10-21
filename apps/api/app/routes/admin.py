import secrets
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import Principal, operator
from app.db import get_session
from app.models import Invite, Workspace
from app.schemas.api import InviteCreate, InviteOut, VendorBudgetSet, WorkspacePatch
from app.services.spend_guard import ensure_vendor_budget

router = APIRouter(prefix="/v1/admin", tags=["admin"])


@router.post("/invites", response_model=InviteOut)
async def create_invite(
    body: InviteCreate, _: Principal = Depends(operator), session: AsyncSession = Depends(get_session)
) -> InviteOut:
    ws = Workspace(name=body.workspace_name, credit_balance=body.credits, spend_cap=body.spend_cap)
    session.add(ws)
    await session.flush()
    inv = Invite(
        email=body.email.lower(),
        code=secrets.token_urlsafe(24),
        workspace_id=ws.id,
        expires_at=datetime.now(UTC) + timedelta(days=14),
    )
    session.add(inv)
    await session.commit()
    return InviteOut(code=inv.code, workspace_id=ws.id, expires_at=inv.expires_at)


@router.patch("/workspaces/{workspace_id}")
async def patch_workspace(
    workspace_id: str,
    body: WorkspacePatch,
    _: Principal = Depends(operator),
    session: AsyncSession = Depends(get_session),
) -> dict:
    ws = await session.get(Workspace, workspace_id)
    if ws is None:
        raise HTTPException(404, "Workspace not found")
    for k, v in body.model_dump(exclude_none=True).items():
        setattr(ws, k, v)
    await session.commit()
    return {"ok": True}


@router.put("/vendor-budgets")
async def set_vendor_budget(
    body: VendorBudgetSet, _: Principal = Depends(operator), session: AsyncSession = Depends(get_session)
) -> dict:
    await ensure_vendor_budget(session, body.vendor, body.limit)
    await session.commit()
    return {"ok": True}
