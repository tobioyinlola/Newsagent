"""SRT generation and copy-ready social captions. Disclosure text is always included (hard rule 2)."""

DISCLOSURE = "Featured startup · AI-generated anchor"
HASHTAGS = {
    "linkedin": ["#startups", "#founders", "#innovation"],
    "instagram": ["#startup", "#founderstory", "#entrepreneur", "#innovation"],
    "x": ["#startups", "#buildinpublic"],
}


def _ts(seconds: float) -> str:
    ms = round(seconds * 1000)
    h, ms = divmod(ms, 3_600_000)
    m, ms = divmod(ms, 60_000)
    s, ms = divmod(ms, 1000)
    return f"{h:02}:{m:02}:{s:02},{ms:03}"


def build_srt(segments: list[dict], duration_s: float, max_words: int = 8) -> str:
    """Timing is proportional to word count across the anchor duration (no word-level timestamps yet)."""
    chunks: list[str] = []
    for seg in segments:
        words = seg["text"].split()
        chunks += [" ".join(words[i : i + max_words]) for i in range(0, len(words), max_words)]
    total = sum(len(c.split()) for c in chunks) or 1
    t, out = 0.0, []
    for i, c in enumerate(chunks, 1):
        end = t + duration_s * len(c.split()) / total
        out.append(f"{i}\n{_ts(t)} --> {_ts(end)}\n{c}\n")
        t = end
    return "\n".join(out)


def suggested_captions(company: str, hook: str, share_url: str | None = None) -> dict[str, str]:
    link = f"\n{share_url}" if share_url else ""
    return {platform: f"{hook}\n\n{DISCLOSURE}{link}\n\n{' '.join(tags)}" for platform, tags in HASHTAGS.items()} | {
        "company": company
    }
