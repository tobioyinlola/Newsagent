"""Media packages: what they cost, whether they can be bought right now, and taking a slot when one is bought."""

from datetime import datetime
from decimal import ROUND_HALF_UP, Decimal
from typing import cast

from sqlalchemy import CursorResult, select, update
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import DistributionPackage
from app.models.base import utcnow
from app.services import credits

CENT = Decimal("0.01")


def _aware(value: datetime) -> datetime:
    return value if value.tzinfo else value.replace(tzinfo=utcnow().tzinfo)


def credit_price(pkg: DistributionPackage) -> Decimal | None:
    """What the package costs in credits: its US-dollar price at the platform's credit price. None for a custom quote."""
    return None if pkg.usd_price is None else credits.credits_for_usd(pkg.usd_price)


def state(pkg: DistributionPackage, now: datetime | None = None) -> str:
    """open | quote (priced by us, not sold here) | not_started | ended | sold_out | off"""
    now = now or utcnow()
    if not pkg.active:
        return "off"
    if pkg.starts_at and now < _aware(pkg.starts_at):
        return "not_started"
    if pkg.ends_at and now > _aware(pkg.ends_at):
        return "ended"
    if pkg.slots_total is not None and pkg.slots_taken >= pkg.slots_total:
        return "sold_out"
    return "open" if pkg.usd_price is not None else "quote"


def view(pkg: DistributionPackage, now: datetime | None = None) -> dict:
    price = credit_price(pkg)
    left = None if pkg.slots_total is None else max(0, pkg.slots_total - pkg.slots_taken)
    off = None
    if pkg.standard_usd and pkg.usd_price and pkg.standard_usd > pkg.usd_price:
        off = int(((pkg.standard_usd - pkg.usd_price) / pkg.standard_usd * 100).quantize(Decimal("1"), rounding=ROUND_HALF_UP))
    return {
        "id": pkg.id,
        "slug": pkg.slug,
        "kind": pkg.kind,
        "region": pkg.region,
        "campaign": pkg.campaign,
        "name": pkg.name,
        "usd_price": None if pkg.usd_price is None else str(pkg.usd_price),
        "standard_usd": None if pkg.standard_usd is None else str(pkg.standard_usd),
        "percent_off": off,
        "credits": None if price is None else str(price),
        "local_prices": pkg.local_prices or {},
        "outlets": list(pkg.outlet_names or []),
        "includes": list(pkg.includes or []),
        "ideal_for": pkg.ideal_for,
        "note": pkg.note,
        "slots_total": pkg.slots_total,
        "slots_left": left,
        "ends_at": pkg.ends_at,
        "state": state(pkg, now),
    }


async def listing(db: AsyncSession, *, everything: bool = False) -> list[DistributionPackage]:
    q = select(DistributionPackage).order_by(DistributionPackage.sort)
    if not everything:
        q = q.where(DistributionPackage.active.is_(True))
    return list((await db.execute(q)).scalars())


async def by_id(db: AsyncSession, id: str) -> DistributionPackage | None:
    return (await db.execute(select(DistributionPackage).where(DistributionPackage.id == id))).scalar_one_or_none()


async def claim(db: AsyncSession, pkg: DistributionPackage) -> bool:
    """Take one slot. A single conditional update, so two buyers can never share the last one."""
    if pkg.slots_total is None:
        return True
    got = await db.execute(
        update(DistributionPackage)
        .where(DistributionPackage.id == pkg.id, DistributionPackage.slots_taken < DistributionPackage.slots_total)
        .values(slots_taken=DistributionPackage.slots_taken + 1)
    )
    return cast(CursorResult, got).rowcount == 1


def lines(pkg: DistributionPackage, catalog: list[dict], total: Decimal) -> list[dict]:
    """The request lines for a package: its catalogue outlets share the package price between them. A package with none of our
    outlets (a partnership, say) is one line for the whole package; the team follows it up."""
    by = {o["id"]: o for o in catalog}
    held = [by[i] for i in (pkg.outlet_ids or []) if i in by]
    if not held:
        return [{"id": f"pkg:{pkg.slug}", "name": pkg.name, "region": pkg.region or "Package", "package": True, "base_credits": str(total),
                 "logo_fee": "0", "picture_fee": "0", "include_logo": False, "picture_count": 0, "picture_keys": [], "logo_key": None,
                 "accepts_logo": False, "accepts_images": False, "logo_credits": "0", "picture_credits": "0", "media_policy_configured": True,
                 "credits": str(total)}]
    share = (total / len(held)).quantize(CENT, rounding=ROUND_HALF_UP)
    out = []
    for n, o in enumerate(held):
        part = share if n < len(held) - 1 else total - share * (len(held) - 1)  # the cents never go missing
        out.append({**{k: o[k] for k in ["id", "name", "region", "accepts_logo", "accepts_images", "logo_credits", "picture_credits", "media_policy_configured"]},
                    "base_credits": str(part), "logo_fee": "0", "picture_fee": "0", "include_logo": False, "picture_count": 0,
                    "picture_keys": [], "logo_key": None, "package": True, "credits": str(part)})
    return out


def _norm(name: str) -> str:
    n = name.lower().replace(".com", "")
    return "".join(ch for ch in n if ch.isalnum())


def resolve(names: list[str], catalog: list[dict]) -> list[str]:
    """The outlets we hold in our catalogue among the names an operator typed. Matching ignores case, spaces and ".com", and knows the
    spellings the package document used. Names we do not hold are simply not matched: the team arranges those by hand."""
    from app.services.package_seed import CATALOG as ALIASES

    by = {_norm(o["name"]): o["id"] for o in catalog}
    out: list[str] = []
    for raw in names:
        n = raw.strip()
        if not n:
            continue
        found = by.get(_norm(n)) or ALIASES.get(n) or next((v for k, v in ALIASES.items() if _norm(k) == _norm(n)), None)
        if found and found not in out:
            out.append(found)
    return out
