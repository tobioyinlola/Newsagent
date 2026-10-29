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


# The presenter passing the conversation over: "Let's hear from the founder." The question that follows opens with its own welcome.
_PASSOVER = re.compile(r"\b(let'?s hear (from|what)|let us hear|over to|hear (it )?(directly )?from)\b", re.I)


def strip_passover(text: str) -> str:
    """The text without its "let's hear from ..." hand-over lines (the first question welcomes the guest itself). Never empties it."""
    kept = [s for s in sentences(text) if not _PASSOVER.search(s)]
    return " ".join(kept) if kept else text


def strip_invites(text: str) -> str:
    """The text without any invitation to get featured: the closing card on screen carries the call to action, so the presenter
    never says it. Never empties it."""
    kept = [s for s in sentences(text) if not is_invite(s)]
    return " ".join(kept) if kept else text


# Lines that round the programme off: "That's all for this edition.", "Thank you for watching.", "Have a wonderful evening."
_SIGNOFF = re.compile(
    r"\b(that'?s all for|thank you for watching|thanks for watching|that was cover founder|until next time|see you (next time|soon)|"
    r"good ?night|have a (wonderful|great|good|lovely) (day|evening|night|week)|for cover founder news)\b",
    re.I,
)


def one_signoff(text: str) -> str:
    """Rounds off once. Sign-off lines that follow each other ("That was Cover Founder News. Thank you for watching.") are one
    round-up and stay together. If the closing rounds off in two separate places, only the last round-up is kept, so the
    closing stays the closing. Every other sentence stays in place."""
    parts = sentences(text)
    idx = [i for i, s in enumerate(parts) if _SIGNOFF.search(s)]
    groups: list[list[int]] = []
    for i in idx:
        if groups and i == groups[-1][-1] + 1:
            groups[-1].append(i)
        else:
            groups.append([i])
    if len(groups) < 2:
        return text
    drop = {i for g in groups[:-1] for i in g}
    return " ".join(s for i, s in enumerate(parts) if i not in drop)


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
