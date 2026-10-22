"""Content moderation for briefs, scripts and founder transcripts.

Two layers, worst verdict wins:
  1. Deterministic rules below. Cheap, explainable, and the same every time. These are STARTER rules written by an
     engineer: a human policy owner should review and tune them (docs/security-review.md).
  2. An optional LLM check (ScriptLLM.moderate) for what keyword rules can't see.

Levels: allow -> proceeds. review -> held for an operator (nothing paid runs until approved).
block -> refused outright. The person sees a plain-language reason, never our rule text.
"""

import hashlib
import re
from dataclasses import dataclass, field

LEVELS = {"allow": 0, "review": 1, "block": 2}

I = re.IGNORECASE  # noqa: E741


def _r(p: str) -> re.Pattern[str]:
    return re.compile(p, I)


# (category, level, pattern, plain-language message)
RULES: list[tuple[str, str, re.Pattern[str], str]] = [
    (
        "illegal_goods",
        "block",
        _r(
            r"\b(sell|selling|buy|buying|order|supply|supplying)\b[^.]{0,40}\b(cocaine|heroin|meth(amphetamine)?|fentanyl|firearms?|assault rifles?|counterfeit (money|notes|currency)|fake (ids?|passports?)|stolen (cards?|data|identities))\b"
        ),
        "Content about selling illegal goods can't be used.",
    ),
    (
        "child_safety",
        "block",
        _r(r"\bchild(ren)?\b[^.]{0,30}\b(porn\w*|sexual\w*|explicit)\b"),
        "This content can't be used.",
    ),
    (
        "violence",
        "block",
        _r(r"\b(kill|murder|bomb|shoot|exterminate)\b[^.]{0,20}\b(them|him|her|everyone|all of|people)\b|\bdeath to\b"),
        "Content that promotes violence can't be used.",
    ),
    (
        "malware_fraud",
        "block",
        _r(
            r"\b(phishing kit|ransomware|steal (passwords?|credentials|card numbers)|credit card (skimmer|generator))\b"
        ),
        "Content that promotes fraud or malware can't be used.",
    ),
    (
        "financial_promises",
        "review",
        _r(
            r"\b(guaranteed (returns?|profits?|income)|risk[- ]free (investment|returns?)|double your money|get rich quick|100% (profit|returns?)|ponzi|pyramid scheme|passive income guaranteed)\b"
        ),
        "Investment promises need a quick check by our team.",
    ),
    (
        "health_claims",
        "review",
        _r(
            r"\b(miracle cure|(cures?|treats?|prevents?|reverses?)\s+(cancer|diabetes|covid(-19)?|hiv|aids|malaria|hypertension)|lose \d+\s?(kg|kilos?|lbs|pounds) in)\b"
        ),
        "Health claims need a quick check by our team.",
    ),
    (
        "regulated_services",
        "review",
        _r(r"\b(payday loans?|forex signals?|crypto giveaway|betting tips|casino|sports ?betting|online gambling)\b"),
        "Regulated services need a quick check by our team.",
    ),
    (
        "political",
        "review",
        _r(r"\b(vote for|elect|re-?elect|campaign(ing)? for|political party|election campaign)\b"),
        "Political content needs a quick check by our team.",
    ),
    (
        "adult_content",
        "review",
        _r(r"\b(porn\w*|escort services?|nsfw|adult content|onlyfans)\b"),
        "Adult content needs a quick check by our team.",
    ),
    (
        "false_endorsement",
        "review",
        _r(
            r"\b(endorsed|approved|certified|sponsored|backed|partnered) (by|with) (the )?(president|government|ministry|who|world health organi[sz]ation|un|united nations|world bank|google|microsoft|apple|meta|amazon|openai|nasa)\b"
        ),
        "Endorsements by well-known organisations need a quick check by our team.",
    ),
    (
        "personal_data",
        "review",
        _r(r"[\w.+-]+@[\w-]+\.[\w.]{2,}|(?<!\d)(\+?\d[\d\s().-]{8,}\d)(?!\d)"),
        "Personal contact details need a quick check by our team.",
    ),
]


@dataclass
class Verdict:
    level: str = "allow"
    categories: list[str] = field(default_factory=list)
    messages: list[str] = field(default_factory=list)
    source: str = "rules"

    def merge(self, other: "Verdict") -> "Verdict":
        level = max((self.level, other.level), key=lambda x: LEVELS[x])
        return Verdict(
            level=level,
            categories=sorted(set(self.categories) | set(other.categories)),
            messages=list(dict.fromkeys(self.messages + other.messages)),
            source="+".join(dict.fromkeys([self.source, other.source])),
        )


def screen_text(text: str) -> Verdict:
    v = Verdict()
    for category, level, pattern, message in RULES:
        if pattern.search(text):
            v = v.merge(Verdict(level, [category], [message]))
    return v


def fingerprint(*parts: str) -> str:
    """Stable id for 'the exact content that was reviewed', so an edit invalidates an earlier approval."""
    return hashlib.sha256("\x1f".join(parts).encode()).hexdigest()[:32]


def excerpt(text: str, limit: int = 1500) -> str:
    return text if len(text) <= limit else text[:limit] + "…"


def script_text(
    brief: str, segments: list[dict], ticker: list[str], lower_thirds: list[dict], questions: list[str]
) -> str:
    lt = " ".join(f"{x.get('title', '')} {x.get('subtitle', '')}" for x in lower_thirds)
    return "\n".join([brief, *(s.get("text", "") for s in segments), *ticker, lt, *questions])
