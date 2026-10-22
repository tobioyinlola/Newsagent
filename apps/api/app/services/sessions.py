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
TOUCH_EVERY = timedelta(minutes=5)  # don't write on every request


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
    session: AsyncSession, email: str, purpose: str, *, invite_id: str | None = None, ip: str | None = None
) -> str:
    """Create a fresh code; any earlier unused code for the same email and purpose stops working."""
    email = email.lower()
    now = datetime.now(UTC)
    await session.execute(
        update(AuthCode)
        .where(AuthCode.email == email, AuthCode.purpose == purpose, AuthCode.consumed_at.is_(None))
        .values(consumed_at=now)
    )
    code = new_code()
    session.add(
        AuthCode(
            email=email,
            purpose=purpose,
            code_hash=hash_code(email, purpose, code),
            invite_id=invite_id,
            ip=ip,
            expires_at=now + timedelta(minutes=get_settings().otp_ttl_minutes),
        )
    )
    await session.flush()
    return code


async def check_code(
    session: AsyncSession, email: str, purpose: str, code: str, *, invite_id: str | None = None
) -> bool:
    """True once, for the right unexpired code. Five wrong guesses burn the code. Compares in constant time."""
    email = email.lower()
    now = datetime.now(UTC)
    row = (
        (
            await session.execute(
                select(AuthCode)
                .where(AuthCode.email == email, AuthCode.purpose == purpose, AuthCode.consumed_at.is_(None))
                .order_by(AuthCode.created_at.desc())
            )
        )
        .scalars()
        .first()
    )
    expected = row.code_hash if row else hash_code(email, purpose, "000000")  # same work whether or not a code exists
    ok = hmac.compare_digest(expected, hash_code(email, purpose, code.strip()))
    if row is None or _utc(row.expires_at) < now or (invite_id is not None and row.invite_id != invite_id):
        return False
    if row.attempts >= MAX_CODE_ATTEMPTS:
        row.consumed_at = now
        return False
    if not ok:
        row.attempts += 1
        if row.attempts >= MAX_CODE_ATTEMPTS:
            row.consumed_at = now  # burned: the attacker must request a new code (which is rate limited)
        return False
    row.consumed_at = now
    return True


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
    session: AsyncSession, user: User, request: Request | None, *, mfa_verified: bool
) -> NewSession:
    token = "nas_" + secrets.token_urlsafe(32)  # recognisable prefix so secret scanners can find a leaked one
    now = datetime.now(UTC)
    row = UserSession(
        user_id=user.id,
        token_hash=hash_token(token),
        expires_at=now + lifetime_for(user),
        last_used_at=now,
        mfa_verified=mfa_verified,
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
    idle = timedelta(hours=1) if is_operator_email(user.email) else timedelta(days=s.session_idle_days)
    return row.revoked_at is None and _utc(row.expires_at) > now and now - _utc(row.last_used_at) <= idle


async def revoke_all(session: AsyncSession, user_id: str, *, except_id: str | None = None) -> None:
    q = update(UserSession).where(UserSession.user_id == user_id, UserSession.revoked_at.is_(None))
    if except_id:
        q = q.where(UserSession.id != except_id)
    await session.execute(q.values(revoked_at=datetime.now(UTC)))
