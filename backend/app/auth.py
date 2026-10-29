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
from app.services import rbac
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
    is_operator: bool  # may use the back office at all (an owner, or an active team member with any permission)
    session: UserSession | None = None
    permissions: frozenset[str] = frozenset()
    is_owner: bool = False  # listed in OPERATOR_EMAILS: holds every permission and can't be edited from the back office

    def can(self, permission: str) -> bool:
        return permission in self.permissions


async def current_principal(ctx: AuthCtx = Depends(auth_ctx), db: AsyncSession = Depends(get_session)) -> Principal:
    ws = await db.get(Workspace, ctx.user.workspace_id)
    perms = await rbac.permissions_for(db, ctx.user.email)
    return Principal(
        ctx.user,
        ws,  # type: ignore[arg-type]
        bool(perms),
        ctx.row,
        perms,
        rbac.is_owner(ctx.user.email),
    )


def require(permission: str):
    """A dependency: the signed-in person must hold this back-office permission (checked on the server on every request)."""
    if permission not in rbac.ALL:
        raise ValueError(f"unknown permission {permission}")

    async def check(p: Principal = Depends(current_principal)) -> Principal:
        if not p.is_operator:
            raise HTTPException(403, "Operator only")
        if not p.can(permission):
            raise HTTPException(
                403, {"error": "forbidden", "message": "Your role doesn't allow this.", "permission": permission}
            )
        return p

    return check


async def operator(p: Principal = Depends(current_principal)) -> Principal:
    if not p.is_operator:
        raise HTTPException(403, "Operator only")
    return p
