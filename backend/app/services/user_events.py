"""Product actions worth remembering for marketing segments. Recording one never blocks or fails the action itself."""

import logging

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import UserEvent

log = logging.getLogger("user_events")

# name -> the plain-words label used by segment rules
EVENTS: dict[str, str] = {
    "brand_saved": "saved their brand kit",
    "video_shared": "shared a video link",
}


def record(db: AsyncSession, user_id: str, name: str) -> None:
    """Stage an event in the caller's transaction, so it is saved (or not) together with the action. Unknown names are ignored."""
    if name not in EVENTS:
        log.warning("unknown event %s", name)
        return
    db.add(UserEvent(user_id=user_id, name=name))
