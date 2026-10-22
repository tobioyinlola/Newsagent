"""Request authentication: server-side sessions (bearer token, stored hashed).

`Authorization: Bearer nas_...`. Local development also accepts `Bearer dev:<email>` (only when ENVIRONMENT=local).
Operators confirm every sign-in with an emailed code. Until they do, their session is "pre-OTP": it can only call
/auth/login/otp (and resend) and sign out; everything else needs a fully verified session.
"""

from dataclasses import dataclass
from datetime import UTC, datetime

from fastapi import Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import get_session
from app.models import User, UserSession, Workspace
from app.services import sessions as sess

UNAUTHENTICATED = HTTPException(401, "Please sign in.")


@dataclass
class AuthCtx:
    user: User
    row: UserSession | None  # None for local dev tokens

    @property
    def otp_ok(self) -> bool:
        return self.row is None or self.row.otp_verified


async def auth_ctx_any(
    authorization: str | None = Header(default=None), db: AsyncSession = Depends(get_session)
) -> AuthCtx:
    """Any live session, including one still waiting for its emailed sign-in code."""
    if not authorization or not authorization.lower().startswith("bearer "):
        raise UNAUTHENTICATED
    token = authorization[7:].strip()
    if get_settings().is_local and token.startswith("dev:"):
        user = (await db.execute(select(User).where(User.email == token[4:].lower()))).scalar_one_or_none()
        if user is None:
            raise HTTPException(403, "No account. Signup is invite-only.")
        return AuthCtx(user, None)
    row = (
        await db.execute(select(UserSession).where(UserSession.token_hash == sess.hash_token(token)))
    ).scalar_one_or_none()
    user = await db.get(User, row.user_id) if row else None
    if row is None or user is None or not sess.session_is_live(row, user):
        raise UNAUTHENTICATED
    now = datetime.now(UTC)
    if now - sess._utc(row.last_used_at) > sess.TOUCH_EVERY:
        row.last_used_at = now  # sliding idle timeout, written at most every few minutes
        await db.commit()
    return AuthCtx(user, row)


async def auth_ctx(ctx: AuthCtx = Depends(auth_ctx_any)) -> AuthCtx:
    if not ctx.otp_ok:
        raise HTTPException(401, {"error": "otp_required", "message": "Enter the code we emailed you to continue."})
    return ctx


@dataclass
class Principal:
    user: User
    workspace: Workspace
    is_operator: bool
    session: UserSession | None = None


async def current_principal(ctx: AuthCtx = Depends(auth_ctx), db: AsyncSession = Depends(get_session)) -> Principal:
    ws = await db.get(Workspace, ctx.user.workspace_id)
    return Principal(ctx.user, ws, sess.is_operator_email(ctx.user.email), ctx.row)  # type: ignore[arg-type]


async def operator(p: Principal = Depends(current_principal)) -> Principal:
    if not p.is_operator:
        raise HTTPException(403, "Operator only")
    return p
