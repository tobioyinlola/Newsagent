"""Deterministic claims check (hard rule 3): flag numbers and superlatives for owner confirmation."""

import re

from app.integrations.llm.base import ClaimFlag

_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("revenue", re.compile(r"[^.]*(\$|₦|€|£|revenue|ARR|MRR|profit)[^.]*", re.I)),
    ("funding", re.compile(r"[^.]*(raised|funding|seed|series [a-z]|valuation|investors?)[^.]*", re.I)),
    (
        "users",
        re.compile(
            r"[^.]*\b\d[\d,.]*\s*(k|m|million|thousand)?\s*(users|customers|merchants|clients|downloads)[^.]*", re.I
        ),
    ),
    ("ranking", re.compile(r"[^.]*(#\s?1|ranked|top \d+|number one|leading)[^.]*", re.I)),
    ("superlative", re.compile(r"[^.]*\b(first|only|best|largest|fastest|biggest|most)\b[^.]*", re.I)),
]


def detect_claims(text: str) -> list[ClaimFlag]:
    flags: list[ClaimFlag] = []
    seen: set[tuple[str, str]] = set()
    for category, pat in _PATTERNS:
        for m in pat.finditer(text):
            sentence = m.group(0).strip()
            if sentence and (sentence, category) not in seen:
                seen.add((sentence, category))
                flags.append(ClaimFlag(text=sentence, category=category))
    return flags
