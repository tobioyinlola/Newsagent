"""Guards for the Video Rulebook (app/video_rules/rulebook.py). These make the rules add-on only:
- no rule is ever deleted (retire it with replaced_by instead);
- a change to any rule needs VERSION + 1 and a CHANGELOG line, and shows up in the committed lock file;
- the renderer, the web app and docs/video-rules.md use exactly the rulebook's values;
- every active rule has at least one test that names it: covers("BIV-...") in Python, // covers: BIV-... in TypeScript.
"""

import json
import re
from pathlib import Path

from app.video_rules import rulebook as rb

ROOT = Path(__file__).resolve().parents[2]
LOCK = ROOT / "backend/app/video_rules/rules.lock.json"


def _now() -> dict:
    snap = {
        r.id: {"value": r.value, "status": r.status, "replaced_by": r.replaced_by, "title": r.title, "area": r.area}
        for r in rb.RULES
    }
    return json.loads(json.dumps(snap))


def test_ids_are_unique_well_formed_and_retired_rules_name_their_replacement():
    ids = [r.id for r in rb.RULES]
    assert len(ids) == len(set(ids))
    assert all(re.fullmatch(r"BIV-[A-Z]+-\d{3}", i) for i in ids), ids
    for r in rb.RULES:
        assert r.area in rb.AREA_TITLES
        if r.status == "retired":
            assert r.replaced_by in {x.id for x in rb.RULES}, f"{r.id} must name the rule that replaced it"


def test_no_rule_is_ever_deleted_and_every_change_is_versioned():
    lock = json.loads(LOCK.read_text())["versions"]
    every_id_ever = {rid for snap in lock.values() for rid in snap}
    missing = every_id_ever - {r.id for r in rb.RULES}
    assert not missing, f"rules deleted: {missing}. Retire them (status='retired', replaced_by=...) instead"
    latest = max(map(int, lock))
    assert latest == rb.VERSION, "run `uv run python ../scripts/export_video_rules.py` from backend/ and commit the result"
    assert lock[str(latest)] == _now(), (
        "the rulebook changed but its lock did not: bump VERSION, add a CHANGELOG line, then run "
        "`uv run python ../scripts/export_video_rules.py` from backend/"
    )
    assert len(rb.CHANGELOG) >= rb.VERSION, "one CHANGELOG line per rulebook version"


def test_the_renderer_the_web_app_and_the_docs_use_the_rulebook():
    want = {"version": rb.VERSION, "rules": {r.id: r.value for r in rb.active()}}
    for path in ("backend/renderer/src/videoRules.generated.json", "frontend/src/lib/videoRules.generated.json"):
        assert json.loads((ROOT / path).read_text()) == json.loads(json.dumps(want)), f"{path} is stale: regenerate it"
    doc = (ROOT / "docs/video-rules.md").read_text()
    assert f"rulebook version {rb.VERSION}" in doc and all(f"`{r.id}`" in doc for r in rb.RULES), "regenerate the docs"


_COVERS = re.compile(r"covers\(([^)]*)\)|covers:\s*([A-Z0-9 ,\-]+)")
TEST_FILES = [
    *(ROOT / "backend/tests").glob("test_*.py"),
    *(ROOT / "backend/renderer/src").rglob("*.test.ts"),
    *(ROOT / "frontend/src").rglob("*.test.ts"),
    *(ROOT / "frontend/src").rglob("*.test.tsx"),
    *(ROOT / "frontend/e2e").glob("*.spec.ts"),
    *(ROOT / "frontend/e2e-real").glob("*.spec.ts"),
]


def covered_ids() -> set[str]:
    found: set[str] = set()
    for f in TEST_FILES:
        for m in _COVERS.finditer(f.read_text()):
            found |= set(re.findall(r"BIV-[A-Z]+-\d{3}", m.group(0)))
    return found


def test_every_active_rule_is_covered_by_a_test():
    uncovered = sorted(r.id for r in rb.active() if r.id not in covered_ids())
    assert not uncovered, f"no test names these rules (add covers(...) to the test that checks them): {uncovered}"


def test_tests_only_name_rules_that_exist():
    unknown = covered_ids() - {r.id for r in rb.RULES}
    assert not unknown, f"tests name rules that are not in the rulebook: {sorted(unknown)}"
