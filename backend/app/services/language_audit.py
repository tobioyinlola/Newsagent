"""Explicit abusive-language screening of interview transcripts, with word boundaries.

A flagged answer is retained privately for audit and retake; no audio is silently cut or censored.
"""

import re
import unicodedata

_WORDS = re.compile(
    r"(?<!\w)(?:fuck(?:ing|ed|er|ers)?|motherfucker(?:s)?|bullshit|shit(?:ty)?|asshole(?:s)?|bastard(?:s)?|bitch(?:es)?|cunt(?:s)?|dickhead(?:s)?|idiot(?:s)?|moron(?:s)?)(?!\w)",
    re.I,
)
_MASKED = re.compile(r"(?<!\w)(?:f[\W_]*[u*@][\W_]*[c*@][\W_]*k|s[\W_]*h[\W_]*[i*@][\W_]*t)(?!\w)", re.I)
MESSAGE = "Abusive language was detected in this answer. Please record it again using respectful language."


def has_abusive_language(text: str) -> bool:
    normalized = unicodedata.normalize("NFKC", text or "")
    return bool(_WORDS.search(normalized) or _MASKED.search(normalized))


def must_retake(take) -> bool:
    return "abusive_language" in (take.flags or []) or has_abusive_language(take.transcript or "")


def enforce(takes: dict, included=None):
    from fastapi import HTTPException

    bad = [q + 1 for q, take in takes.items() if (included is None or q in included) and must_retake(take)]
    if bad:
        raise HTTPException(
            422,
            {
                "error": "abusive_language",
                "message": MESSAGE + " Questions: " + ", ".join(map(str, sorted(bad))),
                "questions": sorted(bad),
            },
        )
