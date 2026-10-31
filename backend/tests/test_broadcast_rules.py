from types import SimpleNamespace

import pytest
from sqlalchemy import select

from app.integrations import registry
from app.integrations.transcription.base import Transcript
from app.models import AuditLog, Project, Workspace
from app.pipeline.queue import get_queue
from app.services import broadcast_rules as rules
from app.services import language_audit
from tests.conftest import OWNER
from tests.helpers import record
from tests.test_live_interview import live_project, start, state


def test_broadcast_defaults_are_answer_specific_distinct_and_repair_old_metadata():
    script = SimpleNamespace(
        story={"headline": "An overall headline", "chyrons": {"0": "An overall headline"}},
        segments=[{"kind": "intro", "text": "Welcome."}, {"kind": "outro", "text": "Closing."}],
    )
    answers = {
        0: "We help farmers reach buyers.",
        1: "Our new app launches in Lagos.",
        2: "We have a small team.",
        3: "We plan to reach more cities.",
    }
    rules.enrich(script, "Ada Obi", answers)
    assert all(line.startswith("OBI:") for line in script.story["chyrons"].values())
    assert len(set(script.story["chyrons"].values())) == 4
    assert "farmers" in script.story["chyrons"]["0"] and "Lagos" in script.story["chyrons"]["1"]
    assert len(set(script.story["answer_bridges"].values())) == 4
    assert [x["kind"] for x in script.segments] == ["intro", "analysis", "outro"]
    previous = script.story["chyrons"]["0"]
    rules.enrich(script, "Ada Obi", {**answers, 0: "We build tools for independent designers."})
    assert script.story["chyrons"]["0"] != previous and "designers" in script.story["chyrons"]["0"]
    assert sum(x["kind"] == "analysis" for x in script.segments) == 1


@pytest.mark.parametrize(
    "text", ["What the fuck is that?", "That is bullshit.", "You are an idiot.", "f.u.c.k", "ＦＵＣＫ"]
)
def test_abusive_transcripts_are_flagged(text):
    assert language_audit.has_abusive_language(text)


@pytest.mark.parametrize(
    "text", ["Our assistant helps customers.", "We are based in Scunthorpe.", "We class this as a new business model."]
)
def test_normal_business_words_are_not_flagged(text):
    assert not language_audit.has_abusive_language(text)


async def test_abusive_take_requires_retake_keeps_media_and_audits_without_logging_words(
    client, workspace, maker, monkeypatch
):
    pid = await live_project(client)
    token = (await start(client, pid)).json()["token"]
    original = registry.get_transcription().transcribe

    async def abusive(*args):
        return Transcript("This is fucking ridiculous.", "", True)

    monkeypatch.setattr(registry.get_transcription(), "transcribe", abusive)
    take_id = await record(client, token, 0)
    take = (await client.get(f"/v1/interview/{token}/takes/{take_id}")).json()
    assert take["status"] == "needs_retake" and "abusive_language" in take["flags"]
    assert any("Abusive language" in message for message in take["messages"])
    assert (await client.post(f"/v1/interview/{token}/submit")).status_code == 422
    async with maker() as db:
        from app.models import Take

        stored = await db.get(Take, take_id)
        assert stored.processed_video_key and await registry.get_storage().exists(stored.processed_video_key)
        audit = (await db.execute(select(AuditLog).where(AuditLog.action == "interview.abusive_language"))).scalar_one()
        assert "fucking" not in str(audit.detail).lower() and audit.detail["action"] == "retake_required"
    monkeypatch.setattr(registry.get_transcription(), "transcribe", original)
    for q in range(4):
        await record(client, token, q)
    assert (await client.post(f"/v1/interview/{token}/submit")).status_code == 200
    assert (await client.post(f"/v1/projects/{pid}/interview/merge", headers=OWNER)).status_code == 200
    await get_queue().drain()
    assert await state(client, pid) == "final_ready"


async def test_project_location_answer_summaries_and_recap_are_in_final_scene_plan(client, workspace, maker):
    pid = await live_project(client, name="Ada Obi")
    async with maker() as db:
        project = await db.get(Project, pid)
        project.founder_location = "Lagos, Nigeria"
        ws = await db.get(Workspace, workspace)
        ws.city, ws.country = "Toronto", "Canada"
        await db.commit()
    token = (await start(client, pid, name="Ada Obi")).json()["token"]
    for q in range(4):
        await record(client, token, q)
    assert (await client.post(f"/v1/projects/{pid}/interview/merge", headers=OWNER)).status_code == 200
    await get_queue().drain()
    async with maker() as db:
        project = await db.get(Project, pid)
        scenes = project.scene_plan["scenes"]
        assert [s["type"] for s in scenes][-2:] == ["anchor_analysis", "news_closing"]
        answers = [s for s in scenes if s.get("founder")]
        assert len(answers) == 4
        assert all(s["founder"]["location"] == "Lagos, Nigeria" and s["headline"].startswith("OBI:") for s in answers)
        assert all("mock transcript" in s["headline"] for s in answers)
    assert registry.get_renderer().requests[-1].props["liveLocation"] == "Toronto, Canada"
