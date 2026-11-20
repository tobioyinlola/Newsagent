"""The first-run questions a new customer is asked after signing up, and where each person is in them and in the guided tours.

The answers describe the business, so they live on the workspace (`Workspace.profile`) and show in the back office's customer view.
Progress belongs to the person (`User.onboarding`): the question flow's status and step, and for each tour the step reached, whether it
was finished and whether it was dismissed. Everything is optional: any question, any step and the whole flow can be skipped."""

import re
from datetime import UTC, datetime

# key -> label, in the order they are shown. The keys are what is stored.
ROLES = {
    "founder": "Founder or owner",
    "marketing": "Marketing or communications",
    "pr": "PR or media relations",
    "agency": "Agency or consultant",
    "executive": "Executive or manager",
    "other": "Something else",
}
SIZES = {
    "solo": "Just me",
    "2-10": "2 to 10 people",
    "11-50": "11 to 50 people",
    "51-200": "51 to 200 people",
    "201-1000": "201 to 1,000 people",
    "1000+": "More than 1,000 people",
}
GOALS = {
    "credibility": "Look credible and established",
    "customers": "Win more customers",
    "investors": "Reach investors",
    "hiring": "Attract talent and support hiring",
    "launch": "Announce a launch or news",
    "reputation": "Protect or improve our reputation",
}
HEARD = {
    "search": "A web search",
    "social": "Social media",
    "friend": "A friend or colleague",
    "event": "An event or conference",
    "newsletter": "An email or newsletter",
    "news": "An article or the news",
    "ai": "An AI assistant",
    "other": "Somewhere else",
}
STEPS = ["about_you", "your_business", "your_goals", "how_you_heard"]  # the cards, in order
STATUSES = {"pending", "in_progress", "done", "skipped"}

TEXT_LIMITS = {"contact_name": 120, "phone": 40, "website": 200, "heard_detail": 300}
MAX_TOURS = 60
TOUR_ID = re.compile(r"^[a-z0-9][a-z0-9-]{0,39}$")


def options() -> dict:
    return {
        "roles": [{"key": k, "label": v} for k, v in ROLES.items()],
        "sizes": [{"key": k, "label": v} for k, v in SIZES.items()],
        "goals": [{"key": k, "label": v} for k, v in GOALS.items()],
        "heard": [{"key": k, "label": v} for k, v in HEARD.items()],
        "steps": STEPS,
    }


def clean_answers(raw: dict) -> dict:
    """Keep only what we ask, tidied. Anything unknown or out of range is dropped rather than stored."""
    out: dict = {}
    for key, limit in TEXT_LIMITS.items():
        if key in raw and isinstance(raw[key], str):
            out[key] = " ".join(raw[key].split())[:limit]
    for key, allowed in (("role", ROLES), ("company_size", SIZES), ("heard_from", HEARD)):
        if key in raw:
            out[key] = raw[key] if raw[key] in allowed else ""
    if "goals" in raw:
        goals = raw["goals"] if isinstance(raw["goals"], list) else []
        out["goals"] = [g for g in dict.fromkeys(goals) if isinstance(g, str) and g in GOALS]
    if out.get("website"):
        site = out["website"].lower()
        if not site.startswith(("http://", "https://")):
            out["website"] = "https://" + out["website"]
    return out


def state(onboarding: dict | None, profile: dict | None) -> dict:
    """What the browser needs: where the questions stand, the saved answers and each tour's progress."""
    o = onboarding or {}
    q = o.get("profile") or {}
    return {
        "profile_status": q.get("status", "not_started"),  # not_started: an account from before these questions existed
        "profile_step": int(q.get("step", 0)),
        "profile": profile or {},
        "tours": o.get("tours") or {},
        "options": options(),
    }


def start_for_new_account() -> dict:
    return {"profile": {"status": "pending", "step": 0}, "tours": {}}


def set_progress(onboarding: dict | None, *, status: str | None, step: int | None) -> dict:
    o = dict(onboarding or {})
    q = dict(o.get("profile") or {})
    if status in STATUSES:
        q["status"] = status
        if status in {"done", "skipped"}:
            q["finished_at"] = datetime.now(UTC).isoformat()
    if step is not None:
        q["step"] = max(0, min(step, len(STEPS)))
    o["profile"] = q
    return o


def set_tour(onboarding: dict | None, tour_id: str, *, step: int, done: bool, dismissed: bool, reset: bool) -> dict:
    o = dict(onboarding or {})
    tours = dict(o.get("tours") or {})
    if reset:
        tours.pop(tour_id, None)
    else:
        if tour_id not in tours and len(tours) >= MAX_TOURS:
            raise ValueError("Too many tours")
        old = tours.get(tour_id) or {}
        tours[tour_id] = {
            "step": max(0, min(step, 100)),
            "done": bool(done or old.get("done")),
            "dismissed": bool(dismissed),
            "updated_at": datetime.now(UTC).isoformat(),
            **({"done_at": old.get("done_at") or datetime.now(UTC).isoformat()} if (done or old.get("done")) else {}),
        }
    o["tours"] = tours
    return o
