"""One-time email codes and server-side sessions (the in-house sign-in)."""

import hashlib
import hmac
import secrets
from dataclasses import dataclass
from datetime import UTC, datetime, timedelta

from fastapi import Request
from sqlalchemy import select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import AuthCode, User, UserSession
from app.services import crypto
from app.services.ratelimit import client_ip

MAX_CODE_ATTEMPTS = 5
TOUCH_EVERY = timedelta(minutes=1)  # don't write on every request


def _utc(d: datetime) -> datetime:
    return d if d.tzinfo else d.replace(tzinfo=UTC)


def mask_email(email: str) -> str:
    name, _, domain = email.partition("@")
    return f"{name[:1]}{'*' * max(2, len(name) - 1)}@{domain}"


# ---------- one-time codes ----------
def new_code() -> str:
    return f"{secrets.randbelow(1_000_000):06d}"


def hash_code(email: str, purpose: str, code: str) -> str:
    return hmac.new(crypto.pepper(), f"{email.lower()}|{purpose}|{code}".encode(), hashlib.sha256).hexdigest()


async def issue_code(
    session: AsyncSession,
    email: str,
    purpose: str,
    *,
    invite_id: str | None = None,
    password_hash: str | None = None,
    ip: str | None = None,
    workspace_name: str | None = None,
    city: str | None = None,
    country: str | None = None,
    industry: str | None = None,
) -> str:
    """Create a fresh code. Codes older than a minute stop working; one requested seconds ago (a double click, a quick resend) still does,
    so the code in the first email the person opens is never the one that was just cancelled."""
    email = email.lower()
    now = datetime.now(UTC)
    await session.execute(
        update(AuthCode)
        .where(
            AuthCode.email == email,
            AuthCode.purpose == purpose,
            AuthCode.consumed_at.is_(None),
            AuthCode.created_at < now - timedelta(seconds=60),
        )
        .values(consumed_at=now)
    )
    code = new_code()
    session.add(
        AuthCode(
            email=email,
            purpose=purpose,
            code_hash=hash_code(email, purpose, code),
            invite_id=invite_id,
            password_hash=password_hash,
            ip=ip,
            workspace_name=workspace_name,
            city=city,
            country=country,
            industry=industry,
            expires_at=now + timedelta(minutes=get_settings().otp_ttl_minutes),
        )
    )
    await session.flush()
    return code


async def check_code(
    session: AsyncSession, email: str, purpose: str, code: str, *, invite_id: str | None = None
) -> AuthCode | None:
    """The code's row, once, for the right unexpired code; None otherwise. Five wrong guesses burn the code. Compares in constant time."""
    email = email.lower()
    now = datetime.now(UTC)
    rows = (
        (
            await session.execute(
                select(AuthCode)
                .where(AuthCode.email == email, AuthCode.purpose == purpose, AuthCode.consumed_at.is_(None))
                .order_by(AuthCode.created_at.desc())
                .limit(3)
            )
        )
        .scalars()
        .all()
    )
    given = hash_code(email, purpose, code.strip())
    live = [r for r in rows if _utc(r.expires_at) >= now and (invite_id is None or r.invite_id == invite_id)]
    live = [r for r in live if r.attempts < MAX_CODE_ATTEMPTS]
    dummy = hash_code(email, purpose, "000000")
    hit = None
    for r in live:
        if hmac.compare_digest(r.code_hash, given):
            hit = r
    if not live:
        hmac.compare_digest(dummy, given)  # same work whether or not a code exists
    if hit is None:
        for r in live:
            r.attempts += 1
            if r.attempts >= MAX_CODE_ATTEMPTS:
                r.consumed_at = now  # burned: the attacker must request a new code (which is rate limited)
        return None
    hit.consumed_at = now
    return hit


# ---------- sessions ----------
def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def is_operator_email(email: str) -> bool:
    return email.lower() in {e.strip().lower() for e in get_settings().operator_emails.split(",") if e.strip()}


def lifetime_for(user: User) -> timedelta:
    s = get_settings()
    if is_operator_email(user.email):
        return timedelta(hours=s.operator_session_hours)  # operators: short sessions
    return timedelta(days=s.session_absolute_days)


@dataclass
class NewSession:
    token: str
    row: UserSession


async def create_session(
    session: AsyncSession, user: User, request: Request | None, *, otp_verified: bool
) -> NewSession:
    token = "nas_" + secrets.token_urlsafe(32)  # recognisable prefix so secret scanners can find a leaked one
    now = datetime.now(UTC)
    row = UserSession(
        user_id=user.id,
        token_hash=hash_token(token),
        expires_at=now + lifetime_for(user),
        last_used_at=now,
        otp_verified=otp_verified,
        user_agent=(request.headers.get("user-agent", "")[:300] if request else None),
        ip=client_ip(request) if request else None,
    )
    session.add(row)
    user.last_login_at = now
    await session.flush()
    return NewSession(token, row)


def session_is_live(row: UserSession, user: User, now: datetime | None = None) -> bool:
    now = now or datetime.now(UTC)
    s = get_settings()
    idle = timedelta(minutes=s.session_idle_minutes)  # signed out after an hour without activity
    return row.revoked_at is None and _utc(row.expires_at) > now and now - _utc(row.last_used_at) <= idle


async def revoke_all(session: AsyncSession, user_id: str, *, except_id: str | None = None) -> None:
    q = update(UserSession).where(UserSession.user_id == user_id, UserSession.revoked_at.is_(None))
    if except_id:
        q = q.where(UserSession.id != except_id)
    await session.execute(q.values(revoked_at=datetime.now(UTC)))
