"""Attribution is carried by the emailed signup code; reward and signup commit together."""

import re
import secrets
from decimal import Decimal

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import ReferralLink, ReferralReward, User, Workspace
from app.models.base import utcnow
from app.services import ledger
from app.services.audit import audit


async def ensure_link(db: AsyncSession, user: User) -> str:
    insert = pg_insert if db.get_bind().dialect.name == "postgresql" else sqlite_insert
    for _ in range(3):
        await db.execute(
            insert(ReferralLink)
            .values(code=secrets.token_urlsafe(18), user_id=user.id, created_at=utcnow())
            .on_conflict_do_nothing()
        )
        code = (await db.execute(select(ReferralLink.code).where(ReferralLink.user_id == user.id))).scalar_one_or_none()
        if code:
            return code
    raise RuntimeError("Could not allocate referral code")


async def resolve(db: AsyncSession, code: str | None) -> User | None:
    if not code or not re.fullmatch(r"[A-Za-z0-9_-]{24}", code):
        return None
    return (
        await db.execute(
            select(User)
            .join(ReferralLink, ReferralLink.user_id == User.id)
            .join(Workspace, Workspace.id == User.workspace_id)
            .where(ReferralLink.code == code, Workspace.deleted_at.is_(None), Workspace.suspended.is_(False))
        )
    ).scalar_one_or_none()


async def reward(db: AsyncSession, code: str | None, new_user: User) -> bool:
    referrer = await resolve(db, code)
    if (
        not referrer
        or referrer.email.lower() == new_user.email.lower()
        or referrer.workspace_id == new_user.workspace_id
    ):
        return False
    # Serialize all awards to this wallet, including simultaneous different signups.
    workspace = (
        await db.execute(
            update(Workspace)
            .where(
                Workspace.id == referrer.workspace_id, Workspace.deleted_at.is_(None), Workspace.suspended.is_(False)
            )
            .values(credit_balance=Workspace.credit_balance)
            .returning(Workspace)
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()
    if workspace is None:
        return False
    if (
        await db.execute(select(ReferralReward.id).where(ReferralReward.referred_workspace_id == new_user.workspace_id))
    ).first():
        return False
    amount = Decimal("1")
    tx = await ledger.apply(
        db,
        workspace,
        amount,
        "grant",
        ref=f"referral:{new_user.workspace_id}",
        description="Referral reward: verified new business signup",
    )
    if tx is None:
        return False
    db.add(
        ReferralReward(
            referrer_user_id=referrer.id,
            referrer_workspace_id=workspace.id,
            referred_user_id=new_user.id,
            referred_workspace_id=new_user.workspace_id,
            credits=amount,
        )
    )
    audit(
        db,
        "referral-service",
        "referral.rewarded",
        target_type="workspace",
        target_id=workspace.id,
        detail={
            "referrer_user_id": referrer.id,
            "referred_workspace_id": new_user.workspace_id,
            "credits": "1",
            "ledger_id": tx.id,
        },
    )
    await db.flush()
    return True
