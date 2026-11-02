"""Golden videos: three fixed sample business interview videos are made end to end (mock vendors), and what the video IS (its
scene plan, the settings handed to the renderer, and every line the presenter speaks) is compared with the saved copy in
tests/golden/. Any change to how videos are put together shows up here as a readable diff, so nothing changes by accident.

When a change is intended (a new rule in the Video Rulebook), refresh the saved copies and review the diff in the PR:
    UPDATE_GOLDEN=1 uv run pytest tests/test_video_golden.py
"""

import difflib
import json
import os
import re
from pathlib import Path

import pytest

from app.integrations import registry
from app.integrations.avatar.mock import MockAvatarProvider
from app.models import Project
from app.pipeline.queue import get_queue
from app.services import conversation
from tests.conftest import OWNER
from tests.helpers import record
from tests.test_guided_flow import DETAILS, interviewed
from tests.test_live_interview import start, state

GOLDEN = Path(__file__).parent / "golden"
_ID = re.compile(r"\b[0-9a-f]{32}\b")
_URL = re.compile(r"https?://[^\s\"']+")
_LABEL = re.compile(r"^[A-Z]{3} \d{1,2}, \d{4} · .*$")  # the published date and time stamp


def _normal(x):
    """Ids, signed links and today's date differ on every run; everything else must match exactly."""
    if isinstance(x, dict):
        return {k: _normal(v) for k, v in sorted(x.items())}
    if isinstance(x, list):
        return [_normal(v) for v in x]
    if isinstance(x, float):
        return round(x, 3)
    if isinstance(x, str):
        x = _URL.sub(lambda m: "<url:" + _ID.sub("<id>", m.group(0).split("?")[0].split("/v1/dev-storage/")[-1]) + ">", x)
        x = _ID.sub("<id>", x)
        return "<published-label>" if _LABEL.match(x) else x
    return x


class _Spy(MockAvatarProvider):
    def __init__(self):
        super().__init__()
        self.lines: list[str] = []

    async def generate(self, req):
        self.lines.append(req.script_text)
        return await super().generate(req)


async def _interviewed_with_website(client) -> str:
    details = {**DETAILS, "website_url": "https://www.acmefarms.com/"}
    pid = (await client.post("/v1/projects", json=details, headers=OWNER)).json()["id"]
    assert (await client.post(f"/v1/projects/{pid}/guided/start", headers=OWNER)).status_code == 200
    token = (await start(client, pid)).json()["token"]
    for q in range(4):
        await record(client, token, q)
    return pid


async def _make(client, maker, *, plan: dict | None = None, website: bool = False) -> dict:
    spy = _Spy()
    registry.override(avatar=spy)
    pid = await (_interviewed_with_website(client) if website else interviewed(client))
    if plan is not None:
        r = await client.put(f"/v1/projects/{pid}/interview/plan", json=plan, headers=OWNER)
        assert r.status_code == 200, r.text
    assert (await client.post(f"/v1/projects/{pid}/interview/merge", headers=OWNER)).status_code == 200
    script = (await client.get(f"/v1/projects/{pid}/script", headers=OWNER)).json()
    body = {k: script[k] for k in ("segments", "ticker_lines", "lower_thirds", "interview_questions")}
    body["confirmed_claims"] = [c["text"] for c in script["claim_flags"]]
    assert (await client.put(f"/v1/projects/{pid}/script", json=body, headers=OWNER)).status_code == 200
    assert (await client.post(f"/v1/projects/{pid}/script/approve", json={}, headers=OWNER)).status_code == 200
    await get_queue().drain()
    assert await state(client, pid) == "final_ready"
    async with maker() as db:
        plan_saved = (await db.get(Project, pid)).scene_plan
    props = registry.get_renderer().requests[-1].props
    return _normal({"presenter_lines": sorted(spy.lines), "scene_plan": plan_saved, "render_props": props})


def _compare(name: str, got: dict) -> None:
    path = GOLDEN / f"{name}.json"
    text = json.dumps(got, indent=1, ensure_ascii=False, sort_keys=True) + "\n"
    if os.environ.get("UPDATE_GOLDEN") == "1" or not path.exists():
        GOLDEN.mkdir(exist_ok=True)
        path.write_text(text)
        return
    want = path.read_text()
    if text != want:
        diff = "".join(difflib.unified_diff(want.splitlines(True), text.splitlines(True), f"saved {name}", "now", n=2))
        pytest.fail(
            f"The {name} golden video changed. If intended, add or change a rule in the Video Rulebook, then refresh with "
            f"UPDATE_GOLDEN=1 and review this diff in the PR:\n{diff[:6000]}"
        )


@pytest.fixture(autouse=True)
def _fixed_choices(monkeypatch):
    # the welcome and hand-over lines are chosen from the project id, which is random in tests: fix the choice
    monkeypatch.setattr(conversation, "_seed", lambda _pid: 0)


async def test_golden_guided_video_with_four_answers(client, workspace, maker):
    # covers("BIV-SCN-001", "BIV-SCN-002", "BIV-SCN-004", "BIV-SCN-005", "BIV-SCR-005", "BIV-SCR-006", "BIV-SCR-007",
    #        "BIV-GFX-002", "BIV-GFX-005", "BIV-SCN-009", "BIV-SCR-003")
    _compare("biv_guided_four_answers", await _make(client, maker))


async def test_golden_guided_video_with_an_answer_left_out(client, workspace, maker):
    # covers("BIV-SCN-001", "BIV-SCN-002")
    plan = {
        "layout": "full",
        "order": [0, 1, 2, 3],
        "answers": [{"question_index": q, "include": q != 2} for q in range(4)],
    }
    _compare("biv_guided_answer_left_out", await _make(client, maker, plan=plan))


async def test_golden_guided_video_in_the_column_layout(client, workspace, maker):
    # covers("BIV-SCN-004")
    plan = {"layout": "column", "order": [0, 1, 2, 3], "answers": [{"question_index": q} for q in range(4)]}
    _compare("biv_guided_column_layout", await _make(client, maker, plan=plan))


async def test_golden_guided_video_with_a_website(client, workspace, maker):
    # covers("BIV-SCN-010", "BIV-SCR-011", "BIV-SCR-012", "BIV-SCR-013", "BIV-SCR-014", "BIV-GFX-011")
    _compare("biv_guided_with_website", await _make(client, maker, website=True))
