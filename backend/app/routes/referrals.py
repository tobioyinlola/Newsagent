"""The signed-in user's share link, completed referrals and wallet rewards."""

from decimal import Decimal

from fastapi import APIRouter, Depends, HTTPException
from sqlalchemy import func, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import Principal, current_principal
from app.config import get_settings
from app.db import get_session
from app.models import CreditTransaction, ReferralReward, Workspace
from app.services.referrals import ensure_link

router = APIRouter(prefix="/v1/referrals", tags=["referrals"])


@router.get("")
async def overview(p: Principal = Depends(current_principal), db: AsyncSession = Depends(get_session)):
    if p.workspace.suspended or p.workspace.deleted_at:
        raise HTTPException(403, "Referrals are unavailable for this workspace")
    code = await ensure_link(db, p.user)
    count, credits = (
        await db.execute(
            select(func.count(ReferralReward.id), func.coalesce(func.sum(ReferralReward.credits), 0)).where(
                ReferralReward.referrer_user_id == p.user.id
            )
        )
    ).one()
    rows = (
        await db.execute(
            select(ReferralReward, Workspace.name, Workspace.deleted_at)
            .join(Workspace, Workspace.id == ReferralReward.referred_workspace_id)
            .where(ReferralReward.referrer_user_id == p.user.id)
            .order_by(ReferralReward.created_at.desc())
            .limit(100)
        )
    ).all()
    # The bonus for a referred business's first paid distribution is a wallet credit with a known reference per business.
    refs = {f"referral-bonus:{r.referred_workspace_id}": r for r, _, _ in rows}
    bonus_paid = (
        set(
            (
                await db.execute(
                    select(CreditTransaction.ref).where(
                        CreditTransaction.workspace_id == p.workspace.id, CreditTransaction.ref.in_(list(refs))
                    )
                )
            ).scalars()
        )
        if refs
        else set()
    )
    bonus = Decimal(get_settings().referral_distribution_bonus_credits)
    await db.commit()
    return {
        "code": code,
        "url": f"{get_settings().app_base_url.rstrip('/')}/signup?ref={code}",
        "reward_credits": str(Decimal(get_settings().referral_signup_credits)),
        "bonus_credits": str(bonus),
        "completed_referrals": count,
        "earned_credits": str(Decimal(credits) + bonus * len(bonus_paid)),
        "referrals": [
            {
                "id": r.id,
                "business": name if not deleted else "Deleted business",
                "credits": str(r.credits + (bonus if f"referral-bonus:{r.referred_workspace_id}" in bonus_paid else 0)),
                "bonus_earned": f"referral-bonus:{r.referred_workspace_id}" in bonus_paid,
                "status": "credited",
                "created_at": r.created_at,
            }
            for r, name, deleted in rows
        ],
    }
