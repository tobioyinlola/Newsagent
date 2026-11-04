"""Attribution is carried by the emailed signup code; reward and signup commit together."""

import re
import secrets
from decimal import ROUND_HALF_UP, Decimal

from sqlalchemy import select, update
from sqlalchemy.dialects.postgresql import insert as pg_insert
from sqlalchemy.dialects.sqlite import insert as sqlite_insert
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
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
    # Who referred whom is recorded here whatever the signup reward is; the money comes from the referred business's purchases.
    amount = Decimal(get_settings().referral_signup_credits)
    tx = None
    if amount > 0:
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
            "credits": str(amount),
            "ledger_id": tx.id if tx else None,
        },
    )
    await db.flush()
    return True


async def reward_purchase(
    db: AsyncSession, referred_workspace_id: str, credits: Decimal, checkout_id: str
) -> Decimal | None:
    """A business that came through a referral has just bought credits: its referrer is credited a percentage of them
    (`REFERRAL_PURCHASE_PERCENT`, 5 by default) on every purchase. Returns the credits given, or None if nothing was.
    Safe to call twice for one purchase: the ledger reference makes it happen once. Joins the caller's transaction."""
    percent = Decimal(get_settings().referral_purchase_percent)
    amount = (Decimal(credits) * percent / Decimal(100)).quantize(Decimal("0.01"), rounding=ROUND_HALF_UP)
    if amount <= 0:
        return None
    row = (
        await db.execute(select(ReferralReward).where(ReferralReward.referred_workspace_id == referred_workspace_id))
    ).scalar_one_or_none()
    if row is None:
        return None  # this business did not come through a referral
    # Serialize awards to the referrer's wallet, as the signup reward does. A deleted or suspended referrer earns nothing.
    workspace = (
        await db.execute(
            update(Workspace)
            .where(
                Workspace.id == row.referrer_workspace_id,
                Workspace.deleted_at.is_(None),
                Workspace.suspended.is_(False),
            )
            .values(credit_balance=Workspace.credit_balance)
            .returning(Workspace)
            .execution_options(populate_existing=True)
        )
    ).scalar_one_or_none()
    if workspace is None:
        return None
    referred = await db.get(Workspace, referred_workspace_id)
    name = referred.name if referred is not None else "A business you referred"
    tx = await ledger.apply(
        db,
        workspace,
        amount,
        "grant",
        ref=f"referral-purchase:{checkout_id}",
        description=f"Referral reward: {name} bought credits ({percent:g}% of {Decimal(credits):,.2f})",
    )
    if tx is None:
        return None  # already given for this purchase
    await db.execute(
        update(ReferralReward).where(ReferralReward.id == row.id).values(credits=ReferralReward.credits + amount)
    )  # the running total earned from this referred business
    audit(
        db,
        "referral-service",
        "referral.purchase_reward",
        target_type="workspace",
        target_id=workspace.id,
        detail={
            "referred_workspace_id": referred_workspace_id,
            "checkout": checkout_id,
            "credits": str(amount),
            "percent": str(percent),
            "ledger_id": tx.id,
        },
    )
    return amount


async def notify_purchase_reward(db: AsyncSession, checkout) -> None:
    """After the purchase is committed: tell the referrer what they earned from it (one short email)."""
    from app.models import CreditTransaction
    from app.services.notifications import send_email

    ref = f"referral-purchase:{checkout.id}"
    tx = (await db.execute(select(CreditTransaction).where(CreditTransaction.ref == ref))).scalar_one_or_none()
    if tx is None:
        return
    row = (
        await db.execute(select(ReferralReward).where(ReferralReward.referrer_workspace_id == tx.workspace_id))
    ).scalars()
    reward = next((r for r in row if r.referred_workspace_id == checkout.workspace_id), None)
    if reward is None or reward.referrer_user_id is None:
        return
    email = (await db.execute(select(User.email).where(User.id == reward.referrer_user_id))).scalar_one_or_none()
    referred = await db.get(Workspace, checkout.workspace_id)
    if not email:
        return
    name = referred.name if referred is not None else "A business you referred"
    await send_email(
        email,
        f"You earned {tx.amount:,.2f} credits",
        f"{name}, a business you referred, has just bought credits. We've added {tx.amount:,.2f} credits "
        f"({Decimal(get_settings().referral_purchase_percent):g}% of their purchase) to your wallet. Thank you for spreading the word.",
        link=("See your referrals", f"{get_settings().app_base_url.rstrip('/')}/referrals"),
    )
