"""Operator bootstrap: `python -m app.cli bootstrap-operator you@example.com [credits]`.

Signup is invite-only and invites are created by operators, so the first operator needs a workspace and user
created out of band. Idempotent.
"""

import asyncio
import sys
from decimal import Decimal

from sqlalchemy import select

from app.db import reset_engine, session_maker
from app.models import BrandKit, User, Workspace


async def bootstrap_operator(email: str, credits: Decimal = Decimal("0")) -> str:
    email = email.lower()
    async with session_maker()() as s:
        existing = (await s.execute(select(User).where(User.email == email))).scalar_one_or_none()
        if existing:
            return existing.workspace_id
        ws = Workspace(name="Operator", credit_balance=credits, spend_cap=credits)
        s.add(ws)
        await s.flush()
        s.add(User(email=email, role="owner", workspace_id=ws.id))
        kit = BrandKit(workspace_id=ws.id)
        s.add(kit)
        await s.flush()
        ws.brand_kit_id = kit.id
        await s.commit()
        return ws.id


async def reset_mfa(email: str) -> bool:
    """Lockout recovery: turn off a user's second factor and sign them out everywhere. Audited as actor "cli"."""
    from sqlalchemy import delete

    from app.models import AuditLog, RecoveryCode
    from app.services import sessions

    async with session_maker()() as s:
        user = (await s.execute(select(User).where(User.email == email.lower()))).scalar_one_or_none()
        if user is None:
            return False
        user.totp_enabled, user.totp_secret_enc, user.totp_last_step = False, None, None
        await s.execute(delete(RecoveryCode).where(RecoveryCode.user_id == user.id))
        await sessions.revoke_all(s, user.id)
        s.add(
            AuditLog(
                actor="cli",
                action="auth.mfa_reset",
                target_type="user",
                target_id=user.id,
                detail={"email": user.email},
            )
        )
        await s.commit()
        return True


def main() -> None:
    if len(sys.argv) == 3 and sys.argv[1] == "reset-mfa":

        async def go() -> None:
            print("two-factor reset" if await reset_mfa(sys.argv[2]) else "no such user")
            await reset_engine()

        asyncio.run(go())
        return
    if len(sys.argv) < 3 or sys.argv[1] != "bootstrap-operator":
        sys.exit("usage: python -m app.cli bootstrap-operator EMAIL [CREDITS] | reset-mfa EMAIL")
    credits = Decimal(sys.argv[3]) if len(sys.argv) > 3 else Decimal("0")

    async def run() -> None:
        wid = await bootstrap_operator(sys.argv[2], credits)
        print(f"operator workspace: {wid}  (also add the email to OPERATOR_EMAILS)")
        await reset_engine()

    asyncio.run(run())


if __name__ == "__main__":
    main()
