"""The exchange rates package prices are shown with. Display only: the customer is always charged in US dollars (as credits).

The defaults are the rates the package document's own prices imply (for example, its Nigerian price is its US price at 1,400 naira to
the dollar). An operator can change them in the admin when the market moves; a price the document states in a currency is shown exactly
as written, and only the others are converted."""

from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.models import SystemSetting

KEY = "package_rates"

# currency -> (name, how many of it buy one US dollar). The order is the order they are offered in.
CURRENCIES: dict[str, tuple[str, str]] = {
    "USD": ("US dollar", "1"),
    "NGN": ("Nigerian naira", "1400"),
    "GBP": ("British pound", "0.7599"),
    "EUR": ("Euro", "0.9104"),
    "CAD": ("Canadian dollar", "1.4318"),
    "GHS": ("Ghanaian cedi", "11.7545"),
    "KES": ("Kenyan shilling", "129.92"),
    "UGX": ("Ugandan shilling", "4189.5"),
    "AED": ("UAE dirham", "3.6725"),
    "QAR": ("Qatari riyal", "3.64"),
    "CHF": ("Swiss franc", "0.8422"),
}


async def rates(db: AsyncSession) -> dict[str, str]:
    """Rates in force: the document's, with any the operator has changed."""
    row = (await db.execute(select(SystemSetting).where(SystemSetting.key == KEY))).scalar_one_or_none()
    saved = (row.value if row else {}) or {}
    return {code: str(saved.get(code, default)) for code, (_, default) in CURRENCIES.items()}


async def save(db: AsyncSession, values: dict[str, str]) -> dict[str, str]:
    clean: dict[str, str] = {}
    for code, raw in values.items():
        code = code.upper()
        if code not in CURRENCIES or code == "USD":
            continue
        n = Decimal(str(raw))
        if not (Decimal("0.0001") <= n <= Decimal("1000000")):
            raise ValueError(f"{code}: enter how many {CURRENCIES[code][0]} buy one US dollar")
        clean[code] = format(n.normalize(), "f")
    row = (await db.execute(select(SystemSetting).where(SystemSetting.key == KEY))).scalar_one_or_none()
    if row is None:
        db.add(SystemSetting(key=KEY, value=clean))
    else:
        row.value = {**(row.value or {}), **clean}
    await db.flush()
    return await rates(db)


def to_usd(amount: Decimal, code: str, table: dict[str, str]) -> Decimal | None:
    """What an amount in another currency is worth in US dollars, at the rates in force."""
    r = Decimal(table.get(code, "0") or "0")
    return None if r <= 0 else (amount / r).quantize(Decimal("0.01"))


def listing(table: dict[str, str]) -> list[dict]:
    return [{"code": c, "name": name, "per_usd": table[c]} for c, (name, _) in CURRENCIES.items()]
