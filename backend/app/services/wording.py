"""Correct a name or phrase across a finished video: the written story, the presenter's lines, the ticker and the lower thirds.

What it never touches: the founder's own recorded answers (their words are theirs) and the questions the presenter already asked.
It makes a new approved version of the script, so the earlier one stays in the history."""

from dataclasses import dataclass, field
from datetime import UTC, datetime
from typing import Any

from sqlalchemy.ext.asyncio import AsyncSession

from app.models import Project, ScriptVersion
from app.pipeline.steps import approved_script
from app.services.safety import find_banned


def pairs(find: str, replace: str) -> list[tuple[str, str]]:
    """The wording as written, in capitals (headline bars) and in lower case, longest first so a longer match is never split."""
    out: list[tuple[str, str]] = []
    for a, b in ((find, replace), (find.upper(), replace.upper()), (find.lower(), replace.lower())):
        if a and (a, b) not in out:
            out.append((a, b))
    return sorted(out, key=lambda p: -len(p[0]))


def swap(value: Any, wanted: list[tuple[str, str]]) -> tuple[Any, int]:
    """Replace inside any text, list or object. Returns the new value and how many times something was replaced."""
    if isinstance(value, str):
        count, text = 0, value
        for a, b in wanted:
            count += text.count(a)
            text = text.replace(a, b)
        return text, count
    if isinstance(value, list):
        items = [swap(v, wanted) for v in value]
        return [i[0] for i in items], sum(i[1] for i in items)
    if isinstance(value, dict):
        total, out = 0, {}
        for k, v in value.items():
            out[k], n = swap(v, wanted)
            total += n
        return out, total
    return value, 0


@dataclass
class Report:
    found: dict[str, int] = field(default_factory=dict)
    kept: dict[str, int] = field(default_factory=dict)  # places that are never changed
    applied: bool = False
    rerendering: bool = False
    version: int | None = None

    @property
    def total(self) -> int:
        return sum(self.found.values())


async def correct(session: AsyncSession, project: Project, find: str, replace: str, *, apply: bool) -> Report:
    """Find (and, when `apply`, change) the wording. `apply` makes a new approved script version; the caller decides about re-rendering."""
    find, replace = find.strip(), replace.strip()
    if not find or not replace or find == replace:
        raise ValueError("Give the wording to find and the wording to put in its place.")
    if find_banned(replace):
        raise ValueError("The new wording can't contain a real news network name.")
    prev = await approved_script(session, project.id)
    wanted = pairs(find, replace)
    report = Report()
    story, report.found["story"] = swap(prev.story or {}, wanted)
    segments, report.found["presenter_lines"] = swap(prev.segments, wanted)
    ticker, report.found["ticker"] = swap(prev.ticker_lines, wanted)
    thirds, report.found["lower_thirds"] = swap(prev.lower_thirds, wanted)
    title, report.found["name_card_role"] = swap(project.founder_title or "", wanted)
    _, report.kept["interview_questions"] = swap(prev.interview_questions, wanted)
    report.found = {k: v for k, v in report.found.items() if v}
    report.kept = {k: v for k, v in report.kept.items() if v}
    if not apply or report.total == 0:
        return report
    sv = ScriptVersion(
        project_id=project.id,
        version=prev.version + 1,
        segments=segments,
        ticker_lines=ticker,
        lower_thirds=thirds,
        interview_questions=prev.interview_questions,
        claim_flags=prev.claim_flags,
        story=story or None,
        approved=True,
        approved_by=prev.approved_by,
        approved_at=prev.approved_at or datetime.now(UTC),
    )
    session.add(sv)
    project.founder_title = title
    await session.flush()
    report.applied, report.version = True, sv.version
    return report
