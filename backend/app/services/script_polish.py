"""Keeps what the presenter says from repeating itself.

A video is spoken in several separately made pieces: the opening, a lead-in for each question, the closing. The pieces are
written at different moments (some by the language model, some by us), so the same thing can end up said twice: a hand-over
("let's hear from the founder") in the opening and again in the first question, an invitation to get featured written by the
model and added again by us, two "thank you for watching" lines. Said twice, the video sounds like a glitch.

Everything here is plain text work done before any presenter clip is ordered. It only ever removes words, so it can lower
what the presenter vendor charges for a video and can never raise it.
"""

import re

# A full stop after these does not end a sentence.
_ABBREVIATIONS = {
    "mr",
    "mrs",
    "ms",
    "dr",
    "prof",
    "inc",
    "ltd",
    "llc",
    "co",
    "corp",
    "st",
    "vs",
    "etc",
    "no",
    "jr",
    "sr",
}
_SPLIT = re.compile(r"(?<=[.!?])[\"')\]”’]*\s+")
_WORD = re.compile(r"[a-z0-9]+")
_STOP = {
    "a",
    "an",
    "and",
    "the",
    "to",
    "of",
    "in",
    "on",
    "for",
    "is",
    "are",
    "it",
    "that",
    "this",
    "with",
    "as",
    "at",
    "by",
}

_MIN_TOKENS = 3  # shorter sentences ("Thank you.") are only dropped when they are exact repeats
_SIMILAR = 0.8  # share of the shorter sentence's words that the other sentence also contains


def sentences(text: str) -> list[str]:
    """Split text into sentences, keeping their punctuation. Abbreviations like "Ltd." do not end a sentence."""
    pieces = [p for p in _SPLIT.split(" ".join(text.split())) if p]
    out: list[str] = []
    for piece in pieces:
        if out:
            last_word = out[-1].rstrip(".!?\"')]”’").rsplit(" ", 1)[-1].lower()
            if out[-1].endswith(".") and last_word in _ABBREVIATIONS:
                out[-1] = f"{out[-1]} {piece}"
                continue
        out.append(piece)
    return out


def _tokens(sentence: str) -> list[str]:
    return [w for w in _WORD.findall(sentence.lower()) if w not in _STOP]


def same_thing(a: str, b: str) -> bool:
    """Do two sentences say the same thing? Exact repeats always; otherwise one must contain nearly all the other's words."""
    ta, tb = _tokens(a), _tokens(b)
    if not ta or not tb:
        return False
    if ta == tb:
        return True
    if min(len(ta), len(tb)) < _MIN_TOKENS:
        return False
    sa, sb = set(ta), set(tb)
    return len(sa & sb) / min(len(sa), len(sb)) >= _SIMILAR


# Hand-over to the founder: "Let's hear from him now.", "Over to the founder.", "Joining us now is ..."
_HANDOVER = re.compile(
    r"\b(let'?s hear (from|what)|let us hear|over to|joins us|joining us|i spoke (to|with)|we spoke (to|with)|sat down with|"
    r"hear (it )?(directly )?from)\b",
    re.I,
)
# An invitation to get featured on Cover Founder.
_INVITE = re.compile(r"\bfeature[ds]?\b", re.I)
_INVITE_WHERE = re.compile(r"\b(cover founder|get in touch|contact us|reach out|talk to us)\b", re.I)
_THANKS = re.compile(r"\b(thank you|thanks) for (watching|joining us|tuning in)\b", re.I)


def is_invite(sentence: str) -> bool:
    return bool(_INVITE.search(sentence) and _INVITE_WHERE.search(sentence))


def has_invite(text: str) -> bool:
    return any(is_invite(s) for s in sentences(text))


def ends_with_handover(text: str) -> bool:
    """Does the text already end by passing over to the founder?"""
    parts = sentences(text)
    return bool(parts) and bool(_HANDOVER.search(parts[-1]))


def remove_repeats(parts: list[str]) -> list[str]:
    """The same pieces in the same order, with every sentence that repeats an earlier one (in this piece or an earlier piece)
    taken out, and at most one invitation to get featured and one "thank you for watching" kept (the last of each, so a
    closing stays a closing)."""
    kept: list[list[str]] = [[] for _ in parts]
    seen: list[str] = []
    for i, part in enumerate(parts):
        for s in sentences(part):
            if is_invite(s) or _THANKS.search(
                s
            ):  # closing lines: handled below, where the last of each is the one kept
                kept[i].append(s)
                continue
            if any(same_thing(s, earlier) for earlier in seen):
                continue
            kept[i].append(s)
            seen.append(s)
    for matcher in (is_invite, lambda s: bool(_THANKS.search(s))):
        hits = [(i, j) for i, sents in enumerate(kept) for j, s in enumerate(sents) if matcher(s)]
        for i, j in hits[:-1]:
            kept[i][j] = ""
    return [" ".join(s for s in sents if s) for sents in kept]
