"""Sign-up (invite only), sign-in, sessions and two-factor (TOTP). No passwords: a code emailed to the address proves
control of it, then a server-side session is issued.

Responses never reveal whether an email has an account: login/start always answers the same way, and a wrong,
expired or unknown code all give the same 401.
"""

import hashlib
import secrets
from datetime import UTC, datetime

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import AuthCtx, Principal, auth_ctx, auth_ctx_any, current_principal
from app.config import get_settings
from app.db import get_session
from app.models import BrandKit, Invite, RecoveryCode, User, UserSession, Workspace
from app.schemas.api import (
    CodeSentOut,
    InvitePreview,
    LoginStartIn,
    LoginVerifyIn,
    MeOut,
    MfaCodeIn,
    MfaEnableOut,
    MfaSetupOut,
    SessionInfo,
    SessionOut,
    SignupStartIn,
    SignupVerifyIn,
)
from app.services import crypto, ratelimit, totp
from app.services import sessions as sess
from app.services.audit import audit
from app.services.notifications import send_email

router = APIRouter(prefix="/v1", tags=["auth"])
BAD_CODE = HTTPException(401, "That code is incorrect or has expired. Request a new one and try again.")
BAD_INVITE = HTTPException(404, "That invite link isn't valid or has expired.")


async def _throttle(
    request: Request, name: str, subject: str, per_subject: tuple[int, int], per_ip: tuple[int, int]
) -> None:
    key = hashlib.sha256(subject.lower().encode()).hexdigest()[:16]
    if not await ratelimit.hit(f"{name}:s:{key}", *per_subject) or not await ratelimit.hit(
        f"{name}:ip:{ratelimit.client_ip(request)}", *per_ip
    ):
        raise HTTPException(429, "Too many attempts. Please wait a little and try again.")


async def _invite(db: AsyncSession, code: str) -> Invite:
    inv = (await db.execute(select(Invite).where(Invite.code == code))).scalar_one_or_none()
    if inv is None or inv.used_at is not None or sess._utc(inv.expires_at) < datetime.now(UTC):
        raise BAD_INVITE
    return inv


def _session_out(ns: sess.NewSession, user: User, *, mfa_required: bool) -> SessionOut:
    return SessionOut(
        token=ns.token,
        expires_at=ns.row.expires_at,
        mfa_required=mfa_required,
        mfa_enrolment_required=sess.is_operator_email(user.email) and not user.totp_enabled,
    )


def _email(kind: str, code: str) -> tuple[str, str]:
    mins = get_settings().otp_ttl_minutes
    what = "sign up" if kind == "signup" else "sign in"
    return (
        f"Your Newsagent {what} code: {code}",
        f"Your code to {what} is:\n\n    {code}\n\nIt works once and expires in {mins} minutes. If you didn't ask for it, "
        "ignore this email: nobody can get in without the code. Never share it with anyone.\n",
    )


# ---------- sign up (invite only) ----------
@router.get("/auth/invite/{code}", response_model=InvitePreview)
async def invite_preview(code: str, request: Request, db: AsyncSession = Depends(get_session)) -> InvitePreview:
    await _throttle(request, "invite", ratelimit.client_ip(request), (30, 3600), (60, 3600))
    inv = await _invite(db, code)
    ws = await db.get(Workspace, inv.workspace_id)
    return InvitePreview(workspace_name=ws.name if ws else "", email_hint=sess.mask_email(inv.email))


@router.post("/auth/signup/start", response_model=CodeSentOut)
async def signup_start(
    body: SignupStartIn, request: Request, bg: BackgroundTasks, db: AsyncSession = Depends(get_session)
) -> CodeSentOut:
    await _throttle(request, "signup", body.invite_code, (5, 3600), (20, 3600))
    inv = await _invite(db, body.invite_code)
    if (await db.execute(select(User.id).where(User.email == inv.email.lower()))).first():
        raise HTTPException(409, "This email already has an account. Sign in instead.")
    code = await sess.issue_code(db, inv.email, "signup", invite_id=inv.id, ip=ratelimit.client_ip(request))
    await db.commit()
    subject, text = _email("signup", code)
    bg.add_task(send_email, inv.email, subject, text)
    return CodeSentOut(email_hint=sess.mask_email(inv.email), expires_in_s=get_settings().otp_ttl_minutes * 60)


@router.post("/auth/signup/verify", response_model=SessionOut)
async def signup_verify(body: SignupVerifyIn, request: Request, db: AsyncSession = Depends(get_session)) -> SessionOut:
    await _throttle(request, "signup-verify", body.invite_code, (10, 600), (30, 600))
    inv = await _invite(db, body.invite_code)
    ok = await sess.check_code(db, inv.email, "signup", body.code, invite_id=inv.id)
    await db.commit()  # persists the failed-attempt counter too
    if not ok:
        raise BAD_CODE
    if (await db.execute(select(User.id).where(User.email == inv.email.lower()))).first():
        raise HTTPException(409, "This email already has an account. Sign in instead.")
    ws = await db.get(Workspace, inv.workspace_id)
    assert ws is not None
    user = User(email=inv.email.lower(), role="owner", workspace_id=ws.id)
    db.add(user)
    kit = BrandKit(workspace_id=ws.id)  # neutral fallback kit (spec section 10)
    db.add(kit)
    await db.flush()
    ws.brand_kit_id = kit.id
    inv.used_at = datetime.now(UTC)
    ns = await sess.create_session(db, user, request, mfa_verified=True)
    audit(db, user.email, "auth.signup", target_type="workspace", target_id=ws.id, request=request)
    await db.commit()
    return _session_out(ns, user, mfa_required=False)


# ---------- sign in ----------
@router.post("/auth/login/start", response_model=CodeSentOut)
async def login_start(
    body: LoginStartIn, request: Request, bg: BackgroundTasks, db: AsyncSession = Depends(get_session)
) -> CodeSentOut:
    email = body.email.lower()
    await _throttle(request, "login", email, (5, 3600), (20, 3600))
    user = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
    if user is not None:  # unknown emails get the identical response and no email
        code = await sess.issue_code(db, email, "login", ip=ratelimit.client_ip(request))
        await db.commit()
        subject, text = _email("login", code)
        bg.add_task(send_email, email, subject, text)
    return CodeSentOut(expires_in_s=get_settings().otp_ttl_minutes * 60)


@router.post("/auth/login/verify", response_model=SessionOut)
async def login_verify(body: LoginVerifyIn, request: Request, db: AsyncSession = Depends(get_session)) -> SessionOut:
    email = body.email.lower()
    await _throttle(request, "login-verify", email, (10, 600), (30, 600))
    user = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
    ok = await sess.check_code(db, email, "login", body.code)  # always run: same work for unknown emails
    await db.commit()
    if not ok or user is None:
        raise BAD_CODE
    ns = await sess.create_session(db, user, request, mfa_verified=not user.totp_enabled)
    if sess.is_operator_email(email):
        audit(
            db,
            email,
            "auth.login",
            target_type="user",
            target_id=user.id,
            detail={"mfa": user.totp_enabled},
            request=request,
        )
    await db.commit()
    return _session_out(ns, user, mfa_required=user.totp_enabled)


# ---------- who am I ----------
@router.get("/me", response_model=MeOut)
async def me(p: Principal = Depends(current_principal)) -> MeOut:
    return MeOut(
        email=p.user.email,
        workspace_id=p.workspace.id,
        workspace_name=p.workspace.name,
        credit_balance=p.workspace.credit_balance,
        is_operator=p.is_operator,
        mfa_enabled=p.user.totp_enabled,
    )


@router.get("/auth/status")
async def auth_status(ctx: AuthCtx = Depends(auth_ctx_any)) -> dict:
    """Lets the app route correctly even for a session still waiting for its authenticator code."""
    op = sess.is_operator_email(ctx.user.email)
    return {
        "email": ctx.user.email,
        "mfa_enabled": ctx.user.totp_enabled,
        "mfa_verified": ctx.mfa_ok,
        "is_operator": op,
        "mfa_enrolment_required": op and not ctx.user.totp_enabled,
    }


# ---------- two-factor (TOTP) ----------
def _recovery_hash(email: str, code: str) -> str:
    return sess.hash_code(email, "recovery", code.strip().lower().replace("-", ""))


async def _new_recovery_codes(db: AsyncSession, user: User) -> list[str]:
    await db.execute(delete(RecoveryCode).where(RecoveryCode.user_id == user.id))
    codes = []
    for _ in range(8):
        raw = secrets.token_hex(5)  # 40 bits each, single use
        codes.append(f"{raw[:5]}-{raw[5:]}")
        db.add(RecoveryCode(user_id=user.id, code_hash=_recovery_hash(user.email, raw)))
    return codes


@router.post("/auth/mfa/verify")
async def mfa_verify(
    body: MfaCodeIn, request: Request, ctx: AuthCtx = Depends(auth_ctx_any), db: AsyncSession = Depends(get_session)
) -> dict:
    """Second step of sign-in: an authenticator code, or a one-time recovery code."""
    user, row = ctx.user, ctx.row
    if row is None or not user.totp_enabled or not user.totp_secret_enc:
        raise HTTPException(409, "Two-factor sign-in isn't turned on for this account.")
    await _throttle(request, "mfa", user.id, (10, 600), (60, 600))
    step = totp.verify(crypto.decrypt(user.totp_secret_enc), body.code, user.totp_last_step)
    used_recovery = False
    if step is None:
        rc = (
            await db.execute(
                select(RecoveryCode).where(
                    RecoveryCode.user_id == user.id,
                    RecoveryCode.used_at.is_(None),
                    RecoveryCode.code_hash == _recovery_hash(user.email, body.code),
                )
            )
        ).scalar_one_or_none()
        if rc is None:
            raise HTTPException(401, "That code is incorrect. Check your authenticator app and try again.")
        rc.used_at, used_recovery = datetime.now(UTC), True
    else:
        user.totp_last_step = step
    row.mfa_verified = True
    if used_recovery:
        audit(db, user.email, "auth.recovery_code_used", target_type="user", target_id=user.id, request=request)
    await db.commit()
    return {"ok": True, "recovery_code_used": used_recovery}


@router.post("/auth/mfa/setup", response_model=MfaSetupOut)
async def mfa_setup(ctx: AuthCtx = Depends(auth_ctx), db: AsyncSession = Depends(get_session)) -> MfaSetupOut:
    if ctx.user.totp_enabled:
        raise HTTPException(409, "Two-factor sign-in is already on.")
    secret = totp.new_secret()
    ctx.user.totp_secret_enc = crypto.encrypt(secret)  # pending until /enable proves the app works
    await db.commit()
    return MfaSetupOut(secret=secret, otpauth_uri=totp.provisioning_uri(secret, ctx.user.email))


@router.post("/auth/mfa/enable", response_model=MfaEnableOut)
async def mfa_enable(
    body: MfaCodeIn, request: Request, ctx: AuthCtx = Depends(auth_ctx), db: AsyncSession = Depends(get_session)
) -> MfaEnableOut:
    user = ctx.user
    if user.totp_enabled or not user.totp_secret_enc:
        raise HTTPException(409, "Start setup first.")
    await _throttle(request, "mfa", user.id, (10, 600), (60, 600))
    step = totp.verify(crypto.decrypt(user.totp_secret_enc), body.code)
    if step is None:
        raise HTTPException(422, "That code didn't match. Check the time on your phone and try again.")
    user.totp_enabled, user.totp_last_step = True, step
    if ctx.row:
        ctx.row.mfa_verified = True
        await sess.revoke_all(db, user.id, except_id=ctx.row.id)  # other devices must now pass the second factor
    codes = await _new_recovery_codes(db, user)
    audit(db, user.email, "auth.mfa_enabled", target_type="user", target_id=user.id, request=request)
    await db.commit()
    return MfaEnableOut(recovery_codes=codes)


@router.post("/auth/mfa/disable")
async def mfa_disable(
    body: MfaCodeIn, request: Request, ctx: AuthCtx = Depends(auth_ctx), db: AsyncSession = Depends(get_session)
) -> dict:
    user = ctx.user
    if sess.is_operator_email(user.email):
        raise HTTPException(
            403, "Operators must keep two-factor sign-in on. Ask another operator to reset it if you are locked out."
        )
    if not user.totp_enabled or not user.totp_secret_enc:
        raise HTTPException(409, "Two-factor sign-in isn't on.")
    await _throttle(request, "mfa", user.id, (10, 600), (60, 600))
    if totp.verify(crypto.decrypt(user.totp_secret_enc), body.code, user.totp_last_step) is None:
        raise HTTPException(401, "That code is incorrect.")
    user.totp_enabled, user.totp_secret_enc, user.totp_last_step = False, None, None
    await db.execute(delete(RecoveryCode).where(RecoveryCode.user_id == user.id))
    if ctx.row:
        await sess.revoke_all(db, user.id, except_id=ctx.row.id)
    audit(db, user.email, "auth.mfa_disabled", target_type="user", target_id=user.id, request=request)
    await db.commit()
    return {"ok": True}


@router.post("/auth/mfa/recovery-codes", response_model=MfaEnableOut)
async def mfa_new_recovery_codes(
    body: MfaCodeIn, request: Request, ctx: AuthCtx = Depends(auth_ctx), db: AsyncSession = Depends(get_session)
) -> MfaEnableOut:
    user = ctx.user
    if not user.totp_enabled or not user.totp_secret_enc:
        raise HTTPException(409, "Two-factor sign-in isn't on.")
    await _throttle(request, "mfa", user.id, (10, 600), (60, 600))
    step = totp.verify(crypto.decrypt(user.totp_secret_enc), body.code, user.totp_last_step)
    if step is None:
        raise HTTPException(401, "That code is incorrect.")
    user.totp_last_step = step
    codes = await _new_recovery_codes(db, user)
    await db.commit()
    return MfaEnableOut(recovery_codes=codes)


# ---------- sessions / sign out ----------
@router.post("/auth/logout")
async def logout(ctx: AuthCtx = Depends(auth_ctx_any), db: AsyncSession = Depends(get_session)) -> dict:
    if ctx.row:
        ctx.row.revoked_at = datetime.now(UTC)
        await db.commit()
    return {"ok": True}


@router.post("/auth/logout-all")
async def logout_everywhere(ctx: AuthCtx = Depends(auth_ctx_any), db: AsyncSession = Depends(get_session)) -> dict:
    await sess.revoke_all(db, ctx.user.id)
    await db.commit()
    return {"ok": True}


@router.get("/auth/sessions", response_model=list[SessionInfo])
async def list_sessions(ctx: AuthCtx = Depends(auth_ctx), db: AsyncSession = Depends(get_session)) -> list[SessionInfo]:
    rows = (
        (
            await db.execute(
                select(UserSession)
                .where(UserSession.user_id == ctx.user.id, UserSession.revoked_at.is_(None))
                .order_by(UserSession.last_used_at.desc())
            )
        )
        .scalars()
        .all()
    )
    return [
        SessionInfo(
            id=r.id,
            created_at=r.created_at,
            last_used_at=r.last_used_at,
            user_agent=r.user_agent,
            ip=r.ip,
            current=bool(ctx.row and r.id == ctx.row.id),
        )
        for r in rows
        if sess.session_is_live(r, ctx.user)
    ]


@router.delete("/auth/sessions/{session_id}")
async def revoke_session(
    session_id: str, ctx: AuthCtx = Depends(auth_ctx), db: AsyncSession = Depends(get_session)
) -> dict:
    row = await db.get(UserSession, session_id)
    if row is None or row.user_id != ctx.user.id:  # you can only sign out your own devices
        raise HTTPException(404, "Session not found")
    row.revoked_at = datetime.now(UTC)
    await db.commit()
    return {"ok": True}
