"""Hard rule 1: no real news network names or marks in anything we render."""

import re

BANNED_TERMS = [
    "cnn", "bbc", "fox news", "sky news", "al jazeera", "msnbc", "reuters", "bloomberg tv", "nbc news",
    "abc news", "cbs news", "channels tv", "arise news", "dw news", "france 24", "cnbc",
]  # fmt: skip
_PATTERN = re.compile(r"(?<![a-z0-9])(" + "|".join(re.escape(t) for t in BANNED_TERMS) + r")(?![a-z0-9])", re.I)


def find_banned(text: str) -> list[str]:
    return sorted({m.group(1).lower() for m in _PATTERN.finditer(text)})


MAX_LOWER_THIRD_TITLE, MAX_LOWER_THIRD_SUBTITLE = 40, 60
MAX_TICKER_LINE, MAX_TICKER_LINES = 90, 8


def text_overflow(lower_thirds: list[dict], ticker_lines: list[str]) -> str | None:
    """Return a plain-language problem if on-screen text would not fit the fixed broadcast layout."""
    for lt in lower_thirds:
        if len(str(lt.get("title", ""))) > MAX_LOWER_THIRD_TITLE:
            return f"A lower-third title is too long (max {MAX_LOWER_THIRD_TITLE} characters)."
        if len(str(lt.get("subtitle", ""))) > MAX_LOWER_THIRD_SUBTITLE:
            return f"A lower-third subtitle is too long (max {MAX_LOWER_THIRD_SUBTITLE} characters)."
    if len(ticker_lines) > MAX_TICKER_LINES:
        return f"Too many ticker lines (max {MAX_TICKER_LINES})."
    if any(len(t) > MAX_TICKER_LINE for t in ticker_lines):
        return f"A ticker line is too long (max {MAX_TICKER_LINE} characters)."
    return None
