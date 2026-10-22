"""Request authentication: server-side sessions (bearer token, stored hashed).

`Authorization: Bearer nas_...`. Local development also accepts `Bearer dev:<email>` (only when ENVIRONMENT=local).
A session may be "pre-MFA": the user proved the email code but has not yet given their authenticator code. Such a
session can only call the MFA endpoints and sign out; everything else needs a fully verified one.
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
    def mfa_ok(self) -> bool:
        return self.row is None or not self.user.totp_enabled or self.row.mfa_verified


async def auth_ctx_any(
    authorization: str | None = Header(default=None), db: AsyncSession = Depends(get_session)
) -> AuthCtx:
    """Any live session, including one still waiting for its authenticator code."""
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
    if not ctx.mfa_ok:
        raise HTTPException(401, {"error": "mfa_required", "message": "Enter your authenticator code to continue."})
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
    if p.session is not None and not p.user.totp_enabled:  # operators must have a second factor
        raise HTTPException(
            403,
            {
                "error": "mfa_enrolment_required",
                "message": "Set up your authenticator app to use the operator console.",
            },
        )
    return p
