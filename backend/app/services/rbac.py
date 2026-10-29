"""Back-office roles and permissions.

Cover Founder's owners (the OPERATOR_EMAILS setting) always hold every permission and can't be edited or removed from the
back office. Everyone else on the team is a `StaffMember` with a role, which is a named set of permissions, or a custom list.
Permissions are checked on the server for every request; the back office only hides what a person can't use.

Nobody can hand out a permission they don't hold themselves, can change their own access, or change someone who holds
permissions they lack, so an admin can't promote themselves or anyone above them.
"""

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import StaffMember
from app.services import sessions as sess


@dataclass(frozen=True)
class Perm:
    key: str
    label: str
    group: str


PERMISSIONS: tuple[Perm, ...] = (
    Perm("overview.view", "See the overview and system health", "Business"),
    Perm("customers.view", "See customers and their videos", "Business"),
    Perm("customers.manage", "Invite customers, change their credits, caps and status", "Business"),
    Perm("finance.view", "See revenue, payments, vendor costs and budgets", "Finance"),
    Perm("finance.manage", "Edit credit packs and vendor budgets", "Finance"),
    Perm("review.manage", "Decide the review queue", "Operations"),
    Perm("operations.view", "See the queue and jobs", "Operations"),
    Perm("operations.manage", "Retry failed videos", "Operations"),
    Perm("settings.manage", "Change system switches and limits", "Operations"),
    Perm("presenter.manage", "Manage the presenter clip library", "Content"),
    Perm("audit.view", "See the audit log", "Security"),
    Perm("team.manage", "Invite and manage the back-office team", "Security"),
)
ALL = frozenset(p.key for p in PERMISSIONS)


@dataclass(frozen=True)
class Role:
    key: str
    label: str
    description: str
    permissions: frozenset[str]


ROLES: tuple[Role, ...] = (
    Role("admin", "Admin", "Everything, including managing the team (within their own access).", ALL),
    Role(
        "support",
        "Support",
        "Helps customers and keeps videos moving: reviews, retries, and customer look-ups.",
        frozenset(
            {"overview.view", "customers.view", "review.manage", "operations.view", "operations.manage"},
        ),
    ),
    Role(
        "finance",
        "Finance",
        "Revenue, payments, credit packs and vendor budgets.",
        frozenset({"overview.view", "customers.view", "finance.view", "finance.manage"}),
    ),
    Role(
        "content",
        "Content",
        "The presenter clip library and the review queue.",
        frozenset({"overview.view", "presenter.manage", "review.manage"}),
    ),
    Role(
        "viewer",
        "Viewer",
        "Read-only: can look, can't change anything.",
        frozenset({"overview.view", "customers.view", "finance.view", "operations.view", "audit.view"}),
    ),
)
ROLE_BY_KEY = {r.key: r for r in ROLES}
CUSTOM = "custom"
OWNER = "owner"


class Invalid(ValueError):
    """The role or permission list isn't acceptable (the message is shown to the person)."""


def resolve(role: str, permissions: list[str] | None) -> tuple[str, list[str]]:
    """The (role, sorted permission list) to store. A named role means exactly its permissions; "custom" means the given ones."""
    if role == CUSTOM:
        chosen = set(permissions or [])
        unknown = chosen - ALL
        if unknown:
            raise Invalid(f"Unknown permission: {sorted(unknown)[0]}")
        if not chosen:
            raise Invalid("Choose at least one permission, or pick a role.")
        return CUSTOM, sorted(chosen)
    found = ROLE_BY_KEY.get(role)
    if found is None:
        raise Invalid("Choose a role.")
    return found.key, sorted(found.permissions)


def owner_emails() -> set[str]:
    from app.config import get_settings

    return {e.strip().lower() for e in get_settings().operator_emails.split(",") if e.strip()}


def is_owner(email: str) -> bool:
    return email.lower() in owner_emails()


async def staff_row(db: AsyncSession, email: str) -> StaffMember | None:
    return (await db.execute(select(StaffMember).where(StaffMember.email == email.lower()))).scalar_one_or_none()


async def permissions_for(db: AsyncSession, email: str) -> frozenset[str]:
    """What this signed-in person may do in the back office: everything for an owner; for the team, their permissions while
    their membership is active; nothing otherwise."""
    if is_owner(email):
        return ALL
    row = await staff_row(db, email)
    if row is None or row.status != "active":
        return frozenset()
    return frozenset(row.permissions or []) & ALL


async def team_emails(db: AsyncSession) -> set[str]:
    """Everyone who belongs to the back-office team (owners and every staff member, whatever their status)."""
    rows = (await db.execute(select(StaffMember.email))).scalars().all()
    return owner_emails() | {e.lower() for e in rows}


def may_grant(actor: frozenset[str], wanted: list[str] | frozenset[str]) -> bool:
    return set(wanted) <= set(actor)


async def revoke_sessions(db: AsyncSession, row: StaffMember) -> None:
    if row.user_id:
        await sess.revoke_all(db, row.user_id)


async def blocked(db: AsyncSession, email: str) -> bool:
    """Was this person taken off the team (suspended or removed)? They can't sign in at all, not even to the customer app."""
    if is_owner(email):
        return False
    row = await staff_row(db, email)
    return row is not None and row.status in ("suspended", "removed")


async def role_label(db: AsyncSession, principal) -> str | None:
    if principal.is_owner:
        return "Owner"
    if not principal.is_operator:
        return None
    row = await staff_row(db, principal.user.email)
    if row is None:
        return None
    return "Custom" if row.role == CUSTOM else ROLE_BY_KEY[row.role].label if row.role in ROLE_BY_KEY else row.role
