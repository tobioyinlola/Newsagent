import asyncio
from datetime import UTC, datetime, timedelta
from decimal import Decimal

import pytest
from sqlalchemy import select

from app import jobs
from app.integrations import registry
from app.integrations.malware.mock import EICAR
from app.models import Asset, InterviewSession, Project, Take, Workspace
from app.pipeline.queue import get_queue
from app.services import crypto
from app.services import interview as iv
from tests.conftest import OPS, OWNER
from tests.helpers import api_path, invite, make_awaiting_founder, record, upload_chunks


async def state(client, pid):
    return (await client.get(f"/v1/projects/{pid}", headers=OWNER)).json()["state"]


# ---------- pipeline up to the founder ----------
async def test_interview_pipeline_reaches_awaiting_founder_with_clips(client, workspace, maker):
    pid = await make_awaiting_founder(client)
    assert await state(client, pid) == "awaiting_founder"
    async with maker() as s:
        assets = {(a.type, a.format) for a in (await s.execute(select(Asset).where(Asset.project_id == pid))).scalars()}
        costs = (await client.get(f"/v1/projects/{pid}/costs", headers=OWNER)).json()
    assert {("anchor", "main"), ("anchor_outro", "outro"), ("question_clip", "q0"), ("question_clip", "q1")} <= assets
    assert {line["stage"] for line in costs["lines"]} == {"anchor_render", "question_clips"}
    assert Decimal(costs["total"]) == sum(Decimal(line["cost"]) for line in costs["lines"]) > 0
    assert "Your founder interview is ready to send" in {m["subject"] for m in registry.get_email().sent}


async def test_clips_are_not_regenerated_or_recharged_on_rerun(client, workspace, maker):
    from app.pipeline.runner import run_step

    pid = await make_awaiting_founder(client)
    async with maker() as s:
        before = (await s.get(Workspace, workspace)).credit_balance
    await run_step("question_clips", {"project_id": pid})  # re-delivery
    async with maker() as s:
        assert (await s.get(Workspace, workspace)).credit_balance == before


async def test_interview_questions_validated_at_approval(client, workspace):
    r = await client.post("/v1/projects", json={"brief_text": "Acme sells farm produce online."}, headers=OWNER)
    pid = r.json()["id"]
    s = (await client.post(f"/v1/projects/{pid}/script/generate", headers=OWNER)).json()
    body = {k: s[k] for k in ("segments", "ticker_lines", "lower_thirds")}
    body["segments"] = [{"kind": "intro", "text": "Tonight we feature Acme."}]
    body["interview_questions"] = []
    await client.put(f"/v1/projects/{pid}/script", json=body, headers=OWNER)
    r = await client.post(f"/v1/projects/{pid}/script/approve", json={"with_interview": True}, headers=OWNER)
    assert r.status_code == 422 and "1 to 5" in r.json()["detail"]["message"]
    body["interview_questions"] = ["As seen on CNN, what is your story?"]
    await client.put(f"/v1/projects/{pid}/script", json=body, headers=OWNER)
    assert (
        await client.post(f"/v1/projects/{pid}/script/approve", json={"with_interview": True}, headers=OWNER)
    ).status_code == 422


# ---------- magic link ----------
async def test_invite_creates_hashed_link_and_emails_plain_text(client, workspace, maker):
    pid = await make_awaiting_founder(client)
    token = await invite(client, pid)
    async with maker() as s:
        sess = (await s.execute(select(InterviewSession))).scalar_one()
    assert token not in sess.token_hash and len(sess.token_hash) == 64 and sess.token_hash == iv.hash_token(token)
    assert crypto.decrypt(sess.token_enc) == token and token not in (sess.token_enc or "")
    assert (sess.expiry.replace(tzinfo=UTC) - datetime.now(UTC)).days in (13, 14)
    mail = [m for m in registry.get_email().sent if m["to"] == "founder@startup.example.com"]
    assert len(mail) == 1 and f"/i/{token}" in mail[0]["text"] and "AI-generated" in mail[0]["text"]


async def test_invite_only_when_awaiting_founder(client, workspace):
    r = await client.post("/v1/projects", json={"brief_text": "x" * 30}, headers=OWNER)
    pid = r.json()["id"]
    r = await client.post(f"/v1/projects/{pid}/interview", json={"founder_name": "A"}, headers=OWNER)
    assert r.status_code == 409


async def test_new_link_replaces_old_and_revoke_works(client, workspace):
    pid = await make_awaiting_founder(client)
    t1 = await invite(client, pid)
    t2 = await invite(client, pid)
    assert (await client.get(f"/v1/interview/{t1}")).status_code == 404
    assert (await client.get(f"/v1/interview/{t2}")).status_code == 200
    await client.delete(f"/v1/projects/{pid}/interview", headers=OWNER)
    assert (await client.get(f"/v1/interview/{t2}")).status_code == 404


async def test_bad_expired_and_foreign_tokens_look_identical(client, workspace, maker):
    pid = await make_awaiting_founder(client)
    token = await invite(client, pid)
    bad = await client.get("/v1/interview/not-a-token")
    async with maker() as s:
        (await s.execute(select(InterviewSession))).scalar_one().expiry = datetime.now(UTC) - timedelta(minutes=1)
        await s.commit()
    expired = await client.get(f"/v1/interview/{token}")
    assert bad.status_code == expired.status_code == 404 and bad.json() == expired.json()


async def test_token_scoped_to_its_own_project(client, workspace):
    p1, p2 = await make_awaiting_founder(client), await make_awaiting_founder(client)
    t1, t2 = await invite(client, p1), await invite(client, p2)
    await client.post(f"/v1/interview/{t1}/consent")
    take = (
        await client.post(
            f"/v1/interview/{t1}/takes", json={"question_index": 0, "kind": "video", "mime": "video/webm"}
        )
    ).json()["id"]
    # the other founder's token cannot touch it
    assert (await client.get(f"/v1/interview/{t2}/takes/{take}")).status_code == 404
    assert (await client.post(f"/v1/interview/{t2}/takes/{take}/chunk-urls", json={"indexes": [0]})).status_code == 404


async def test_guest_view_has_questions_clips_consent_and_no_internals(client, workspace):
    pid = await make_awaiting_founder(client)
    token = await invite(client, pid)
    v = (await client.get(f"/v1/interview/{token}")).json()
    assert v["founder_name"] == "Ada Obi" and v["can_record"] and not v["consented"]
    assert len(v["questions"]) == 2 and all(q["clip_url"] for q in v["questions"])
    assert (
        "only in the video" in v["consent_text"]
        and "90 days" in v["consent_text"]
        and "AI-generated" in v["consent_text"]
    )
    raw = str({k: val for k, val in v.items() if k != "questions"}) + str([q["text"] for q in v["questions"]])
    assert pid not in raw and "workspace" not in raw.lower() and "credit" not in raw.lower()


# ---------- recording, chunks, resume ----------
async def test_must_consent_before_recording(client, workspace):
    pid = await make_awaiting_founder(client)
    token = await invite(client, pid)
    r = await client.post(
        f"/v1/interview/{token}/takes", json={"question_index": 0, "kind": "video", "mime": "video/webm"}
    )
    assert r.status_code == 409 and "how your recording will be used" in r.json()["detail"]


async def test_resume_after_dropped_connection(client, workspace):
    pid = await make_awaiting_founder(client)
    token = await invite(client, pid)
    await client.post(f"/v1/interview/{token}/consent")
    take = (
        await client.post(
            f"/v1/interview/{token}/takes", json={"question_index": 0, "kind": "video", "mime": "video/mp4"}
        )
    ).json()
    await upload_chunks(client, token, take["id"], [0, 1])
    # the connection drops: chunk 2's PUT went through but its confirm was lost; chunk 3 never left the device
    url = (await client.post(f"/v1/interview/{token}/takes/{take['id']}/chunk-urls", json={"indexes": [2]})).json()[
        "urls"
    ]["2"]
    await client.put(api_path(url), content=b"x" * 500)
    # on reconnect the page asks the server what it has, then sends only what is missing
    status = (await client.get(f"/v1/interview/{token}/takes/{take['id']}")).json()
    assert status["chunks_received"] == [0, 1]
    early = await client.post(f"/v1/interview/{token}/takes/{take['id']}/complete", json={"chunk_count": 4})
    assert early.status_code == 409 and early.json()["detail"]["missing"] == [2, 3]
    await client.post(f"/v1/interview/{token}/takes/{take['id']}/chunks/2/confirm")
    await upload_chunks(client, token, take["id"], [3])
    done = await client.post(f"/v1/interview/{token}/takes/{take['id']}/complete", json={"chunk_count": 4})
    assert done.status_code == 200 and done.json()["status"] == "uploaded"
    again = await client.post(f"/v1/interview/{token}/takes/{take['id']}/complete", json={"chunk_count": 4})
    assert again.status_code == 200  # a retried request after a lost response is harmless
    await get_queue().drain()
    assert (await client.get(f"/v1/interview/{token}/takes/{take['id']}")).json()["status"] == "ready"


async def test_processing_joins_chunks_in_order_and_stores_results(client, workspace, maker):
    pid = await make_awaiting_founder(client)
    token = await invite(client, pid)
    tid = await record(client, token, 0, chunks=3)
    renderer = registry.get_renderer()
    assert len(renderer.processed) == 1
    urls = renderer.processed[0].chunk_urls
    assert [u.rsplit("/", 1)[1] for u in urls] == ["00000", "00001", "00002"] and renderer.processed[0].ext == "webm"
    async with maker() as s:
        t = await s.get(Take, tid)
    assert t.status == "ready" and t.transcript and t.processed_video_key and float(t.duration_s) == 4.0


@pytest.mark.parametrize(
    "body,status",
    [
        ({"question_index": 0, "kind": "video", "mime": "application/x-msdownload"}, 415),
        ({"question_index": 9, "kind": "video", "mime": "video/webm"}, 422),
        ({"question_index": 0, "kind": "video", "mime": "audio/webm"}, 415),
    ],
)
async def test_start_take_validation(client, workspace, body, status):
    pid = await make_awaiting_founder(client)
    token = await invite(client, pid)
    await client.post(f"/v1/interview/{token}/consent")
    assert (await client.post(f"/v1/interview/{token}/takes", json=body)).status_code == status


async def test_chunk_limits(client, workspace):
    pid = await make_awaiting_founder(client)
    token = await invite(client, pid)
    await client.post(f"/v1/interview/{token}/consent")
    tid = (
        await client.post(
            f"/v1/interview/{token}/takes", json={"question_index": 0, "kind": "video", "mime": "video/webm"}
        )
    ).json()["id"]
    assert (
        await client.post(f"/v1/interview/{token}/takes/{tid}/chunk-urls", json={"indexes": [iv.MAX_CHUNKS]})
    ).status_code == 422
    assert (
        await client.post(f"/v1/interview/{token}/takes/{tid}/chunks/0/confirm")
    ).status_code == 409  # never uploaded
    url = (await client.post(f"/v1/interview/{token}/takes/{tid}/chunk-urls", json={"indexes": [0]})).json()["urls"][
        "0"
    ]
    await client.put(api_path(url), content=b"x" * (iv.MAX_CHUNK_BYTES + 1))
    assert (await client.post(f"/v1/interview/{token}/takes/{tid}/chunks/0/confirm")).status_code == 422
    assert (await client.get(f"/v1/interview/{token}/takes/{tid}")).json()["chunks_received"] == []


async def test_recording_again_has_no_per_question_attempt_cap(client, workspace):
    pid = await make_awaiting_founder(client)
    token = await invite(client, pid)
    await client.post(f"/v1/interview/{token}/consent")
    body = {"question_index": 0, "kind": "video", "mime": "video/webm"}
    for _ in range(12):
        assert (await client.post(f"/v1/interview/{token}/takes", json=body)).status_code == 200
    view = (await client.get(f"/v1/interview/{token}")).json()
    assert view["questions"][0]["attempts_left"] is None


async def test_retake_supersedes_previous(client, workspace, maker):
    pid = await make_awaiting_founder(client)
    token = await invite(client, pid)
    first = await record(client, token, 0)
    second = await record(client, token, 0)
    async with maker() as s:
        assert (await s.get(Take, first)).status == "superseded" and (await s.get(Take, second)).status == "ready"
    v = (await client.get(f"/v1/interview/{token}")).json()
    assert v["questions"][0]["take"]["id"] == second and v["questions"][0]["attempts_left"] is None


# ---------- quality flags ----------
async def test_bad_take_is_flagged_with_plain_message(client, workspace):
    pid = await make_awaiting_founder(client)
    token = await invite(client, pid)
    registry.get_renderer().process_flags = ["dark_video", "no_speech"]
    tid = await record(client, token, 0)
    t = (await client.get(f"/v1/interview/{token}")).json()["questions"][0]["take"]
    assert t["id"] == tid and t["status"] == "needs_retake"
    assert any("too dark" in m for m in t["messages"]) and any("couldn't hear" in m for m in t["messages"])
    registry.get_renderer().process_flags = []
    await record(client, token, 0)
    assert (await client.get(f"/v1/interview/{token}")).json()["questions"][0]["take"]["status"] == "ready"


async def test_silent_transcript_adds_no_speech_flag(client, workspace):
    from app.integrations.transcription.base import Transcript

    class Silent:
        async def transcribe(self, url):
            return Transcript("", "", False)

    registry.override(transcription=Silent())
    pid = await make_awaiting_founder(client)
    token = await invite(client, pid)
    await record(client, token, 0)
    assert (await client.get(f"/v1/interview/{token}")).json()["questions"][0]["take"]["flags"] == ["no_speech"]


# ---------- submit ----------
async def test_submit_requires_every_answer_then_notifies_owner(client, workspace, maker):
    pid = await make_awaiting_founder(client)
    token = await invite(client, pid)
    await record(client, token, 0)
    r = await client.post(f"/v1/interview/{token}/submit")
    assert r.status_code == 422 and "Question 2" in r.json()["detail"]["message"]
    await record(client, token, 1)
    assert (await client.post(f"/v1/interview/{token}/submit")).status_code == 200
    assert await state(client, pid) == "processing_founder"
    assert "Your founder has submitted their answers" in {m["subject"] for m in registry.get_email().sent}
    async with maker() as s:
        assert (await s.execute(select(InterviewSession))).scalar_one().token_enc is None  # no stored link after submit
    v = (await client.get(f"/v1/interview/{token}")).json()
    assert v["submitted"] and not v["can_record"]
    assert (
        await client.post(
            f"/v1/interview/{token}/takes", json={"question_index": 0, "kind": "video", "mime": "video/webm"}
        )
    ).status_code == 404


async def test_audio_only_needs_photo_and_scans_it(client, workspace):
    pid = await make_awaiting_founder(client, questions=["What problem do you solve?"])
    token = await invite(client, pid)
    await record(client, token, 0, kind="audio", mime="audio/webm")
    r = await client.post(f"/v1/interview/{token}/submit")
    assert r.status_code == 422 and "photo" in r.json()["detail"]["message"]
    png = b"\x89PNG\r\n\x1a\n" + b"\x00" * 64
    slot = (await client.post(f"/v1/interview/{token}/photo", json={"content_type": "image/png"})).json()
    await client.put(api_path(slot["upload_url"]), content=png + EICAR)
    assert (await client.post(f"/v1/interview/{token}/photo/confirm", json={"key": slot["key"]})).status_code == 422
    slot = (await client.post(f"/v1/interview/{token}/photo", json={"content_type": "image/png"})).json()
    await client.put(api_path(slot["upload_url"]), content=png)
    assert (await client.post(f"/v1/interview/{token}/photo/confirm", json={"key": slot["key"]})).status_code == 200
    assert (await client.post(f"/v1/interview/{token}/submit")).status_code == 200
    assert (
        await client.post(f"/v1/interview/{token}/photo/confirm", json={"key": "projects/other/takes/photo-x.png"})
    ).status_code in (404, 422)


# ---------- owner review, plan, merge ----------
async def submitted_project(client, answers=(0, 1)):
    pid = await make_awaiting_founder(client)
    token = await invite(client, pid)
    for q in answers:
        await record(client, token, q)
    await client.post(f"/v1/interview/{token}/submit")
    return pid, token


async def test_owner_sees_answers_and_default_plan(client, workspace):
    pid, _ = await submitted_project(client)
    st = (await client.get(f"/v1/projects/{pid}/interview", headers=OWNER)).json()
    assert st["submitted"] and len(st["takes"]) == 2 and st["plan"]["layout"] == "pip"
    assert all(t["video_url"] and t["transcript"] and t["status"] == "ready" for t in st["takes"])


async def test_merge_builds_scene_timeline_and_reaches_final(client, workspace):
    pid, _ = await submitted_project(client)
    plan = {
        "layout": "split",
        "order": [1, 0],
        "answers": [{"question_index": 0, "trim_start_s": 0.5, "trim_end_s": 0.5}, {"question_index": 1}],
    }
    assert (await client.put(f"/v1/projects/{pid}/interview/plan", json=plan, headers=OWNER)).status_code == 200
    r = await client.post(f"/v1/projects/{pid}/interview/merge", headers=OWNER)
    assert r.status_code == 200, r.text
    await get_queue().drain()
    assert await state(client, pid) == "final_ready"
    req = registry.get_renderer().requests[-1]
    kinds = [s["type"] for s in req.props["scenes"]]
    assert req.composition == "InterviewMerge" and req.props["layout"] == "split"
    assert kinds == ["anchor", "question", "answer", "question", "answer", "anchor", "anchor"]
    answers = [s for s in req.props["scenes"] if s["type"] == "answer"]
    assert [round(a["seconds"], 1) for a in answers] == [4.0, 3.0]  # question 1 untrimmed first, then 0 trimmed by 1s
    assert answers[1]["startFromSeconds"] == 0.5 and answers[0]["founder"] == {
        "name": "Ada Obi",
        "title": "CEO, Acme",
        "location": "",
    }
    assert req.props["totalSeconds"] == pytest.approx(sum(s["seconds"] for s in req.props["scenes"]))
    assert req.props["disclosures"] == {"tag": "Featured", "anchor": "AI-generated anchor"}
    d = (await client.get(f"/v1/projects/{pid}/downloads", headers=OWNER)).json()
    assert {i["type"] for i in d["items"]} >= {"render", "thumbnail", "caption"}


async def test_merge_captions_include_founder_words_at_the_right_time(client, workspace, maker):
    pid, _ = await submitted_project(client, answers=(0, 1))
    await client.post(f"/v1/projects/{pid}/interview/merge", headers=OWNER)
    await get_queue().drain()
    async with maker() as s:
        key = (
            (await s.execute(select(Asset).where(Asset.project_id == pid, Asset.type == "caption")))
            .scalar_one()
            .storage_key
        )
    srt = (await registry.get_storage().get(key, 1_000_000)).decode()
    cues = iv.parse_srt(srt)
    spoken = " ".join(text for _, _, text in cues)
    assert "mock transcript" in spoken and "What problem are you solving?" in spoken
    assert cues == sorted(cues) and all(b > a for a, b, _ in cues)


async def test_dropping_an_answer_removes_its_question_too(client, workspace):
    pid, _ = await submitted_project(client)
    plan = {"layout": "pip", "answers": [{"question_index": 0, "include": False}, {"question_index": 1}]}
    await client.put(f"/v1/projects/{pid}/interview/plan", json=plan, headers=OWNER)
    await client.post(f"/v1/projects/{pid}/interview/merge", headers=OWNER)
    await get_queue().drain()
    kinds = [s["type"] for s in registry.get_renderer().requests[-1].props["scenes"]]
    assert kinds == ["anchor", "question", "answer", "anchor", "anchor"]


@pytest.mark.parametrize(
    "plan,msg",
    [
        ({"layout": "carousel"}, "Layout"),
        ({"order": [0, 0]}, "Order"),
        ({"answers": [{"question_index": 0, "trim_start_s": -1}]}, "negative"),
        ({"answers": [{"question_index": 0, "trim_start_s": 2.5, "trim_end_s": 1}]}, "shorter than 1 second"),
    ],
)
async def test_plan_validation(client, workspace, plan, msg):
    pid, _ = await submitted_project(client)
    r = await client.put(f"/v1/projects/{pid}/interview/plan", json=plan, headers=OWNER)
    assert r.status_code == 422 and msg in r.json()["detail"]["message"]


async def test_skip_interview_makes_anchor_only_cut(client, workspace):
    pid = await make_awaiting_founder(client)
    r = await client.post(f"/v1/projects/{pid}/interview/merge", headers=OWNER)  # founder never answered
    assert r.status_code == 200
    await get_queue().drain()
    assert await state(client, pid) == "final_ready"
    assert [s["type"] for s in registry.get_renderer().requests[-1].props["scenes"]] == ["anchor", "anchor"]


async def test_merge_blocked_while_answers_processing(client, workspace, maker):
    pid, _ = await submitted_project(client)
    async with maker() as s:
        t = (await s.execute(select(Take).where(Take.project_id == pid, Take.status == "ready"))).scalars().first()
        t.status = "processing"
        await s.commit()
    assert (await client.post(f"/v1/projects/{pid}/interview/merge", headers=OWNER)).status_code == 409


async def test_owner_retake_reopens_link_and_emails_founder(client, workspace):
    pid, token = await submitted_project(client)
    registry.get_email().sent.clear()
    r = await client.post(
        f"/v1/projects/{pid}/interview/retake", json={"question_index": 1, "note": "Louder please"}, headers=OWNER
    )
    assert r.status_code == 200 and r.json()["emailed"]
    assert await state(client, pid) == "awaiting_founder"
    mail = [m for m in registry.get_email().sent if "re-record" in m["subject"]]
    assert len(mail) == 1 and "Louder please" in mail[0]["text"]
    new_token = mail[0]["text"].split("/i/")[1].split()[0]
    v = (await client.get(f"/v1/interview/{new_token}")).json()
    assert v["can_record"] and not v["submitted"] and v["questions"][1]["take"]["status"] == "needs_retake"
    assert "owner asked" in " ".join(v["questions"][1]["take"]["messages"])


async def test_merge_revokes_founder_link(client, workspace):
    pid, token = await submitted_project(client)
    await client.post(f"/v1/projects/{pid}/interview/merge", headers=OWNER)
    await get_queue().drain()
    assert (await client.get(f"/v1/interview/{token}")).status_code == 404


# ---------- spend & failures ----------
async def test_transcription_budget_exhausted_fails_take_not_project(client, workspace, maker):
    from app.models import VendorBudget

    pid = await make_awaiting_founder(client)
    token = await invite(client, pid)
    async with maker() as s:
        vb = (await s.execute(select(VendorBudget).where(VendorBudget.vendor == "transcription"))).scalar_one()
        vb.limit = Decimal("0")
        before = (await s.get(Workspace, workspace)).credit_balance
        await s.commit()
    registry.get_email().sent.clear()
    tid = await record(client, token, 0)
    async with maker() as s:
        t = await s.get(Take, tid)
        assert t.status == "failed" and "budget" in t.error.lower()
        assert (await s.get(Workspace, workspace)).credit_balance == before  # nothing charged
        assert (await s.get(Project, pid)).state == "awaiting_founder"
    assert "Your video is paused: limit reached" in {m["subject"] for m in registry.get_email().sent}
    async with maker() as s:  # operator fixes the budget; founder retries
        vb = (await s.execute(select(VendorBudget).where(VendorBudget.vendor == "transcription"))).scalar_one()
        vb.limit = Decimal("100")
        await s.commit()
    assert (await client.post(f"/v1/interview/{token}/takes/{tid}/reprocess")).status_code == 200
    await get_queue().drain()
    assert (await client.get(f"/v1/interview/{token}/takes/{tid}")).json()["status"] == "ready"


async def test_vendor_failure_retries_then_fails_cleanly_without_charge(client, workspace, maker):
    from app.integrations.renderer.mock import MockRenderer

    calls = {"n": 0}

    class Flaky(MockRenderer):
        async def process(self, req):
            calls["n"] += 1
            raise RuntimeError("renderer down")

    pid = await make_awaiting_founder(client)
    registry.override(renderer=Flaky(registry.get_storage()))
    token = await invite(client, pid)
    async with maker() as s:
        before = (await s.get(Workspace, workspace)).credit_balance
    tid = await record(client, token, 0)
    assert calls["n"] == 2  # renderer policy: 2 attempts
    async with maker() as s:
        assert (await s.get(Take, tid)).status == "failed"
        assert (await s.get(Workspace, workspace)).credit_balance == before
    r = (await client.post(f"/v1/interview/{token}/submit")).json()["detail"]["problems"]
    assert any("couldn't be processed" in p for p in r)


async def test_processing_is_idempotent_on_redelivery(client, workspace):
    from app.pipeline.takes import process_take

    pid = await make_awaiting_founder(client)
    token = await invite(client, pid)
    tid = await record(client, token, 0)
    n = len(registry.get_renderer().processed)
    await process_take(tid)  # duplicate delivery of the same job
    assert len(registry.get_renderer().processed) == n


# ---------- reminders, expiry, retention ----------
async def test_reminders_follow_schedule_once_each(client, workspace, maker):
    pid = await make_awaiting_founder(client)
    token = await invite(client, pid)
    registry.get_email().sent.clear()
    t0 = datetime.now(UTC)
    assert await jobs.send_due_reminders(t0 + timedelta(days=1)) == 0
    assert await jobs.send_due_reminders(t0 + timedelta(days=2, hours=1)) == 1
    assert await jobs.send_due_reminders(t0 + timedelta(days=2, hours=2)) == 0  # not twice
    assert await jobs.send_due_reminders(t0 + timedelta(days=6)) == 1
    mails = registry.get_email().sent
    assert len(mails) == 2 and all(m["subject"].startswith("Reminder:") and f"/i/{token}" in m["text"] for m in mails)
    assert await jobs.send_due_reminders(t0 + timedelta(days=30)) == 0  # expired at 14 days


async def test_long_outage_sends_one_reminder_not_a_burst(client, workspace):
    pid = await make_awaiting_founder(client)
    await invite(client, pid)
    registry.get_email().sent.clear()
    assert await jobs.send_due_reminders(datetime.now(UTC) + timedelta(days=10)) == 1
    assert len(registry.get_email().sent) == 1


async def test_no_reminders_after_submit_or_without_email(client, workspace):
    pid, _ = await submitted_project(client)
    registry.get_email().sent.clear()
    assert await jobs.send_due_reminders(datetime.now(UTC) + timedelta(days=5)) == 0
    pid2 = await make_awaiting_founder(client)
    r = await client.post(f"/v1/projects/{pid2}/interview", json={"founder_name": "X"}, headers=OWNER)  # no email
    assert r.status_code == 200
    assert await jobs.send_due_reminders(datetime.now(UTC) + timedelta(days=5)) == 0


async def test_expiry_job_drops_stored_token(client, workspace, maker):
    pid = await make_awaiting_founder(client)
    await invite(client, pid)
    assert await jobs.expire_sessions(datetime.now(UTC) + timedelta(days=15)) == 1
    async with maker() as s:
        assert (await s.execute(select(InterviewSession))).scalar_one().token_enc is None


async def test_raw_takes_deleted_after_retention_unless_kept(client, workspace, maker):
    pid, token = await submitted_project(client)
    await client.post(f"/v1/projects/{pid}/interview/merge", headers=OWNER)
    await get_queue().drain()
    storage = registry.get_storage()
    async with maker() as s:
        t = (await s.execute(select(Take).where(Take.project_id == pid))).scalars().first()
        tid, key = t.id, f"projects/{pid}/takes/{t.id}/raw/00000"
    assert await storage.exists(key)
    assert await jobs.purge_old_raw_takes(datetime.now(UTC) + timedelta(days=30)) == 0  # too early
    await client.put(f"/v1/projects/{pid}/keep-raw-takes", json={"keep": True}, headers=OWNER)
    assert await jobs.purge_old_raw_takes(datetime.now(UTC) + timedelta(days=100)) == 0  # owner keeps them
    await client.put(f"/v1/projects/{pid}/keep-raw-takes", json={"keep": False}, headers=OWNER)
    assert await jobs.purge_old_raw_takes(datetime.now(UTC) + timedelta(days=100)) == 2
    assert not await storage.exists(key)
    async with maker() as s:
        t = await s.get(Take, tid)
        assert t.raw_deleted_at is not None and t.processed_video_key and await storage.exists(t.processed_video_key)


async def test_stuck_processing_takes_are_requeued(client, workspace, maker):
    from app.pipeline.takes import requeue_stuck

    pid = await make_awaiting_founder(client)
    token = await invite(client, pid)
    tid = await record(client, token, 0)
    async with maker() as s:
        t = await s.get(Take, tid)
        t.status, t.created_at = "processing", datetime.now(UTC) - timedelta(hours=1)
        await s.commit()
    assert await requeue_stuck() == 1
    await get_queue().drain()
    async with maker() as s:
        assert (await s.get(Take, tid)).status == "ready"


# ---------- deletion & logging ----------
async def test_deleting_project_removes_takes_and_files(client, workspace, maker):
    pid, token = await submitted_project(client)
    storage = registry.get_storage()
    async with maker() as s:
        t = (await s.execute(select(Take).where(Take.project_id == pid))).scalars().first()
        keys = [f"projects/{pid}/takes/{t.id}/raw/00000", t.processed_video_key]
    assert all([await storage.exists(k) for k in keys])
    assert (await client.delete(f"/v1/admin/projects/{pid}", headers=OPS)).status_code == 200
    assert not any([await storage.exists(k) for k in keys])
    async with maker() as s:
        assert (await s.execute(select(Take))).first() is None and (
            await s.execute(select(InterviewSession))
        ).first() is None
    assert (await client.get(f"/v1/interview/{token}")).status_code == 404


def test_tokens_are_redacted_from_logs():
    import logging

    from app.main import RedactTokens, redact

    assert redact("GET /v1/interview/abc_DEF-123/takes HTTP/1.1") == "GET /v1/interview/[redacted]/takes HTTP/1.1"
    assert redact("/v1/share/SECRET?x=1") == "/v1/share/[redacted]?x=1"
    rec = logging.LogRecord(
        "uvicorn.access", logging.INFO, "", 0, '%s - "%s %s"', ("1.2.3.4", "GET", "/v1/interview/TOKEN123/x"), None
    )
    RedactTokens().filter(rec)
    assert "TOKEN123" not in rec.getMessage()
    import httpx

    rec = logging.LogRecord(
        "httpx",
        logging.INFO,
        "",
        0,
        "HTTP Request: %s %s",
        ("GET", httpx.URL("http://x/v1/interview/TOKEN123/y")),
        None,
    )
    RedactTokens().filter(rec)
    assert "TOKEN123" not in rec.getMessage() and "[redacted]" in rec.getMessage()


# ---------- srt helpers ----------
def test_srt_shift_and_trim():
    srt = "1\n00:00:00,000 --> 00:00:02,000\nhello\n\n2\n00:00:02,000 --> 00:00:04,000\nworld\n"
    out = iv.shifted_cues(srt, offset=10.0, trim_start=1.0, window=2.5)
    assert out == [(10.0, 11.0, "hello"), (11.0, 12.5, "world")]
    assert iv.shifted_cues(srt, 0, 3.0, 5)[0][2] == "world"
    assert "00:00:10,000 --> 00:00:11,000" in iv.merge_srt(out)


async def test_admin_can_set_transcription_budget(client, workspace):
    r = await client.put("/v1/admin/vendor-budgets", json={"vendor": "transcription", "limit": "5"}, headers=OPS)
    assert r.status_code == 200


async def test_speedtest_slot_is_scoped_and_cleaned_up(client, workspace):
    pid = await make_awaiting_founder(client)
    token = await invite(client, pid)
    slot = (await client.post(f"/v1/interview/{token}/speedtest")).json()
    assert f"projects/{pid}/takes/speedtest-" in slot["key"]
    await client.put(api_path(slot["upload_url"]), content=b"x" * 1000)
    assert await registry.get_storage().exists(slot["key"])
    await client.post(f"/v1/interview/{token}/speedtest/done", json={"key": slot["key"]})
    assert not await registry.get_storage().exists(slot["key"])
    # cannot be used to delete someone else's file
    other = f"projects/{pid}/anchor.webm"
    await registry.get_storage().put(other, b"keep")
    await client.post(f"/v1/interview/{token}/speedtest/done", json={"key": other})
    assert await registry.get_storage().exists(other)


async def test_parallel_confirmations_preserve_every_chunk_and_complete(client, workspace, monkeypatch):
    pid = await make_awaiting_founder(client)
    token = await invite(client, pid)
    await client.post(f"/v1/interview/{token}/consent")
    take = (
        await client.post(
            f"/v1/interview/{token}/takes", json={"question_index": 0, "kind": "video", "mime": "video/webm"}
        )
    ).json()["id"]
    urls = (
        await client.post(f"/v1/interview/{token}/takes/{take}/chunk-urls", json={"indexes": list(range(8))})
    ).json()["urls"]
    for url in urls.values():
        assert (await client.put(api_path(url), content=b"x" * 500)).status_code == 200
    storage = registry.get_storage()
    original_size = storage.size
    arrived = 0
    together = asyncio.Event()

    async def synchronized_size(key):
        nonlocal arrived
        result = await original_size(key)
        arrived += 1
        if arrived == 8:
            together.set()
        await asyncio.wait_for(together.wait(), timeout=10)
        return result

    monkeypatch.setattr(storage, "size", synchronized_size)
    responses = await asyncio.gather(
        *(client.post(f"/v1/interview/{token}/takes/{take}/chunks/{i}/confirm") for i in range(8))
    )
    assert all(r.status_code == 200 for r in responses), [r.text for r in responses]
    saved = (await client.get(f"/v1/interview/{token}/takes/{take}")).json()
    assert saved["chunks_received"] == list(range(8))
    completed = await client.post(f"/v1/interview/{token}/takes/{take}/complete", json={"chunk_count": 8})
    assert completed.status_code == 200, completed.text
    assert completed.json()["status"] == "uploaded"
