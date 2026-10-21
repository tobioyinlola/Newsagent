"""Hard rule 1: no real news network names or marks in anything we render."""

import re

BANNED_TERMS = [
    "cnn", "bbc", "fox news", "sky news", "al jazeera", "msnbc", "reuters", "bloomberg tv", "nbc news",
    "abc news", "cbs news", "channels tv", "arise news", "dw news", "france 24", "cnbc",
]  # fmt: skip
_PATTERN = re.compile(r"(?<![a-z0-9])(" + "|".join(re.escape(t) for t in BANNED_TERMS) + r")(?![a-z0-9])", re.I)


def find_banned(text: str) -> list[str]:
    return sorted({m.group(1).lower() for m in _PATTERN.finditer(text)})
