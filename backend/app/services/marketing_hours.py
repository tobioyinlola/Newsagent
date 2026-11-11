"""Sending hours: only email people during the day where they live. Used by workflows and campaigns."""

from datetime import UTC, datetime, time, timedelta
from zoneinfo import ZoneInfo, ZoneInfoNotFoundError

from pydantic import BaseModel, Field, model_validator

from app.config import get_settings

COUNTRY_TZ = {
    "nigeria": "Africa/Lagos",
    "ghana": "Africa/Accra",
    "kenya": "Africa/Nairobi",
    "south africa": "Africa/Johannesburg",
    "egypt": "Africa/Cairo",
    "united kingdom": "Europe/London",
    "uk": "Europe/London",
    "england": "Europe/London",
    "united states": "America/New_York",
    "usa": "America/New_York",
    "us": "America/New_York",
    "canada": "America/Toronto",
    "india": "Asia/Kolkata",
    "united arab emirates": "Asia/Dubai",
    "uae": "Asia/Dubai",
    "germany": "Europe/Berlin",
    "france": "Europe/Paris",
}


class Hours(BaseModel):
    enabled: bool = True
    start: int = Field(9, ge=0, le=23)
    end: int = Field(18, ge=1, le=24)

    @model_validator(mode="after")
    def _order(self) -> "Hours":
        if self.start >= self.end:
            raise ValueError("The sending hours must start before they end.")
        return self


def tz_for(country: str | None) -> ZoneInfo:
    for name in (COUNTRY_TZ.get((country or "").strip().lower()), get_settings().marketing_default_timezone, "UTC"):
        if name:
            try:
                return ZoneInfo(name)
            except ZoneInfoNotFoundError:
                continue
    return ZoneInfo("UTC")


def next_open(now: datetime, tz: ZoneInfo, start: int, end: int) -> datetime | None:
    """None if `now` is inside the sending hours where the person lives; otherwise when the hours next open (UTC)."""
    local = now.astimezone(tz)
    if start <= local.hour < end:
        return None
    day = local.date() if local.hour < start else local.date() + timedelta(days=1)
    return datetime.combine(day, time(start), tzinfo=tz).astimezone(UTC)
