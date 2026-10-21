from datetime import UTC, datetime

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import Principal, current_principal, verified_email
from app.db import get_session
from app.models import BrandKit, Invite, User, Workspace
from app.schemas.api import MeOut, RedeemInvite
from app.services.ratelimit import limit

router = APIRouter(prefix="/v1", tags=["auth"])


@router.post("/auth/redeem", response_model=MeOut, dependencies=[Depends(limit("auth", 10, 600))])
async def redeem(
    body: RedeemInvite, email: str = Depends(verified_email), session: AsyncSession = Depends(get_session)
) -> MeOut:
    inv = (await session.execute(select(Invite).where(Invite.code == body.code))).scalar_one_or_none()
    now = datetime.now(UTC)
    if inv is None or inv.used_at is not None or inv.email.lower() != email or inv.expires_at.replace(tzinfo=UTC) < now:
        raise HTTPException(400, "Invite is invalid or expired")
    ws = await session.get(Workspace, inv.workspace_id)
    assert ws is not None
    session.add(User(email=email, role="owner", workspace_id=ws.id))  # type: ignore[union-attr]
    kit = BrandKit(workspace_id=ws.id)  # type: ignore[union-attr]  # neutral fallback kit (spec section 10)
    session.add(kit)
    await session.flush()
    ws.brand_kit_id = kit.id  # type: ignore[union-attr]
    inv.used_at = now
    await session.commit()
    return MeOut(
        email=email,
        workspace_id=ws.id,
        workspace_name=ws.name,  # type: ignore[union-attr]
        credit_balance=ws.credit_balance,
        is_operator=False,
    )  # type: ignore[union-attr]


@router.get("/me", response_model=MeOut)
async def me(p: Principal = Depends(current_principal)) -> MeOut:
    return MeOut(
        email=p.user.email,
        workspace_id=p.workspace.id,
        workspace_name=p.workspace.name,
        credit_balance=p.workspace.credit_balance,
        is_operator=p.is_operator,
    )
