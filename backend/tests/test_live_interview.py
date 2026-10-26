"""The AI interviewer: the owner is interviewed on the dashboard BEFORE anything paid runs, then the video is made."""

from decimal import Decimal

import pytest
from sqlalchemy import select

from app.integrations import registry
from app.integrations.tts.base import TTSProvider
from app.models import Asset, InterviewSession, Job, Take, Workspace
from app.pipeline.queue import get_queue
from app.services import interview as iv
from tests.conftest import OPS, OWNER
from tests.helpers import BRIEF, api_path, record, upload_chunks

QUESTIONS = ["What problem are you solving?", "Why now?", "Who is it for?", "What is next?"]


async def state(client, pid):
    return (await client.get(f"/v1/projects/{pid}", headers=OWNER)).json()["state"]


async def live_project(client, questions=None, name="Tobi Oyinlola", segments=None):
    r = await client.post(
        "/v1/projects", json={**BRIEF, "founder_name": name, "founder_title": "CEO, Acme"}, headers=OWNER
    )
    pid = r.json()["id"]
    script = (await client.post(f"/v1/projects/{pid}/script/generate", headers=OWNER)).json()
    body = {k: script[k] for k in ("segments", "ticker_lines", "lower_thirds", "interview_questions")}
    body["segments"] = segments or [
        {"kind": "intro", "text": "Tonight we feature Acme, a farm marketplace."},
        {"kind": "body", "text": "Acme connects farmers to buyers."},
        {"kind": "outro", "text": "That was Acme. Back to you."},
    ]
    body["interview_questions"] = questions or QUESTIONS
    await client.put(f"/v1/projects/{pid}/script", json=body, headers=OWNER)
    r = await client.post(
        f"/v1/projects/{pid}/script/approve", json={"with_interview": True, "interview_mode": "live"}, headers=OWNER
    )
    assert r.status_code == 200, r.text
    await get_queue().drain()
    return pid


async def start(client, pid, name="Tobi Oyinlola", consent=True):
    return await client.post(
        f"/v1/projects/{pid}/interview/live",
        json={"founder_name": name, "founder_title": "CEO, Acme", "consent": consent},
        headers=OWNER,
    )


async def interviewed_project(client, answers=(0, 1, 2, 3), segments=None):
    pid = await live_project(client, segments=segments)
    token = (await start(client, pid)).json()["token"]
    for q in answers:
        await record(client, token, q)
    return pid, token


# ---------- approval: nothing paid runs before the interview ----------
async def test_live_approval_waits_for_the_interview_and_spends_nothing(client, workspace, maker):
    pid = await live_project(client)
    p = (await client.get(f"/v1/projects/{pid}", headers=OWNER)).json()
    assert p["state"] == "interviewing" and p["interview_mode"] == "live" and p["founder_name"] == "Tobi Oyinlola"
    async with maker() as s:
        assert (await s.execute(select(Job).where(Job.project_id == pid))).scalars().all() == []
        assert (await s.execute(select(Asset).where(Asset.project_id == pid))).scalars().all() == []
        assert (await s.get(Workspace, workspace)).credit_balance == Decimal("10")  # untouched


async def test_invite_mode_is_unchanged(client, workspace):
    r = await client.post("/v1/projects", json=BRIEF, headers=OWNER)
    pid = r.json()["id"]
    await client.post(f"/v1/projects/{pid}/script/generate", headers=OWNER)
    await client.post(f"/v1/projects/{pid}/script/approve", json={"with_interview": True}, headers=OWNER)
    await get_queue().drain()
    assert await state(client, pid) == "awaiting_founder"


async def test_the_system_shows_what_it_understood_from_the_announcement(client, workspace):
    brief = {"brief_text": "Acme Farms helps farmers sell produce online. We have 5,000 users.", "founder_name": "Tobi"}
    pid = (await client.post("/v1/projects", json=brief, headers=OWNER)).json()["id"]
    await client.post(f"/v1/projects/{pid}/script/generate", headers=OWNER)
    u = (await client.get(f"/v1/projects/{pid}/understanding", headers=OWNER)).json()
    assert u["company"] == "Acme Farms" and "sell produce" in u["announcement"] and u["founder_name"] == "Tobi"
    assert "We have 5,000 users" in u["key_facts"]


# ---------- starting the interview ----------
async def test_start_needs_consent_and_the_right_state_and_is_resumable(client, workspace, maker):
    pid = await live_project(client)
    assert (await start(client, pid, consent=False)).status_code == 422
    r = await start(client, pid)
    assert r.status_code == 200, r.text
    s = r.json()
    assert s["questions"] == QUESTIONS and s["max_total_s"] == 300 and s["max_answer_s"] == 75 and s["company"]
    assert (await start(client, pid)).json()["token"] == s["token"]  # reload: same room, same recorder credential
    async with maker() as db:
        sess = (await db.execute(select(InterviewSession))).scalar_one()
        assert sess.mode == "live" and sess.consent_at and sess.founder_name == "Tobi Oyinlola"
        assert s["token"] not in sess.token_hash  # only a hash is stored for lookup
    plain = await client.post("/v1/projects", json=BRIEF, headers=OWNER)
    assert (await start(client, plain.json()["id"])).status_code == 409


async def test_only_the_owner_can_open_the_room(client, workspace, maker):
    from app.models import User

    pid = await live_project(client)
    async with maker() as s:  # a user of a different workspace
        ws = Workspace(name="Other")
        s.add(ws)
        await s.flush()
        s.add(User(email="other@elsewhere.example.com", workspace_id=ws.id))
        await s.commit()
    other = {"Authorization": "Bearer dev:other@elsewhere.example.com"}
    body = {"founder_name": "x", "consent": True}
    assert (await client.post(f"/v1/projects/{pid}/interview/live", json=body, headers=other)).status_code == 404
    assert (await client.post(f"/v1/projects/{pid}/interview/live/skip", headers=other)).status_code == 404


# ---------- recording: camera required, 5 minute design ----------
async def test_live_recording_requires_the_camera(client, workspace):
    pid = await live_project(client)
    token = (await start(client, pid)).json()["token"]
    v = (await client.get(f"/v1/interview/{token}")).json()
    assert v["mode"] == "live" and v["can_record"] and v["max_chunks"] == iv.LIVE_MAX_CHUNKS
    assert all(q["clip_url"] is None for q in v["questions"])  # no anchor exists yet
    r = await client.post(
        f"/v1/interview/{token}/takes", json={"question_index": 0, "kind": "audio", "mime": "audio/webm"}
    )
    assert r.status_code == 422 and "camera" in r.json()["detail"].lower()
    r = await client.post(
        f"/v1/interview/{token}/takes", json={"question_index": 0, "kind": "video", "mime": "video/webm"}
    )
    assert r.status_code == 200


async def test_live_answers_are_capped_in_length(client, workspace):
    pid = await live_project(client)
    token = (await start(client, pid)).json()["token"]
    take = (
        await client.post(
            f"/v1/interview/{token}/takes", json={"question_index": 0, "kind": "video", "mime": "video/webm"}
        )
    ).json()["id"]
    r = await client.post(f"/v1/interview/{token}/takes/{take}/chunk-urls", json={"indexes": [iv.LIVE_MAX_CHUNKS]})
    assert r.status_code == 422
    await upload_chunks(client, token, take, [0, 1])
    r = await client.post(f"/v1/interview/{token}/takes/{take}/complete", json={"chunk_count": iv.LIVE_MAX_CHUNKS + 1})
    assert r.status_code == 422


def test_answer_windows_keep_the_whole_interview_under_five_minutes():
    # greeting + every question spoken + the answers + the closing must always fit
    for n in (1, 3, 4, 5):
        elapsed, total = 15.0, 15.0 + 14.0
        for left in range(n, 0, -1):
            w = iv.answer_window_s(elapsed, left)
            assert iv.LIVE_MIN_ANSWER_S <= w <= iv.LIVE_MAX_ANSWER_S
            elapsed += 9 + w
            total += 9 + w
        assert total <= iv.LIVE_MAX_TOTAL_S + 1, (n, total)
    assert iv.answer_window_s(0, 0) == 0


# ---------- the interviewer's voice ----------
async def test_voice_lines_greet_the_founder_by_name_and_fall_back_to_the_browser_voice(client, workspace):
    pid = await live_project(client)
    token = (await start(client, pid, name="Tobi Oyinlola")).json()["token"]
    r = await client.post(f"/v1/interview/{token}/voice")
    assert r.status_code == 200
    lines = {x["key"]: x for x in r.json()["lines"]}
    assert list(lines) == ["greeting", "q0", "q1", "q2", "q3", "thanks", "closing"]
    assert lines["greeting"]["text"].startswith("Hi Tobi, welcome.") and "four questions" in lines["greeting"]["text"]
    assert "Tobi" in lines["closing"]["text"] and lines["q1"]["text"] == "Why now?"
    assert all(x["audio_url"] is None for x in lines.values())  # the mock has no audio: the browser speaks


class FakeTTS(TTSProvider):
    def __init__(self):
        self.calls = []

    def estimate_cost(self, text):
        return 0.002

    async def synthesize(self, text):
        self.calls.append(text)
        return b"ID3-fake-mp3-" + text.encode()


async def test_voice_audio_is_generated_once_cached_and_billed_through_the_spend_guard(client, workspace, maker):
    tts = FakeTTS()
    registry.override(tts=tts)
    await client.put("/v1/admin/vendor-budgets", json={"vendor": "tts", "limit": "5"}, headers=OPS)
    pid = await live_project(client)
    token = (await start(client, pid)).json()["token"]
    first = (await client.post(f"/v1/interview/{token}/voice")).json()["lines"]
    assert all(x["audio_url"] for x in first) and len(tts.calls) == 7
    second = (await client.post(f"/v1/interview/{token}/voice")).json()["lines"]
    assert all(x["audio_url"] for x in second) and len(tts.calls) == 7  # cached by text
    audio = await client.get(api_path(first[0]["audio_url"]))
    assert audio.status_code == 200 and audio.content.startswith(b"ID3")
    async with maker() as s:
        from app.models import CreditTransaction

        rows = (await s.execute(select(CreditTransaction).where(CreditTransaction.vendor == "tts"))).scalars().all()
    assert rows and all(r.stage == "interview_voice" for r in rows)


async def test_a_missing_voice_budget_never_blocks_the_interview(client, workspace):
    registry.override(tts=FakeTTS())  # a real voice, but the operator set no "tts" budget: fail closed, quietly
    pid = await live_project(client)
    token = (await start(client, pid)).json()["token"]
    r = await client.post(f"/v1/interview/{token}/voice")
    assert r.status_code == 200 and all(x["audio_url"] is None for x in r.json()["lines"])


async def test_a_voice_vendor_error_never_blocks_the_interview(client, workspace):
    class Broken(FakeTTS):
        async def synthesize(self, text):
            raise RuntimeError("vendor down")

    registry.override(tts=Broken())
    await client.put("/v1/admin/vendor-budgets", json={"vendor": "tts", "limit": "5"}, headers=OPS)
    pid = await live_project(client)
    token = (await start(client, pid)).json()["token"]
    r = await client.post(f"/v1/interview/{token}/voice")
    assert r.status_code == 200 and all(x["audio_url"] is None for x in r.json()["lines"])


# ---------- snapshots ----------
async def test_a_snapshot_is_kept_with_its_answer(client, workspace, maker):
    pid = await live_project(client)
    token = (await start(client, pid)).json()["token"]
    take_id = await record(client, token, 0)
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
    slot = (await client.post(f"/v1/interview/{token}/photo", json={"content_type": "image/png"})).json()
    assert (await client.put(api_path(slot["upload_url"]), content=png)).status_code == 200
    r = await client.post(f"/v1/interview/{token}/photo/confirm", json={"key": slot["key"], "take_id": take_id})
    assert r.status_code == 200, r.text
    async with maker() as s:
        t = await s.get(Take, take_id)
        assert t.snapshot_key == slot["key"]
        assert (await s.execute(select(InterviewSession))).scalar_one().photo_key is None  # not the profile photo
    st = (await client.get(f"/v1/projects/{pid}/interview", headers=OWNER)).json()
    assert st["mode"] == "live" and st["takes"][0]["snapshot_url"]
    bad = await client.post(f"/v1/interview/{token}/photo/confirm", json={"key": slot["key"], "take_id": "nope"})
    assert bad.status_code == 404


# ---------- finishing, reviewing, proceeding ----------
async def test_submit_needs_every_answer_and_leaves_the_owner_to_proceed(client, workspace):
    pid, token = await interviewed_project(client, answers=(0, 1))
    r = await client.post(f"/v1/interview/{token}/submit")
    assert r.status_code == 422 and "Question 3 hasn't been answered" in r.json()["detail"]["message"]
    for q in (2, 3):
        await record(client, token, q)
    assert (await client.post(f"/v1/interview/{token}/submit")).status_code == 200
    assert await state(client, pid) == "interviewing"  # the owner reviews first
    st = (await client.get(f"/v1/projects/{pid}/interview", headers=OWNER)).json()
    assert st["submitted"] and len(st["takes"]) == 4 and st["plan"]["layout"] == "column"


async def test_proceed_needs_all_answers_then_makes_the_presenter_and_merges_automatically(client, workspace, maker):
    pid, token = await interviewed_project(client, answers=(0, 1))
    r = await client.post(f"/v1/projects/{pid}/interview/merge", headers=OWNER)
    assert r.status_code == 409 and "Answer every question" in r.json()["detail"]
    for q in (2, 3):
        await record(client, token, q)
    await client.post(f"/v1/interview/{token}/submit")
    r = await client.post(f"/v1/projects/{pid}/interview/merge", headers=OWNER)
    assert r.status_code == 200, r.text
    await get_queue().drain()  # anchor, question clips, then the merge, with no further clicks
    assert await state(client, pid) == "final_ready"
    req = registry.get_renderer().requests[-1]
    assert req.composition == "InterviewMerge" and req.props["layout"] == "column"
    kinds = [s["type"] for s in req.props["scenes"]]
    assert kinds == ["anchor"] + ["question", "answer"] * 4 + ["anchor"]
    answers = [s for s in req.props["scenes"] if s["type"] == "answer"]
    assert [a["questionNumber"] for a in answers] == [1, 2, 3, 4] and all(a["totalQuestions"] == 4 for a in answers)
    assert answers[1]["question"] == "Why now?" and answers[0]["founder"]["name"] == "Tobi Oyinlola"
    for a in answers:  # the founder's words, timed inside the answer so the column stays in sync
        assert a["cues"] and all(0 <= c["start"] < c["end"] <= a["seconds"] + 0.01 for c in a["cues"])
        assert a["cues"][0]["text"] == "mock transcript"
    async with maker() as s:  # the interview link stops working once the video is being made
        assert (await s.execute(select(InterviewSession))).scalar_one().revoked_at is not None


async def test_the_owners_words_are_screened_before_anything_paid_runs(client, workspace, maker):
    from app.integrations.transcription.base import Transcript

    class Pitchy:
        async def transcribe(self, url):
            return Transcript(
                "We offer guaranteed returns to every investor.", "1\n00:00:00,000 --> 00:00:02,000\nx\n", True
            )

    registry.override(transcription=Pitchy())
    pid, token = await interviewed_project(client)
    await client.post(f"/v1/interview/{token}/submit")
    r = await client.post(f"/v1/projects/{pid}/interview/merge", headers=OWNER)
    assert r.status_code == 409 and r.json()["detail"]["error"] == "in_review"
    assert await state(client, pid) == "interviewing"
    async with maker() as s:
        paid = (await s.execute(select(Job).where(Job.project_id == pid, Job.stage != "process_take"))).scalars().all()
        assert paid == []  # nothing paid has run
    case = (await client.get("/v1/admin/moderation", headers=OPS)).json()[0]
    await client.post(f"/v1/admin/moderation/{case['id']}/decision", json={"decision": "approve"}, headers=OPS)
    assert (await client.post(f"/v1/projects/{pid}/interview/merge", headers=OWNER)).status_code == 200


async def test_dropping_an_answer_drops_its_question_from_the_column_numbering(client, workspace):
    pid, token = await interviewed_project(client)
    await client.post(f"/v1/interview/{token}/submit")
    plan = {"layout": "column", "answers": [{"question_index": 1, "include": False}]}
    assert (await client.put(f"/v1/projects/{pid}/interview/plan", json=plan, headers=OWNER)).status_code == 200
    await client.post(f"/v1/projects/{pid}/interview/merge", headers=OWNER)
    await get_queue().drain()
    answers = [s for s in registry.get_renderer().requests[-1].props["scenes"] if s["type"] == "answer"]
    assert [a["question"] for a in answers] == [QUESTIONS[0], QUESTIONS[2], QUESTIONS[3]]
    assert [a["questionNumber"] for a in answers] == [1, 2, 3] and answers[0]["totalQuestions"] == 3


async def test_redoing_one_answer_after_the_interview(client, workspace):
    pid, token = await interviewed_project(client)
    await client.post(f"/v1/interview/{token}/submit")
    again = (await start(client, pid)).json()["token"]  # a finished session: a fresh room for the redo
    assert again != token
    await record(client, again, 2)
    assert (await client.post(f"/v1/interview/{again}/submit")).status_code == 200
    st = (await client.get(f"/v1/projects/{pid}/interview", headers=OWNER)).json()
    assert len(st["takes"]) == 4 and st["submitted"]
    assert (await client.get(f"/v1/interview/{token}")).status_code == 404  # the old room is closed


async def test_skipping_the_interview_makes_the_anchor_only_video(client, workspace):
    pid = await live_project(client)
    r = await client.post(f"/v1/projects/{pid}/interview/live/skip", headers=OWNER)
    assert r.status_code == 200 and r.json()["interview_enabled"] is False
    await get_queue().drain()
    assert await state(client, pid) == "final_ready"
    assert registry.get_renderer().requests[-1].composition == "NewsStudio"


async def test_live_endpoints_are_scoped_to_the_owner(client, workspace):
    pid = await live_project(client)
    nobody = {"Authorization": "Bearer dev:nobody@example.com"}
    assert (await client.post(f"/v1/projects/{pid}/interview/live/skip", headers=nobody)).status_code in (401, 403)


@pytest.mark.parametrize("state_name", ["draft", "script_ready"])
async def test_cannot_skip_when_not_interviewing(client, workspace, state_name):
    r = await client.post("/v1/projects", json=BRIEF, headers=OWNER)
    pid = r.json()["id"]
    if state_name == "script_ready":
        await client.post(f"/v1/projects/{pid}/script/generate", headers=OWNER)
    assert (await client.post(f"/v1/projects/{pid}/interview/live/skip", headers=OWNER)).status_code == 409


async def test_an_unfinished_recording_can_be_abandoned_so_it_never_blocks_submitting(client, workspace):
    pid = await live_project(client, questions=QUESTIONS[:1])
    token = (await start(client, pid)).json()["token"]
    r = await client.post(
        f"/v1/interview/{token}/takes", json={"question_index": 0, "kind": "video", "mime": "video/webm"}
    )
    take = r.json()["id"]
    await upload_chunks(client, token, take, [0])
    assert (await client.delete(f"/v1/interview/{token}/takes/{take}")).status_code == 200
    r = await client.post(f"/v1/interview/{token}/submit")
    assert r.status_code == 422 and "hasn't been answered" in r.json()["detail"]["message"]  # not "still processing"
    await record(client, token, 0)
    assert (await client.post(f"/v1/interview/{token}/submit")).status_code == 200
    done = await client.delete(f"/v1/interview/{token}/takes/{take}")  # a finished or unknown take is left alone
    assert done.status_code == 200


async def test_the_ai_interview_is_compulsory_when_required(client, workspace, monkeypatch):
    from app.config import get_settings

    monkeypatch.setattr(get_settings(), "require_interview", True)
    r = await client.post("/v1/projects", json={**BRIEF, "founder_name": "Ada Obi"}, headers=OWNER)
    pid = r.json()["id"]
    await client.post(f"/v1/projects/{pid}/script/generate", headers=OWNER)
    # asking for a presenter-only video, or for an invite-link interview, still gets the AI interview
    r = await client.post(f"/v1/projects/{pid}/script/approve", json={"with_interview": False}, headers=OWNER)
    assert r.status_code == 200, r.text
    out = r.json()
    assert out["interview_enabled"] is True and out["interview_mode"] == "live"
    assert out["state"] == "interviewing"
    # and it cannot be skipped
    skip = await client.post(f"/v1/projects/{pid}/interview/live/skip", headers=OWNER)
    assert skip.status_code == 403
    assert await state(client, pid) == "interviewing"
