import secrets
from datetime import UTC, datetime, timedelta
from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import Principal, operator
from app.db import get_session
from app.models import CreditPack, Invite, VendorBudget, Workspace
from app.schemas.api import (
    InviteCreate,
    InviteOut,
    ManualCreditsIn,
    PackIn,
    PackOut,
    PackPatch,
    VendorBudgetOut,
    VendorBudgetSet,
    WorkspaceAdminOut,
    WorkspacePatch,
)
from app.services import ledger
from app.services.audit import audit
from app.services.spend_guard import ensure_vendor_budget

router = APIRouter(prefix="/v1/admin", tags=["admin"])


@router.post("/invites", response_model=InviteOut)
async def create_invite(
    body: InviteCreate,
    request: Request,
    op: Principal = Depends(operator),
    session: AsyncSession = Depends(get_session),
) -> InviteOut:
    ws = Workspace(name=body.workspace_name, credit_balance=Decimal("0"), spend_cap=body.spend_cap)
    session.add(ws)
    await session.flush()
    if body.credits:
        await ledger.apply(
            session, ws, body.credits, "grant", description=f"Starting credits (invited by {op.user.email})"
        )
    inv = Invite(
        email=body.email.lower(),
        code=secrets.token_urlsafe(24),
        workspace_id=ws.id,
        expires_at=datetime.now(UTC) + timedelta(days=14),
    )
    session.add(inv)
    audit(
        session,
        op.user.email,
        "invite.create",
        target_type="workspace",
        target_id=ws.id,
        detail={"email": inv.email, "credits": str(body.credits)},
        request=request,
    )
    await session.commit()
    return InviteOut(code=inv.code, workspace_id=ws.id, expires_at=inv.expires_at)


@router.patch("/workspaces/{workspace_id}")
async def patch_workspace(
    workspace_id: str,
    body: WorkspacePatch,
    request: Request,
    op: Principal = Depends(operator),
    session: AsyncSession = Depends(get_session),
) -> dict:
    ws = await session.get(Workspace, workspace_id)
    if ws is None:
        raise HTTPException(404, "Workspace not found")
    changes = body.model_dump(exclude_none=True)
    target = changes.pop("credit_balance", None)
    if target is not None:  # a balance edit is an adjustment in the ledger, never a silent overwrite
        delta = Decimal(target) - ws.credit_balance
        if delta:
            await ledger.apply(session, ws, delta, "adjustment", description=f"Operator adjustment by {op.user.email}")
    for k, v in changes.items():
        setattr(ws, k, v)
    audit(
        session,
        op.user.email,
        "workspace.update",
        target_type="workspace",
        target_id=ws.id,
        detail={
            **{k: str(v) for k, v in changes.items()},
            **({"credit_balance": str(target)} if target is not None else {}),
        },
        request=request,
    )
    await session.commit()
    return {"ok": True}


@router.put("/vendor-budgets")
async def set_vendor_budget(
    body: VendorBudgetSet,
    request: Request,
    op: Principal = Depends(operator),
    session: AsyncSession = Depends(get_session),
) -> dict:
    await ensure_vendor_budget(session, body.vendor, body.limit)
    audit(
        session,
        op.user.email,
        "vendor_budget.set",
        target_type="vendor",
        target_id=body.vendor,
        detail={"limit": str(body.limit)},
        request=request,
    )
    await session.commit()
    return {"ok": True}


@router.get("/workspaces", response_model=list[WorkspaceAdminOut])
async def list_workspaces(
    _: Principal = Depends(operator), session: AsyncSession = Depends(get_session)
) -> list[Workspace]:
    rows = await session.execute(select(Workspace).order_by(Workspace.created_at.desc()).limit(200))
    return list(rows.scalars().all())


@router.get("/vendor-budgets", response_model=list[VendorBudgetOut])
async def list_vendor_budgets(
    _: Principal = Depends(operator), session: AsyncSession = Depends(get_session)
) -> list[VendorBudget]:
    rows = await session.execute(select(VendorBudget).order_by(VendorBudget.period.desc(), VendorBudget.vendor))
    return list(rows.scalars().all())


@router.get("/packs", response_model=list[PackOut])
async def admin_packs(
    _: Principal = Depends(operator), session: AsyncSession = Depends(get_session)
) -> list[CreditPack]:
    return list((await session.execute(select(CreditPack).order_by(CreditPack.price_usd))).scalars().all())


@router.post("/packs", response_model=PackOut)
async def create_pack(
    body: PackIn, request: Request, op: Principal = Depends(operator), session: AsyncSession = Depends(get_session)
) -> CreditPack:
    pack = CreditPack(name=body.name, credits=body.credits, price_usd=body.price_usd)
    session.add(pack)
    await session.flush()
    audit(
        session,
        op.user.email,
        "pack.create",
        target_type="pack",
        target_id=pack.id,
        detail={"credits": str(body.credits), "price_usd": str(body.price_usd)},
        request=request,
    )
    await session.commit()
    return pack


@router.patch("/packs/{pack_id}")
async def patch_pack(
    pack_id: str,
    body: PackPatch,
    request: Request,
    op: Principal = Depends(operator),
    session: AsyncSession = Depends(get_session),
) -> dict:
    pack = await session.get(CreditPack, pack_id)
    if pack is None:
        raise HTTPException(404, "Pack not found")
    pack.active = body.active
    audit(
        session,
        op.user.email,
        "pack.update",
        target_type="pack",
        target_id=pack_id,
        detail={"active": body.active},
        request=request,
    )
    await session.commit()
    return {"ok": True}


@router.post("/workspaces/{workspace_id}/credits")
async def add_credits(
    workspace_id: str,
    body: ManualCreditsIn,
    request: Request,
    op: Principal = Depends(operator),
    session: AsyncSession = Depends(get_session),
) -> dict:
    """Record an offline payment (bank transfer, invoice). `ref` makes a double submit harmless."""
    ws = await session.get(Workspace, workspace_id)
    if ws is None:
        raise HTTPException(404, "Workspace not found")
    tx = await ledger.apply(
        session,
        ws,
        body.credits,
        "purchase",
        ref=f"manual:{body.ref}",
        description=f"Manual purchase: {body.note or body.ref} (recorded by {op.user.email})",
    )
    if tx is None:
        return {"ok": True, "duplicate": True}
    audit(
        session,
        op.user.email,
        "credits.manual",
        target_type="workspace",
        target_id=ws.id,
        detail={"credits": str(body.credits), "ref": body.ref},
        request=request,
    )
    await session.commit()
    return {"ok": True, "duplicate": False, "balance": str(ws.credit_balance)}
