"""What a video costs and what credits are worth.

One video costs `credits_per_video` credit (1), whatever the vendors charge us for it. One credit is sold at `usd_per_credit`
($2.70). Custom quantities use the server-quoted credit price with a $10 minimum. People can also buy fixed amounts (`credit_purchase_usd`: $1, $10, $50, $100, $200) and are given amount / $2.70 credits once the
payment has gone through. A new workspace starts with `signup_credits` (1): one free video. After that, starting a video needs
a credit; with none left the app asks them to buy more.

The price is taken once, when the video is started (the project is created), as one ledger row, so the ledger still sums to the
balance. Making changes to a video afterwards (a new script version, a retry, a re-render) is not a new video and costs nothing.
"""

import hashlib
from dataclasses import dataclass
from decimal import ROUND_CEILING, ROUND_FLOOR, ROUND_HALF_UP, Decimal

from sqlalchemy import select
from sqlalchemy.ext.asyncio import AsyncSession

from app.config import get_settings
from app.models import Project, Workspace
from app.services import ledger

CENT = Decimal("0.01")


class InsufficientCredits(Exception):
    def __init__(self, balance: Decimal, needed: Decimal) -> None:
        super().__init__("not enough credits")
        self.balance, self.needed = balance, needed


class SpendCapReached(Exception):
    pass


def usd_per_credit() -> Decimal:
    return Decimal(get_settings().usd_per_credit)


def credits_per_video() -> Decimal:
    return Decimal(get_settings().credits_per_video)


def credits_for_usd(usd: Decimal | str | int) -> Decimal:
    """The credits a payment of `usd` buys (to the nearest 0.01)."""
    return (Decimal(usd) / usd_per_credit()).quantize(CENT, rounding=ROUND_HALF_UP)


def ngn_for_usd(usd: Decimal) -> Decimal:
    return (usd * get_settings().ngn_per_usd).quantize(CENT, rounding=ROUND_HALF_UP)


def videos_for(credits: Decimal) -> int:
    """Whole videos these credits pay for."""
    return int((credits / credits_per_video()).to_integral_value(rounding=ROUND_FLOOR))


@dataclass(frozen=True)
class CreditOption:
    amount_usd: Decimal
    credits: Decimal
    videos: int


def purchase_options() -> list[CreditOption]:
    amounts = sorted({Decimal(a.strip()) for a in get_settings().credit_purchase_usd.split(",") if a.strip()})
    return [CreditOption(a, credits_for_usd(a), videos_for(credits_for_usd(a))) for a in amounts]


def option_for(amount_usd: Decimal) -> CreditOption | None:
    return next((o for o in purchase_options() if o.amount_usd == Decimal(amount_usd)), None)


CUSTOM_MIN_USD = Decimal("10")
CUSTOM_MAX_USD = Decimal("99999999.99")  # Checkout's Numeric(12, 4) storage bound.


def minimum_custom_credits() -> Decimal:
    return (CUSTOM_MIN_USD / usd_per_credit()).quantize(CENT, rounding=ROUND_CEILING)


def custom_option(quantity: Decimal) -> CreditOption:
    if not quantity.is_finite() or quantity <= 0 or quantity != quantity.quantize(CENT):
        raise ValueError("Enter a positive number of credits with up to 2 decimal places.")
    amount = (quantity * usd_per_credit()).quantize(CENT, rounding=ROUND_HALF_UP)
    if amount < CUSTOM_MIN_USD:
        raise ValueError(f"Custom purchases start at $10 USD. Enter at least {minimum_custom_credits()} credits.")
    if amount > CUSTOM_MAX_USD or quantity > CUSTOM_MAX_USD:
        raise ValueError("This custom purchase is too large. Please enter a smaller amount.")
    return CreditOption(amount, quantity.quantize(CENT), videos_for(quantity))


def custom_quote_version(option: CreditOption) -> str:
    return hashlib.sha256(
        f"{option.credits:.2f}|{option.amount_usd:.2f}|{usd_per_credit().normalize()}".encode()
    ).hexdigest()


async def charge_video(session: AsyncSession, workspace_id: str, project: Project) -> None:
    """Take the price of a video from the workspace's credits. Raises InsufficientCredits (nothing changes) when it can't pay.
    Safe to repeat for the same project: the ledger reference makes a second call a no-op."""
    price = credits_per_video()
    ws = (await session.execute(select(Workspace).where(Workspace.id == workspace_id).with_for_update())).scalar_one()
    enforce = get_settings().enforce_limits
    if enforce and ws.credit_balance < price:
        raise InsufficientCredits(ws.credit_balance, price)
    if enforce and ws.spend_cap and ws.spent_total + price > ws.spend_cap:
        raise SpendCapReached
    tx = await ledger.apply(
        session,
        ws,
        -price,
        "usage",
        project_id=project.id,
        stage="video",
        ref=f"video:{project.id}",
        description="Video (1 credit)" if price == 1 else f"Video ({price} credits)",
    )
    if tx is not None:
        ws.spent_total += price
