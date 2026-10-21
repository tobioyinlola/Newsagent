"""JWT verification (Clerk/Auth0 compatible). Local dev accepts `Bearer dev:<email>` only when ENVIRONMENT=local."""

from dataclasses import dataclass
from functools import lru_cache

import jwt
from fastapi import Depends, Header, HTTPException
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.db import get_session
from app.models import User, Workspace


@lru_cache
def _jwks() -> jwt.PyJWKClient:
    return jwt.PyJWKClient(get_settings().auth_issuer.rstrip("/") + "/.well-known/jwks.json")


def verified_email(authorization: str | None = Header(default=None)) -> str:
    if not authorization or not authorization.lower().startswith("bearer "):
        raise HTTPException(401, "Missing bearer token")
    token = authorization[7:]
    s = get_settings()
    if s.is_local and token.startswith("dev:"):
        return token[4:].lower()
    if not s.auth_issuer:
        raise HTTPException(500, "Auth is not configured")
    try:
        key = _jwks().get_signing_key_from_jwt(token).key
        claims = jwt.decode(token, key, algorithms=["RS256"], audience=s.auth_audience or None, issuer=s.auth_issuer)
    except jwt.PyJWTError:
        raise HTTPException(401, "Invalid token") from None
    email = claims.get("email")
    if not email:
        raise HTTPException(401, "Token has no email claim")
    return email.lower()


@dataclass
class Principal:
    user: User
    workspace: Workspace
    is_operator: bool


async def current_principal(
    email: str = Depends(verified_email), session: AsyncSession = Depends(get_session)
) -> Principal:
    user = (await session.execute(select(User).where(User.email == email))).scalar_one_or_none()
    if user is None:
        raise HTTPException(403, "No account. Signup is invite-only.")
    ws = await session.get(Workspace, user.workspace_id)
    ops = {e.strip().lower() for e in get_settings().operator_emails.split(",") if e.strip()}
    return Principal(user, ws, email in ops)  # type: ignore[arg-type]


async def operator(p: Principal = Depends(current_principal)) -> Principal:
    if not p.is_operator:
        raise HTTPException(403, "Operator only")
    return p
