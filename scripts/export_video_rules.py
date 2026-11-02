"""Write everything generated from the Video Rulebook (backend/app/video_rules/rulebook.py):

- backend/renderer/src/videoRules.generated.json and frontend/src/lib/videoRules.generated.json: the values the renderer and the
  web app read, so all three apps use the same numbers;
- docs/video-rules.md: the readable list of every rule;
- backend/app/video_rules/rules.lock.json: one snapshot of the rules per rulebook VERSION. Older snapshots are never rewritten.

Refuses (exit 1) when a rule disappeared, or rules changed without VERSION + 1 and a CHANGELOG line. Run from backend/:
    uv run python ../scripts/export_video_rules.py
CI runs it and fails if any generated file is not committed.
"""

import json
import sys
from pathlib import Path

ROOT = Path(__file__).resolve().parents[1]
sys.path.insert(0, str(ROOT / "backend"))

from app.video_rules import rulebook as rb  # noqa: E402

LOCK = ROOT / "backend/app/video_rules/rules.lock.json"
TARGETS = [ROOT / "backend/renderer/src/videoRules.generated.json", ROOT / "frontend/src/lib/videoRules.generated.json"]
DOC = ROOT / "docs/video-rules.md"


def snapshot() -> dict:
    return {
        r.id: {"value": r.value, "status": r.status, "replaced_by": r.replaced_by, "title": r.title, "area": r.area}
        for r in rb.RULES
    }


def check_and_update_lock() -> dict:
    lock = json.loads(LOCK.read_text()) if LOCK.exists() else {"versions": {}}
    versions: dict = lock["versions"]
    now = json.loads(json.dumps(snapshot()))  # normalised the way it is stored (tuples become lists)
    problems = []
    if len(set(r.id for r in rb.RULES)) != len(rb.RULES):
        problems.append("two rules share an id")
    if len(rb.CHANGELOG) < rb.VERSION:
        problems.append(f"VERSION is {rb.VERSION} but CHANGELOG has {len(rb.CHANGELOG)} entries: add one line per version")
    known = {rid for snap in versions.values() for rid in snap}
    gone = sorted(known - set(now))
    if gone:
        problems.append(f"rules were deleted: {', '.join(gone)}. Retire them instead (status='retired', replaced_by=...)")
    for r in rb.RULES:
        if r.status == "retired" and not r.replaced_by:
            problems.append(f"{r.id} is retired without replaced_by")
    latest = max(map(int, versions), default=0)
    if latest > rb.VERSION:
        problems.append(f"the lock already has version {latest}; VERSION cannot go back to {rb.VERSION}")
    elif latest == rb.VERSION and versions[str(latest)] != now:
        changed = sorted(k for k in set(now) | set(versions[str(latest)]) if now.get(k) != versions[str(latest)].get(k))
        problems.append(
            f"rules changed ({', '.join(changed)}) but VERSION is still {rb.VERSION}: bump VERSION and add a CHANGELOG line"
        )
    if problems:
        sys.exit("Video Rulebook refused:\n- " + "\n- ".join(problems))
    versions[str(rb.VERSION)] = now
    return {"versions": {k: versions[k] for k in sorted(versions, key=int)}}


def doc() -> str:
    lines = [
        "# Video rules: business interview videos",
        "",
        f"Generated from `backend/app/video_rules/rulebook.py` (rulebook version {rb.VERSION}). Do not edit by hand: change the",
        "rulebook, then run `uv run python ../scripts/export_video_rules.py` from `backend/`. How rules may change is written at",
        "the top of the rulebook; in short, rules are added, never deleted, and every change is versioned and tested.",
        "",
    ]
    for area, title in rb.AREA_TITLES.items():
        rules = [r for r in rb.RULES if r.area == area and r.status == "active"]
        if not rules:
            continue
        lines += [f"## {title}", "", "| Id | Rule | Value |", "|---|---|---|"]
        for r in rules:
            val = r.value if not isinstance(r.value, str) or len(r.value) < 60 else f"“{r.value}”"
            text = f"**{r.title}.** {r.description}".replace("|", "\\|")
            lines.append(f"| `{r.id}` | {text} | {json.dumps(val, ensure_ascii=False) if not isinstance(val, str) else val} |")
        lines.append("")
    retired = [r for r in rb.RULES if r.status == "retired"]
    if retired:
        lines += ["## Retired rules (kept as history)", "", "| Id | Rule | Replaced by |", "|---|---|---|"]
        lines += [f"| `{r.id}` | **{r.title}.** {r.description} | `{r.replaced_by}` |" for r in retired]
        lines.append("")
    lines += ["## Changelog", ""] + [f"- {c}" for c in rb.CHANGELOG] + [""]
    return "\n".join(lines)


def main() -> None:
    lock = check_and_update_lock()
    LOCK.write_text(json.dumps(lock, indent=1, ensure_ascii=False) + "\n")
    values = {"version": rb.VERSION, "rules": {r.id: r.value for r in rb.RULES if r.status == "active"}}
    for t in TARGETS:
        t.write_text(json.dumps(values, indent=1, ensure_ascii=False) + "\n")
    DOC.write_text(doc())
    print(f"Video Rulebook v{rb.VERSION}: {len(rb.active())} active rules written")


if __name__ == "__main__":
    main()
