"""Founder-interview domain logic: tokens, consent, take quality messages, merge plan, caption timing."""

import hashlib
import re
import secrets
from datetime import UTC, datetime

CONSENT_VERSION = "2026-10-v1"


def consent_text(company: str) -> str:
    return (
        f"Your recording will be used only in the video about {company}. "
        "The video includes a visible 'Featured' label and says the anchor is AI-generated. "
        "Your answers will be transcribed to make captions, and the owner of this video can review, trim or drop "
        "any answer before it is published. Your original recording is kept privately and deleted 90 days after "
        "the video is finished unless the video owner chooses to keep it. You can record again as many times as you "
        "like before you submit."
    )


def new_token() -> str:
    return secrets.token_urlsafe(32)


def hash_token(token: str) -> str:
    return hashlib.sha256(token.encode()).hexdigest()


# Limits on a single take. Chunks are ~2 s each, so 80 chunks comfortably covers the 2 minute cap.
MAX_CHUNKS = 80
MAX_CHUNK_BYTES = 8 * 1024 * 1024
MAX_TAKE_BYTES = 150 * 1024 * 1024
MAX_ATTEMPTS_PER_QUESTION = 5
MAX_QUESTIONS = 5
ALLOWED_VIDEO_MIME = {"video/webm": "webm", "video/mp4": "mp4"}
ALLOWED_AUDIO_MIME = {"audio/webm": "webm", "audio/mp4": "m4a", "audio/ogg": "ogg"}

# Flags that mean "please record this again" vs. ones we only mention to the owner.
BLOCKING_FLAGS = {"no_speech", "too_short", "dark_video", "clipped_audio"}
FLAG_MESSAGES = {
    "no_speech": "We couldn't hear you clearly. Please check your microphone and try again.",
    "too_short": "That answer was very short. Please try again with a little more detail.",
    "dark_video": "The picture is too dark. Face a window or turn on a light and try again.",
    "clipped_audio": "The sound was too loud and distorted. Move back a little from the microphone and try again.",
    "owner_requested": "The video owner asked for another take of this answer.",
}


def flag_messages(flags: list[str]) -> list[str]:
    return [FLAG_MESSAGES[f] for f in flags if f in FLAG_MESSAGES]


def is_expired(expiry: datetime, now: datetime | None = None) -> bool:
    exp = expiry if expiry.tzinfo else expiry.replace(tzinfo=UTC)
    return exp < (now or datetime.now(UTC))


# ---------- merge plan (owner edits before the final render) ----------
class InvalidPlan(ValueError):
    pass


def validate_plan(plan: dict, question_count: int, durations: dict[int, float]) -> dict:
    """Normalise {layout, order, answers:[{question_index, include, trim_start_s, trim_end_s}]}."""
    layout = plan.get("layout", "pip")
    if layout not in {"pip", "split"}:
        raise InvalidPlan("Layout must be picture-in-picture or split screen.")
    order = plan.get("order") or list(range(question_count))
    if sorted(order) != list(range(question_count)):
        raise InvalidPlan("Order must list every question exactly once.")
    by_q = {a["question_index"]: a for a in plan.get("answers", [])}
    answers = []
    for q in range(question_count):
        a = by_q.get(q, {})
        start, end = float(a.get("trim_start_s", 0) or 0), float(a.get("trim_end_s", 0) or 0)
        if start < 0 or end < 0:
            raise InvalidPlan("Trim values can't be negative.")
        dur = durations.get(q)
        if dur is not None and a.get("include", True) and start + end > dur - 1.0:
            raise InvalidPlan(f"Answer {q + 1} would be shorter than 1 second after trimming.")
        answers.append(
            {"question_index": q, "include": bool(a.get("include", True)), "trim_start_s": start, "trim_end_s": end}
        )
    return {"layout": layout, "order": order, "answers": answers}


# ---------- captions ----------
_TS = re.compile(r"(\d+):(\d+):(\d+)[,.](\d+)")


def _to_s(m: re.Match[str]) -> float:
    h, mi, s, ms = m.groups()
    return int(h) * 3600 + int(mi) * 60 + int(s) + int(ms.ljust(3, "0")[:3]) / 1000


def _fmt(t: float) -> str:
    ms = round(max(0, t) * 1000)
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02}:{m:02}:{s:02},{ms:03}"


def parse_srt(srt: str) -> list[tuple[float, float, str]]:
    cues = []
    for block in re.split(r"\n\s*\n", srt.strip()):
        lines = [ln for ln in block.splitlines() if ln.strip()]
        for i, ln in enumerate(lines):
            if "-->" in ln:
                a, b = ln.split("-->")
                ma, mb = _TS.search(a), _TS.search(b)
                if ma and mb:
                    cues.append((_to_s(ma), _to_s(mb), " ".join(lines[i + 1 :])))
                break
    return cues


def merge_srt(parts: list[tuple[float, float, str]]) -> str:
    """parts: absolute (start, end, text) cues in timeline order -> SRT text."""
    return "\n".join(f"{i}\n{_fmt(a)} --> {_fmt(b)}\n{t}\n" for i, (a, b, t) in enumerate(parts, 1))


def shifted_cues(srt: str, offset: float, trim_start: float, window: float) -> list[tuple[float, float, str]]:
    """Cues of one answer placed on the final timeline, honouring the owner's trim window."""
    out = []
    for a, b, text in parse_srt(srt):
        a2, b2 = a - trim_start, b - trim_start
        if b2 <= 0 or a2 >= window:
            continue
        out.append((offset + max(0.0, a2), offset + min(window, b2), text))
    return out
