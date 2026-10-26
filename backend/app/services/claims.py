"""Deterministic claims check (hard rule 3): flag numbers and superlatives for owner confirmation."""

import re

from app.integrations.llm.base import ClaimFlag

# A sentence ends at . ! ? followed by a space (so "$3.8M" and "5,000.50" stay whole), or at a line break.
_SENTENCE = re.compile(r"(?<=[.!?])\s+|\n+")

_PATTERNS: list[tuple[str, re.Pattern[str]]] = [
    ("revenue", re.compile(r"(\$|₦|€|£|revenue|ARR|MRR|profit)", re.I)),
    ("funding", re.compile(r"(raised|funding|seed|series [a-z]|valuation|investors?)", re.I)),
    (
        "users",
        re.compile(r"\b\d[\d,.]*\s*(k|m|million|thousand)?\s*(users|customers|merchants|clients|downloads)", re.I),
    ),
    ("ranking", re.compile(r"(#\s?1|ranked|top \d+|number one|leading)", re.I)),
    ("superlative", re.compile(r"\b(first|only|best|largest|fastest|biggest|most)\b", re.I)),
]


def detect_claims(text: str) -> list[ClaimFlag]:
    flags: list[ClaimFlag] = []
    seen: set[tuple[str, str]] = set()
    sentences = [x.strip().rstrip(".!?").strip() for x in _SENTENCE.split(text)]
    for category, pat in _PATTERNS:
        for sentence in sentences:
            if sentence and pat.search(sentence) and (sentence, category) not in seen:
                seen.add((sentence, category))
                flags.append(ClaimFlag(text=sentence, category=category))
    return flags
