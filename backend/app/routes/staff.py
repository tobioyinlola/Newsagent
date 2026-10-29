"""The back-office team: invite people, give them a role (or a custom list of permissions), change or take away their access.

Two halves. `/v1/admin/staff*` is for people who may manage the team (the `team.manage` permission). `/v1/auth/staff/*` is the
public half an invited person uses to join: open the emailed link, choose a password, confirm the emailed code.

Rules that keep access from growing by accident (enforced here, whatever the screen allows):
 * you can only give permissions you hold yourself;
 * you can't change your own access, and can't change someone who holds permissions you lack;
 * owners (OPERATOR_EMAILS) are listed but can't be changed from the back office;
 * suspending or removing someone signs them out everywhere at once and stops them signing in.
"""

import hashlib
import secrets
from datetime import UTC, datetime, timedelta

from fastapi import APIRouter, BackgroundTasks, Depends, HTTPException, Request
from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.auth import Principal, require
from app.config import get_settings
from app.db import get_session
from app.models import StaffMember, User
from app.routes.auth import BAD_CODE, BAD_INVITE, _check_password, _email, _throttle
from app.schemas.api import (
    CodeSentOut,
    PermissionOut,
    RoleOut,
    SessionOut,
    StaffAcceptStartIn,
    StaffAcceptVerifyIn,
    StaffInviteIn,
    StaffInviteOut,
    StaffInvitePreview,
    StaffOut,
    StaffPatch,
    StaffTokenIn,
    TeamOut,
)
from app.services import email_templates as templates
from app.services import passwords, ratelimit, rbac
from app.services import sessions as sess
from app.services.audit import audit
from app.services.notifications import send_email

router = APIRouter(tags=["team"])
MANAGE = "team.manage"


def _hash(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


def _utc(d: datetime | None) -> datetime | None:
    return None if d is None else (d if d.tzinfo else d.replace(tzinfo=UTC))


def _label(role: str) -> str:
    if role == rbac.CUSTOM:
        return "Custom"
    r = rbac.ROLE_BY_KEY.get(role)
    return r.label if r else role


def _invite_hours() -> int:
    return max(48, get_settings().invite_ttl_hours)


def _join_url(token: str) -> str:
    return f"{get_settings().app_base_url}/admin/join?token={token}"


def _can_change(actor: Principal, row: StaffMember) -> bool:
    """Not yourself, and not someone who holds anything you don't."""
    return row.email.lower() != actor.user.email.lower() and rbac.may_grant(actor.permissions, row.permissions or [])


def _out(row: StaffMember, actor: Principal, last_login: datetime | None) -> StaffOut:
    return StaffOut(
        id=row.id,
        email=row.email,
        name=row.name,
        role=row.role,
        role_label=_label(row.role),
        permissions=sorted(row.permissions or []),
        status=row.status,
        invited_by=row.invited_by,
        last_login_at=last_login,
        invite_expires_at=_utc(row.invite_expires_at) if row.status == "invited" else None,
        editable=_can_change(actor, row),
        is_you=row.email.lower() == actor.user.email.lower(),
    )


async def _load(db: AsyncSession, staff_id: str) -> StaffMember:
    row = await db.get(StaffMember, staff_id)
    if row is None or row.status == "removed":
        raise HTTPException(404, "Team member not found")
    return row


def _guard(actor: Principal, row: StaffMember) -> None:
    if row.email.lower() == actor.user.email.lower():
        raise HTTPException(409, "You can't change your own access. Ask another admin.")
    if not rbac.may_grant(actor.permissions, row.permissions or []):
        raise HTTPException(403, "This person has access you don't have, so you can't change them.")


def _grant_check(actor: Principal, perms: list[str]) -> None:
    if not rbac.may_grant(actor.permissions, perms):
        raise HTTPException(403, "You can only give permissions you hold yourself.")


def _resolve(role: str, permissions: list[str] | None) -> tuple[str, list[str]]:
    try:
        return rbac.resolve(role, permissions)
    except rbac.Invalid as e:
        raise HTTPException(422, str(e)) from e


async def _send_invite(row: StaffMember, actor: Principal) -> tuple[bool, str]:
    token = secrets.token_urlsafe(32)
    row.token_hash = _hash(token)
    row.invite_expires_at = datetime.now(UTC) + timedelta(hours=_invite_hours())
    url = _join_url(token)
    subject, html, text = templates.staff_invite(actor.user.email, _label(row.role), url, _invite_hours(), row.name)
    return await send_email(row.email, subject, text, html), url


# ---------- managing the team ----------
@router.get("/v1/admin/staff", response_model=TeamOut)
async def team(actor: Principal = Depends(require(MANAGE)), db: AsyncSession = Depends(get_session)) -> TeamOut:
    rows = (
        (await db.execute(select(StaffMember).where(StaffMember.status != "removed").order_by(StaffMember.created_at)))
        .scalars()
        .all()
    )
    emails = rbac.owner_emails() | {r.email.lower() for r in rows}
    logins = {
        u.email.lower(): u.last_login_at
        for u in (await db.execute(select(User).where(User.email.in_(emails)))).scalars()
    }
    owners = [
        StaffOut(
            id=f"owner:{e}",
            email=e,
            name="",
            role=rbac.OWNER,
            role_label="Owner",
            permissions=sorted(rbac.ALL),
            status="owner",
            last_login_at=logins.get(e),
            editable=False,
            is_you=e == actor.user.email.lower(),
        )
        for e in sorted(rbac.owner_emails())
    ]
    return TeamOut(
        roles=[
            RoleOut(key=r.key, label=r.label, description=r.description, permissions=sorted(r.permissions))
            for r in rbac.ROLES
        ],
        permissions=[PermissionOut(key=p.key, label=p.label, group=p.group) for p in rbac.PERMISSIONS],
        members=[*owners, *[_out(r, actor, logins.get(r.email.lower())) for r in rows]],
        your_permissions=sorted(actor.permissions),
    )


@router.post("/v1/admin/staff", response_model=StaffInviteOut)
async def invite_member(
    body: StaffInviteIn,
    request: Request,
    actor: Principal = Depends(require(MANAGE)),
    db: AsyncSession = Depends(get_session),
) -> StaffInviteOut:
    email = str(body.email).lower()
    if rbac.is_owner(email):
        raise HTTPException(409, "That person is already an owner, with full access.")
    role, perms = _resolve(body.role, body.permissions)
    _grant_check(actor, perms)
    row = await rbac.staff_row(db, email)
    if row is not None and row.status in ("active", "suspended"):
        raise HTTPException(409, "That person is already on the team.")
    user = (await db.execute(select(User).where(User.email == email))).scalar_one_or_none()
    if user is not None and row is None:
        raise HTTPException(409, "That email already has a Cover Founder account, so it can't also join the team.")
    if row is None:
        row = StaffMember(
            email=email, role=role, permissions=perms, workspace_id=actor.workspace.id, invited_by=actor.user.email
        )
        db.add(row)
    row.name = body.name.strip()
    row.role, row.permissions = role, perms
    row.status, row.invited_by, row.accepted_at = "invited", actor.user.email, None  # also revives a removed member
    emailed, url = await _send_invite(row, actor)
    audit(
        db,
        actor.user.email,
        "staff.invite",
        target_type="staff",
        target_id=email,
        detail={"role": role, "permissions": perms},
        request=request,
    )
    await db.commit()
    return StaffInviteOut(member=_out(row, actor, None), emailed=emailed, join_url=None if emailed else url)


@router.patch("/v1/admin/staff/{staff_id}", response_model=StaffOut)
async def update_member(
    staff_id: str,
    body: StaffPatch,
    request: Request,
    actor: Principal = Depends(require(MANAGE)),
    db: AsyncSession = Depends(get_session),
) -> StaffOut:
    row = await _load(db, staff_id)
    _guard(actor, row)
    before = {"role": row.role, "permissions": list(row.permissions or []), "status": row.status}
    if body.name is not None:
        row.name = body.name.strip()
    if body.role is not None:
        role, perms = _resolve(body.role, body.permissions if body.permissions is not None else row.permissions)
        _grant_check(actor, perms)
        row.role, row.permissions = role, perms
    elif body.permissions is not None:
        role, perms = _resolve(rbac.CUSTOM, body.permissions)
        _grant_check(actor, perms)
        row.role, row.permissions = role, perms
    if body.status is not None:
        if row.status == "invited":
            raise HTTPException(409, "They haven't joined yet. Cancel the invitation instead.")
        row.status = body.status
        if body.status == "suspended":
            await rbac.revoke_sessions(db, row)  # signed out everywhere, immediately
    audit(
        db,
        actor.user.email,
        "staff.update",
        target_type="staff",
        target_id=row.email,
        detail={"before": before, "after": {"role": row.role, "permissions": row.permissions, "status": row.status}},
        request=request,
    )
    await db.commit()
    login = (await db.execute(select(User.last_login_at).where(User.email == row.email))).scalar_one_or_none()
    return _out(row, actor, login)


@router.post("/v1/admin/staff/{staff_id}/resend", response_model=StaffInviteOut)
async def resend_invite(
    staff_id: str,
    request: Request,
    actor: Principal = Depends(require(MANAGE)),
    db: AsyncSession = Depends(get_session),
) -> StaffInviteOut:
    row = await _load(db, staff_id)
    _guard(actor, row)
    if row.status != "invited":
        raise HTTPException(409, "They've already joined.")
    emailed, url = await _send_invite(row, actor)  # a fresh link; the old one stops working
    audit(db, actor.user.email, "staff.resend", target_type="staff", target_id=row.email, request=request)
    await db.commit()
    return StaffInviteOut(member=_out(row, actor, None), emailed=emailed, join_url=None if emailed else url)


@router.delete("/v1/admin/staff/{staff_id}")
async def remove_member(
    staff_id: str,
    request: Request,
    actor: Principal = Depends(require(MANAGE)),
    db: AsyncSession = Depends(get_session),
) -> dict:
    row = await _load(db, staff_id)
    _guard(actor, row)
    row.status, row.permissions, row.token_hash, row.invite_expires_at = "removed", [], None, None
    await rbac.revoke_sessions(db, row)
    audit(db, actor.user.email, "staff.remove", target_type="staff", target_id=row.email, request=request)
    await db.commit()
    return {"ok": True}


# ---------- joining (public) ----------
async def _pending(db: AsyncSession, token: str) -> StaffMember:
    row = (await db.execute(select(StaffMember).where(StaffMember.token_hash == _hash(token)))).scalar_one_or_none()
    if (
        row is None
        or row.status != "invited"
        or (_utc(row.invite_expires_at) or datetime.min.replace(tzinfo=UTC)) < datetime.now(UTC)
    ):
        raise BAD_INVITE
    return row


@router.post("/v1/auth/staff/invite", response_model=StaffInvitePreview)
async def invite_preview(
    body: StaffTokenIn, request: Request, db: AsyncSession = Depends(get_session)
) -> StaffInvitePreview:
    await _throttle(request, "staff-invite", ratelimit.client_ip(request), (30, 3600), (60, 3600))
    row = await _pending(db, body.token)
    return StaffInvitePreview(
        email_hint=sess.mask_email(row.email), name=row.name, role_label=_label(row.role), invited_by=row.invited_by
    )


@router.post("/v1/auth/staff/accept/start", response_model=CodeSentOut)
async def accept_start(
    body: StaffAcceptStartIn, request: Request, bg: BackgroundTasks, db: AsyncSession = Depends(get_session)
) -> CodeSentOut:
    await _throttle(request, "staff-accept", body.token[:24], (5, 3600), (20, 3600))
    row = await _pending(db, body.token)
    _check_password(body.password, row.email)
    code = await sess.issue_code(
        db,
        row.email,
        "staff",
        invite_id=row.id,
        password_hash=passwords.hash_password(body.password),
        ip=ratelimit.client_ip(request),
        workspace_name=(
            body.name.strip() or row.name or None
        ),  # the display name rides along until the code is confirmed
    )
    await db.commit()
    subject, html, text = _email("staff", code)
    bg.add_task(send_email, row.email, subject, text, html)
    return CodeSentOut(email_hint=sess.mask_email(row.email), expires_in_s=get_settings().otp_ttl_minutes * 60)


@router.post("/v1/auth/staff/accept/verify", response_model=SessionOut)
async def accept_verify(
    body: StaffAcceptVerifyIn, request: Request, db: AsyncSession = Depends(get_session)
) -> SessionOut:
    await _throttle(request, "staff-verify", body.token[:24], (10, 600), (30, 600))
    row = await _pending(db, body.token)
    code = await sess.check_code(db, row.email, "staff", body.code, invite_id=row.id)
    await db.commit()  # keeps the failed-attempt counter
    if code is None or not code.password_hash:
        raise BAD_CODE
    user = (await db.execute(select(User).where(User.email == row.email))).scalar_one_or_none()
    if user is None:
        user = User(email=row.email, role="staff", workspace_id=row.workspace_id, password_hash=code.password_hash)
        db.add(user)
    elif user.workspace_id == row.workspace_id:  # someone who was removed and has been invited back
        user.password_hash = code.password_hash
        await sess.revoke_all(db, user.id)
    else:
        raise BAD_INVITE
    await db.flush()
    row.user_id, row.status, row.accepted_at = user.id, "active", datetime.now(UTC)
    row.token_hash, row.invite_expires_at = None, None  # one use
    if code.workspace_name:
        row.name = code.workspace_name
    code.password_hash = None
    ns = await sess.create_session(db, user, request, otp_verified=True, operator=True)
    audit(
        db,
        row.email,
        "staff.join",
        target_type="staff",
        target_id=row.email,
        detail={"role": row.role, "invited_by": row.invited_by},
        request=request,
    )
    await db.commit()
    return SessionOut(token=ns.token, expires_at=ns.row.expires_at, otp_required=False)
