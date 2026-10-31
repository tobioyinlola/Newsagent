"""Broadcast defaults repair missing editorial metadata without introducing render failures."""

import hashlib
import re

VERSION = 1
REPORTER_LOCATION = "Toronto, Canada"


def excerpt(text: str, words: int = 18) -> str:
    sentence = re.split(r"(?<=[.!?])\s+", " ".join(text.split()))[0].strip(' .!?"')
    parts = sentence.split()
    return " ".join(parts[:words]) + ("…" if len(parts) > words else "")


def answer_headline(text: str, founder: str) -> str:
    name = (founder.strip().split() or ["Founder"])[-1].upper()
    return f"{name}: {excerpt(text, 12) or 'Shares the story behind the business'}"[:110]


def bridge(text: str, index: int) -> str:
    detail = excerpt(text, 16)
    leads = [
        "You’ve highlighted “{detail}”. I’d like to explore what comes next.",
        "That adds context to the story, especially “{detail}”. Let’s look at another part of the business.",
        "The point about “{detail}” stands out. To bring this together, here’s my final question.",
        "Your explanation of “{detail}” helps frame the bigger picture. Let’s turn to the next point.",
    ]
    if not detail:
        return [
            "That gives us useful context. Let’s explore the next part of the story.",
            "I’d like to build on that and look at the business from another angle.",
            "To bring the discussion together, here’s my final question.",
            "Let’s turn to what comes next for the business.",
        ][index % 4]
    return leads[index % len(leads)].format(detail=detail)


def enrich(script, founder: str, answers: dict[int, str]) -> None:
    """Keep authored lines when usable; fill omissions from the actual answers, not the story headline."""
    if not answers:
        return
    data = dict(script.story or {})
    chyrons = dict(data.get("chyrons") or {})
    hooks = dict(data.get("answer_bridges") or {})
    used: set[str] = set()
    used_headlines: set[str] = set()
    fingerprints = dict(data.get("answer_fingerprints") or {})
    changed = False
    for index, (q, answer) in enumerate(answers.items()):
        digest = hashlib.sha256(answer.encode()).hexdigest()
        if str(q) in fingerprints and fingerprints[str(q)] != digest:
            chyrons.pop(str(q), None)
            hooks.pop(str(q), None)
            changed = True
        fingerprints[str(q)] = digest
        # The founder name and answer-specific summary are always present.
        authored = str(chyrons.get(str(q)) or "").strip()
        summary_text = authored.split(":", 1)[-1].strip()
        if (
            not authored
            or ":" not in authored
            or summary_text in used_headlines
            or summary_text.lower() == str(data.get("headline", "")).lower()
        ):
            chyrons[str(q)] = answer_headline(answer, founder)
        else:
            surname = (founder.strip().split() or ["Founder"])[-1].upper()
            chyrons[str(q)] = f"{surname}: {summary_text}"[:110]
        used_headlines.add(summary_text)
        line = str(hooks.get(str(q)) or "").strip()
        stem = " ".join(line.lower().split()[:4])
        if len(line.split()) < 8 or stem in used or re.fullmatch(r"(?:thank you|thanks)[.! ]*", line, re.I):
            line = bridge(answer, index)
            stem = " ".join(line.lower().split()[:4])
        hooks[str(q)] = line
        used.add(stem)
    data.update(
        chyrons=chyrons, answer_bridges=hooks, broadcast_rules_version=VERSION, answer_fingerprints=fingerprints
    )
    summary = str(data.get("startup_summary") or "").strip()
    if changed and data.get("generated_summary"):
        summary = ""
        script.segments = [segment for segment in script.segments if segment.get("kind") != "analysis"]
    if not summary:
        data["generated_summary"] = True
        parts = [excerpt(text, 20) for text in answers.values() if text.strip()]
        summary = (
            ("To recap, the founder describes the business this way: " + "; ".join(parts[:4]) + ".")
            if parts
            else (
                "To recap, "
                + str(data.get("dek") or data.get("headline") or "this is the story behind the business").rstrip(".")
                + "."
            )
        )
    data["startup_summary"] = summary
    if not any(s.get("kind") == "analysis" and s.get("text", "").strip() for s in script.segments):
        before_outro = [s for s in script.segments if s.get("kind") != "outro"]
        outro = [s for s in script.segments if s.get("kind") == "outro"]
        if not outro:
            from app.services.presenters import STANDARD_OUTRO

            outro = [{"kind": "outro", "text": STANDARD_OUTRO}]
        script.segments = [*before_outro, {"kind": "analysis", "text": summary}, *outro]
    script.story = data
