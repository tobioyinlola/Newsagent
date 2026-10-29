"""Sign-up (invite only), password sign-in, emailed one-time codes and server-side sessions.

Sign-up: choose a password, then prove control of the invited address with a 6-digit emailed code. Sign-in is
email + password; operators also confirm each sign-in with an emailed code. Forgot-password uses an emailed code too.

Responses never reveal whether an email has an account: a wrong password, an unknown email and an account with no
password all give the same 401, forgot-password always answers the same way, and a wrong, expired or unknown code
all give the same 401.
"""

import hashlib
from datetime import UTC, datetime
from decimal import Decimal

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import AuthCtx, Principal, auth_ctx, auth_ctx_any, current_principal
from app.config import get_settings
from app.db import get_session
from app.models import BrandKit, Invite, User, UserSession, Workspace
from app.schemas.api import (
    ChangePasswordIn,
    CodeSentOut,
    ForgotIn,
    InvitePreview,
    LoginIn,
    MeOut,
    OtpIn,
    ResetIn,
    SessionInfo,
    SessionOut,
    SignupStartIn,
    SignupVerifyIn,
)
from app.services import email_templates as templates
from app.services import ledger, passwords, ratelimit
from app.services import sessions as sess
from app.services.audit import audit
from app.services.notifications import send_email

router = APIRouter(prefix="/v1", tags=["auth"])
BAD_CODE = HTTPException(401, "That code is incorrect or has expired. Request a new one and try again.")
BAD_LOGIN = HTTPException(401, "That email and password don't match. Check them and try again, or reset your password.")
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


def _check_password(password: str, email: str) -> None:
    problem = passwords.policy_error(password, email)
    if problem:
        raise HTTPException(422, problem)


def _email(kind: str, code: str) -> tuple[str, str, str]:
    return templates.sign_in_code(kind, code, get_settings().otp_ttl_minutes)


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
    settings = get_settings()
    if body.invite_code:  # an invitation: the workspace and the address are already decided
        await _throttle(request, "signup", body.invite_code, (5, 3600), (20, 3600))
        inv = await _invite(db, body.invite_code)
        email, invite_id, workspace_name = inv.email.lower(), inv.id, None
    else:  # open sign-up: a business creates its own workspace after confirming its email
        if not settings.open_signup_enabled:
            raise HTTPException(403, "Sign-up is by invitation for now. Ask us for an invite link.")
        if not body.email or not body.business_name or not body.business_name.strip():
            raise HTTPException(422, "Enter your business name and email address.")
        if not (body.city or "").strip() or not (body.country or "").strip():
            raise HTTPException(422, "Enter the city and country your business is based in.")
        if not body.industry:
            raise HTTPException(422, "Choose the industry your business is in.")
        email, invite_id, workspace_name = str(body.email).lower(), None, body.business_name.strip()
        await _throttle(request, "signup", email, (5, 3600), (20, 3600))
    if (await db.execute(select(User.id).where(User.email == email))).first():
        raise HTTPException(409, "This email already has an account. Sign in instead.")
    _check_password(body.password, email)
    code = await sess.issue_code(
        db,
        email,
        "signup",
        invite_id=invite_id,
        password_hash=passwords.hash_password(body.password),
        ip=ratelimit.client_ip(request),
        workspace_name=workspace_name,
        city=(body.city or "").strip() or None,
        country=(body.country or "").strip() or None,
        industry=body.industry,
    )
    await db.commit()
    subject, html, text = _email("signup", code)
    bg.add_task(send_email, email, subject, text, html)
    return CodeSentOut(email_hint=sess.mask_email(email), expires_in_s=settings.otp_ttl_minutes * 60)


@router.post("/auth/signup/verify", response_model=SessionOut)
async def signup_verify(body: SignupVerifyIn, request: Request, db: AsyncSession = Depends(get_session)) -> SessionOut:
    inv: Invite | None = None
    if body.invite_code:
        await _throttle(request, "signup-verify", body.invite_code, (10, 600), (30, 600))
        inv = await _invite(db, body.invite_code)
        email = inv.email.lower()
    else:
        if not get_settings().open_signup_enabled or not body.email:
            raise BAD_CODE
        email = str(body.email).lower()
        await _throttle(request, "signup-verify", email, (10, 600), (30, 600))
    row = await sess.check_code(db, email, "signup", body.code, invite_id=inv.id if inv else None)
    await db.commit()  # persists the failed-attempt counter too
    if row is None or not row.password_hash or (inv is None and (row.invite_id or not row.workspace_name)):
        raise BAD_CODE
    if (await db.execute(select(User.id).where(User.email == email))).first():
        raise HTTPException(409, "This email already has an account. Sign in instead.")
    if inv is not None:
        ws = await db.get(Workspace, inv.workspace_id)
        assert ws is not None
        inv.used_at = datetime.now(UTC)
    else:  # a new workspace for a business that signed up on its own
        ws = Workspace(
            name=row.workspace_name,
            city=row.city,
            country=row.country,
            industry=row.industry,
            credit_balance=Decimal("0"),
            spend_cap=Decimal("0"),
        )
        db.add(ws)
        await db.flush()
        credits = Decimal(get_settings().signup_credits or "0")
        if credits > 0:
            await ledger.apply(db, ws, credits, "grant", description="Welcome credits (sign-up)")
    user = User(email=email, role="owner", workspace_id=ws.id, password_hash=row.password_hash)
    db.add(user)
    kit = BrandKit(workspace_id=ws.id)  # neutral fallback kit (spec section 10)
    db.add(kit)
    await db.flush()
    ws.brand_kit_id = kit.id
    row.password_hash = None  # not needed any more
    ns = await sess.create_session(db, user, request, otp_verified=True)
    audit(
        db,
        user.email,
        "auth.signup",
        target_type="workspace",
        target_id=ws.id,
        detail={"via": "invite" if inv else "open"},
        request=request,
    )
    await db.commit()
    return SessionOut(token=ns.token, expires_at=ns.row.expires_at, otp_required=False)


# ---------- sign in ----------
@router.post("/auth/login", response_model=SessionOut)
async def login(
    body: LoginIn, request: Request, bg: BackgroundTasks, db: AsyncSession = Depends(get_session)
) -> SessionOut:
    email = body.email.lower()
    await _throttle(request, "login", email, (10, 600), (40, 600))
    user = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
    ok = passwords.verify_password(body.password, user.password_hash if user else None)  # same work either way
    if not ok or user is None:
        raise BAD_LOGIN
    operator = sess.is_operator_email(email)
    ns = await sess.create_session(db, user, request, otp_verified=not operator)
    if operator:  # second step: operators confirm each sign-in with an emailed code
        code = await sess.issue_code(db, email, "login", ip=ratelimit.client_ip(request))
        subject, html, text = _email("login", code)
        bg.add_task(send_email, email, subject, text, html)
        audit(db, email, "auth.login", target_type="user", target_id=user.id, detail={"otp": "sent"}, request=request)
    await db.commit()
    return SessionOut(token=ns.token, expires_at=ns.row.expires_at, otp_required=operator)


@router.post("/auth/login/otp")
async def login_otp(
    body: OtpIn, request: Request, ctx: AuthCtx = Depends(auth_ctx_any), db: AsyncSession = Depends(get_session)
) -> dict:
    """Operators: finish signing in with the emailed code."""
    if ctx.row is None or ctx.otp_ok:
        return {"ok": True}
    await _throttle(request, "login-otp", ctx.user.id, (10, 600), (40, 600))
    row = await sess.check_code(db, ctx.user.email, "login", body.code)
    if row is None:
        await db.commit()  # keep the attempt count
        raise BAD_CODE
    ctx.row.otp_verified = True
    audit(db, ctx.user.email, "auth.login_verified", target_type="user", target_id=ctx.user.id, request=request)
    await db.commit()
    return {"ok": True}


@router.post("/auth/login/otp/resend", response_model=CodeSentOut)
async def login_otp_resend(
    request: Request, bg: BackgroundTasks, ctx: AuthCtx = Depends(auth_ctx_any), db: AsyncSession = Depends(get_session)
) -> CodeSentOut:
    if ctx.row is None or ctx.otp_ok:
        raise HTTPException(409, "This session doesn't need a code.")
    await _throttle(request, "login-resend", ctx.user.id, (5, 3600), (20, 3600))
    code = await sess.issue_code(db, ctx.user.email, "login", ip=ratelimit.client_ip(request))
    await db.commit()
    subject, html, text = _email("login", code)
    bg.add_task(send_email, ctx.user.email, subject, text, html)
    return CodeSentOut(email_hint=sess.mask_email(ctx.user.email), expires_in_s=get_settings().otp_ttl_minutes * 60)


# ---------- passwords ----------
@router.post("/auth/password/forgot", response_model=CodeSentOut)
async def password_forgot(
    body: ForgotIn, request: Request, bg: BackgroundTasks, db: AsyncSession = Depends(get_session)
) -> CodeSentOut:
    email = body.email.lower()
    await _throttle(request, "forgot", email, (5, 3600), (20, 3600))
    user = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
    if user is not None:  # unknown emails get the identical response and no email
        code = await sess.issue_code(db, email, "reset", ip=ratelimit.client_ip(request))
        await db.commit()
        subject, html, text = _email("reset", code)
        bg.add_task(send_email, email, subject, text, html)
    return CodeSentOut(expires_in_s=get_settings().otp_ttl_minutes * 60)


@router.post("/auth/password/reset")
async def password_reset(body: ResetIn, request: Request, db: AsyncSession = Depends(get_session)) -> dict:
    email = body.email.lower()
    await _throttle(request, "reset", email, (10, 600), (30, 600))
    user = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
    row = await sess.check_code(db, email, "reset", body.code)  # always run: same work for unknown emails
    await db.commit()
    if row is None or user is None:
        raise BAD_CODE
    _check_password(body.new_password, email)
    user.password_hash = passwords.hash_password(body.new_password)
    await sess.revoke_all(db, user.id)  # whoever had the old password is signed out
    audit(db, email, "auth.password_reset", target_type="user", target_id=user.id, request=request)
    await db.commit()
    return {"ok": True}


@router.post("/auth/password/change")
async def password_change(
    body: ChangePasswordIn, request: Request, ctx: AuthCtx = Depends(auth_ctx), db: AsyncSession = Depends(get_session)
) -> dict:
    await _throttle(request, "pwchange", ctx.user.id, (10, 600), (40, 600))
    if not passwords.verify_password(body.current_password, ctx.user.password_hash):
        raise HTTPException(401, "Your current password is incorrect.")
    _check_password(body.new_password, ctx.user.email)
    ctx.user.password_hash = passwords.hash_password(body.new_password)
    await sess.revoke_all(db, ctx.user.id, except_id=ctx.row.id if ctx.row else None)
    audit(db, ctx.user.email, "auth.password_changed", target_type="user", target_id=ctx.user.id, request=request)
    await db.commit()
    return {"ok": True}


# ---------- who am I ----------
@router.get("/me", response_model=MeOut)
async def me(p: Principal = Depends(current_principal)) -> MeOut:
    return MeOut(
        email=p.user.email,
        workspace_id=p.workspace.id,
        workspace_name=p.workspace.name,
        credit_balance=p.workspace.credit_balance,
        is_operator=p.is_operator,
    )


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
