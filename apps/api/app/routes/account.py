"""Account-level privacy rights for the workspace owner: export all data, delete the workspace."""

from fastapi import APIRouter, Depends, HTTPException, Request
from pydantic import BaseModel
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import Principal, current_principal
from app.db import get_session
from app.models import Project
from app.services import privacy
from app.services.audit import audit
from app.services.notifications import send_email
from app.services.ratelimit import limit

router = APIRouter(prefix="/v1/account", tags=["account"])


class DeleteAccountIn(BaseModel):
    confirm: str  # must equal "DELETE <workspace name>"


@router.get("/export", dependencies=[Depends(limit("export", 5, 86400))])
async def export_data(
    request: Request, p: Principal = Depends(current_principal), session: AsyncSession = Depends(get_session)
) -> dict:
    data = await privacy.export_workspace(session, p.workspace, p.user)
    audit(session, p.user.email, "account.export", target_type="workspace", target_id=p.workspace.id, request=request)
    await session.commit()
    return data


@router.delete("", dependencies=[Depends(limit("account-delete", 3, 86400))])
async def delete_account(
    body: DeleteAccountIn,
    request: Request,
    p: Principal = Depends(current_principal),
    session: AsyncSession = Depends(get_session),
) -> dict:
    if p.user.role != "owner":
        raise HTTPException(403, "Only the workspace owner can delete it")
    if body.confirm.strip() != f"DELETE {p.workspace.name}":
        raise HTTPException(
            422, {"error": "confirmation_mismatch", "message": f'Type "DELETE {p.workspace.name}" to confirm.'}
        )
    busy = (
        await session.execute(
            select(Project.id).where(Project.workspace_id == p.workspace.id, Project.state.in_(privacy.IN_FLIGHT))
        )
    ).first()
    if busy:
        raise HTTPException(409, "A video is being made. Please wait for it to finish, then try again.")
    email, wid = p.user.email, p.workspace.id
    audit(
        session, email, "account.delete", target_type="workspace", target_id=wid, request=request
    )  # kept: who deleted what, when
    await privacy.delete_workspace(session, p.workspace)
    await session.commit()
    await send_email(
        email,
        "Your workspace was deleted",
        "Your workspace and everything in it have been permanently deleted. Billing records are kept as required by law.\n",
    )
    return {"ok": True}
