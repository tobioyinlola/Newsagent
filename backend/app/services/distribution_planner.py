"""Suggests outlets for a story, as ready-made plans that fit a budget.

Plain rules, no model: every outlet gets a fit score from where it is, what it covers and what the person wants, and three plans
are built from the best-fitting outlets within the budget. The same inputs always give the same plans, and every suggestion carries
the reasons it was made. Prices are the catalogue's placement prices; a logo or pictures are added at the review step, so a plan's
total is "from" that amount."""

from collections import Counter
from dataclasses import dataclass, field
from decimal import ROUND_CEILING, Decimal

GOALS = ("credibility", "investors", "customers", "hiring")
DEFAULT_GOAL = "credibility"
# Topics and categories that are never suggested (they stay in the full list for people to choose themselves).
SKIP_TOPICS = {"Gossip Blogs"}
SKIP_CATEGORIES = {"Crypto News Channels"}

# Plans are layers: Essential, then Balanced adds to it, then Maximum reach adds to that.
# key: (name, one line, most outlets in the plan, how much cost counts against fit when adding)
PLANS = {
    "essential": ("Essential", "The best fits at the lowest cost", 3, 0.6),
    "balanced": ("Balanced", "Everything in Essential, plus a wider mix", 5, 0.5),
    "max": ("Maximum reach", "Everything in Balanced, plus as many strong fits as your budget allows", 8, 0.25),
}
THIN = 3  # a country with fewer outlets than this gets help from its region
REPEAT_DISCOUNT = 0.7  # each extra outlet from the same place and topic counts for less, so a plan is not five of the same


@dataclass
class Ask:
    budget: Decimal | None = None  # None: no limit, show what each plan would cost
    countries: list[str] = field(default_factory=list)  # where the readers are; empty = anywhere
    goal: str = DEFAULT_GOAL
    industry: str | None = None


def _money(v: Decimal) -> str:
    return format(v.normalize(), "f") if v else "0"


def _topic_weight(topic: str, goal: str, industry: str | None) -> float:
    """1 for any topic we suggest; more for the kind of readers the person's goal and business point to."""
    tech, news = topic == "Technology", topic == "General News"
    w = 1.0
    if (goal in {"credibility", "customers"} and news) or (goal in {"investors", "hiring"} and tech):
        w += 0.6
    elif goal in {"investors", "hiring"} and news:
        w += 0.2
    if industry == "technology" and tech:
        w += 0.4
    return w


def _topic_reason(topic: str, goal: str) -> str:
    if topic == "Technology":
        return "Reaches technology readers"
    return "A general news audience" if goal in {"credibility", "customers"} else "Reaches a broad news audience"


def fit(o: dict, ask: Ask, help_for: dict[str, str]) -> tuple[float, list[str]] | None:
    """How well one outlet suits the person, with the reasons; None when it should not be suggested at all."""
    if o["topic"] in SKIP_TOPICS or o.get("category") in SKIP_CATEGORIES or Decimal(str(o["credits"])) <= 0:
        return None
    reasons: list[str] = []
    if not ask.countries:
        place = 1.0
    elif o.get("country") in ask.countries:
        place = 3.0
        reasons.append(f"Based in {o['country']}")
    elif o.get("country") and o["region"] in help_for:  # nothing or little in the country asked for: the nearest we have
        place = 1.0
        reasons.append(f"Based in {o['country']}, the closest we have to {help_for[o['region']]}")
    else:
        return None
    reasons.append(_topic_reason(o["topic"], ask.goal))
    return place * _topic_weight(o["topic"], ask.goal, ask.industry), reasons


def _layers(ranked: list[tuple[float, list[str], dict]], countries: list[str], budget: Decimal | None) -> dict[str, list]:
    """Build Essential, then add to it for Balanced, then add to that for Maximum reach. Each layer first makes sure every country the
    person asked for (that we have outlets in) is covered, then adds whatever fits best, always inside what is left of the budget."""
    chosen: list[tuple[dict, list[str]]] = []
    pool = list(ranked)
    cells: Counter = Counter()
    left = budget
    out: dict[str, list] = {}

    def take(item, weight_key) -> None:
        nonlocal left
        pool.remove(item)
        _, reasons, o = item
        cells[(o.get("country"), o["topic"])] += 1
        chosen.append((o, reasons))
        if left is not None:
            left -= Decimal(str(o["credits"]))

    def best(candidates, exponent):
        top, top_value = None, -1.0
        for item in candidates:  # already best fit first, then by id, so on a tie the earlier one is kept
            score, _, o = item
            price = Decimal(str(o["credits"]))
            if left is not None and price > left:
                continue
            value = score * REPEAT_DISCOUNT ** cells[(o.get("country"), o["topic"])] / float(price) ** exponent
            if value > top_value:
                top, top_value = item, value
        return top

    for key, (_, _, most, exponent) in PLANS.items():
        if key == "essential":  # someone in every country they chose first, if the budget allows
            for c in countries:
                if len(chosen) >= most:
                    break
                pick = best([i for i in pool if i[2].get("country") == c], exponent)
                if pick:
                    take(pick, key)
        while len(chosen) < most:
            pick = best(pool, exponent)
            if pick is None:
                break
            take(pick, key)
        out[key] = list(chosen)
    return out


def _nice(v: Decimal) -> Decimal:
    step = Decimal(10) if v < 1000 else Decimal(50) if v < 5000 else Decimal(100)
    return (v / step).to_integral_value(rounding=ROUND_CEILING) * step


def recommend(outlets: list[dict], ask: Ask, *, balance: Decimal | None = None, known_countries: dict[str, str]) -> dict:
    """The plans for this person. `outlets` are the ones customers may see; `known_countries` maps each country we list to its region."""
    countries = [c for c in dict.fromkeys(ask.countries) if c in known_countries]
    ask = Ask(ask.budget, countries, ask.goal if ask.goal in GOALS else DEFAULT_GOAL, ask.industry)
    have = Counter(o.get("country") for o in outlets)
    help_for: dict[str, str] = {}  # region -> the thinly covered country it stands in for
    for c in countries:
        if have[c] < THIN:
            help_for.setdefault(known_countries[c], c)
    notes: list[str] = []
    for c in countries:
        if have[c] == 0:
            notes.append(f"We don't have outlets in {c} yet. Showing the closest in the region.")
        elif have[c] == 1:
            notes.append(f"We have just one outlet in {c}, so coverage there is limited.")
    ranked = []
    for o in outlets:
        f = fit(o, ask, help_for)
        if f:
            ranked.append((f[0], f[1], o))
    ranked.sort(key=lambda t: (-t[0], int(t[2]["id"])))
    cheapest = min((Decimal(str(o["credits"])) for _, _, o in ranked), default=None)

    def make(budget: Decimal | None) -> list[dict]:
        out: list[dict] = []
        last: frozenset = frozenset()
        for key, picks in _layers(ranked, countries, budget).items():
            ids = frozenset(o["id"] for o, _ in picks)
            if not picks or ids == last:
                continue
            last = ids
            name, line, _, _ = PLANS[key]
            total = sum((Decimal(str(o["credits"])) for o, _ in picks), Decimal(0))
            plan = {
                "key": key,
                "name": name,
                "summary": line,
                "total_credits": _money(total),
                "outlets": [
                    {k: o.get(k) for k in ("id", "name", "topic", "country", "region", "credits")} | {"reasons": r}
                    for o, r in picks
                ],
                "countries": sorted({o["country"] for o, _ in picks if o.get("country")}),
                "topics": sorted({o["topic"] for o, _ in picks}),
            }
            if balance is not None:
                plan["shortfall_credits"] = _money(max(Decimal(0), total - balance))
            out.append(plan)
        return out

    plans = make(ask.budget)
    open_plans = make(None) if ask.budget is not None else plans  # what the plans would cost with no limit, for budget hints
    presets = sorted({_nice(Decimal(p["total_credits"])) for p in open_plans})
    result = {
        "plans": plans,
        "suggested": {o["id"]: o["reasons"] for p in plans for o in p["outlets"]},
        "budget_presets": [_money(p) for p in presets],
        "cheapest_credits": _money(cheapest) if cheapest is not None else None,
        "notes": notes,
        "countries": countries,
        "goal": ask.goal,
    }
    if balance is not None:
        result["balance_credits"] = _money(balance)
    if not plans:
        if not ranked:
            result["empty"] = "We don't have outlets that match yet. Pick a different country or browse the full list."
        elif cheapest is not None and ask.budget is not None:
            result["empty"] = f"That budget is below our lowest price. The cheapest outlet starts at {_money(cheapest)} credits."
    return result


# ---------- the on/off switch ----------
SWITCH_KEY = "outlet_planner"


async def enabled(db) -> bool:
    """Whether customers and visitors are offered suggested plans. The operator's choice in the back office wins; until one is made,
    OUTLET_PLANNER decides (off unless set to "on")."""
    from app.config import get_settings
    from app.models import SystemSetting

    row = await db.get(SystemSetting, SWITCH_KEY)
    if row is not None and isinstance((row.value or {}).get("enabled"), bool):
        return bool(row.value["enabled"])
    return get_settings().outlet_planner.strip().lower() == "on"


async def switch_state(db) -> dict:
    from app.models import SystemSetting

    row = await db.get(SystemSetting, SWITCH_KEY)
    chosen = row is not None and isinstance((row.value or {}).get("enabled"), bool)
    return {
        "enabled": await enabled(db),
        "source": "back office" if chosen else "default",
        "changed_by": row.updated_by if chosen else None,
        "changed_at": row.updated_at.isoformat() if chosen and row.updated_at else None,
    }


async def set_enabled(db, actor: str, value: bool) -> None:
    from app.models import SystemSetting
    from app.models.base import utcnow

    row = await db.get(SystemSetting, SWITCH_KEY)
    if row is None:
        row = SystemSetting(key=SWITCH_KEY, value={})
        db.add(row)
    row.value, row.updated_by, row.updated_at = {"enabled": value}, actor, utcnow()
