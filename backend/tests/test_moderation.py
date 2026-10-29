from decimal import Decimal

import pytest
from sqlalchemy import select

from app.integrations import registry
from app.models import AuditLog, ModerationCase, Project, Workspace
from app.pipeline.queue import get_queue
from app.services.moderation import fingerprint, screen_text
from tests.conftest import OPS, OWNER, VIDEO
from tests.helpers import invite, make_awaiting_founder, record

BENIGN = [
    "Acme helps farmers sell produce online across Nigeria and Ghana.",
    "Our team treats every customer well and prevents waste in the supply chain.",
    "We build electric tricycles for traders in Kano.",
    "Payments for market women, settled the same day.",
    "A cooperative that elects its leaders every year.",  # 'elects' is not a campaign
]
FLAGGED = [
    ("We offer guaranteed returns of 40% every month", "review", "financial_promises"),
    ("Our tea cures diabetes in two weeks", "review", "health_claims"),
    ("Daily forex signals and betting tips", "review", "regulated_services"),
    ("Vote for our founder in the election campaign", "review", "political"),
    ("Endorsed by the World Health Organization", "review", "false_endorsement"),
    ("Call the founder on +234 801 234 5678 or ada@acme.example", "review", "personal_data"),
    ("We are selling cocaine to students", "block", "illegal_goods"),
    ("Join our ransomware affiliate programme", "block", "malware_fraud"),
    ("death to the competition and kill them all", "block", "violence"),
]


@pytest.mark.parametrize("text", BENIGN)
def test_ordinary_startup_text_is_allowed(text):
    assert screen_text(text).level == "allow"


@pytest.mark.parametrize("text,level,category", FLAGGED)
def test_rules_flag_what_they_should(text, level, category):
    v = screen_text(text)
    assert v.level == level and category in v.categories and v.messages


def test_worst_verdict_wins_and_messages_are_plain():
    v = screen_text("Guaranteed returns! Also selling cocaine.")
    assert v.level == "block" and {"financial_promises", "illegal_goods"} <= set(v.categories)
    assert all("regex" not in m.lower() and "pattern" not in m.lower() for m in v.messages)


async def make_script(client, text, brief="Acme helps farmers sell produce online."):
    pid = (await client.post("/v1/projects", json={"brief_text": brief}, headers=OWNER)).json()["id"]
    s = (await client.post(f"/v1/projects/{pid}/script/generate", headers=OWNER)).json()
    body = {k: s[k] for k in ("ticker_lines", "lower_thirds", "interview_questions")}
    body["segments"] = [{"kind": "intro", "text": text}]
    await client.put(f"/v1/projects/{pid}/script", json=body, headers=OWNER)
    return pid, body


async def test_blocked_brief_is_refused_without_creating_a_project(client, workspace, maker):
    brief = "We are selling cocaine and firearms to students across the city."
    r = await client.post("/v1/projects", json={"brief_text": brief}, headers=OWNER)
    assert r.status_code == 422 and r.json()["detail"]["error"] == "content_blocked"
    async with maker() as s:
        assert (await s.execute(select(Project))).first() is None
        log = (await s.execute(select(AuditLog).where(AuditLog.action == "moderation.blocked"))).scalar_one()
        assert log.target_id == fingerprint(brief) and "cocaine" not in str(log.detail)  # no copy of the content


async def test_review_content_is_held_then_approved_by_operator(client, workspace, maker):
    pid, _ = await make_script(client, "Tonight: Acme offers guaranteed returns on every order.")
    registry.get_email().sent.clear()
    r = await client.post(f"/v1/projects/{pid}/script/approve", headers=OWNER)
    assert r.status_code == 409 and r.json()["detail"]["error"] == "in_review"
    r2 = await client.post(f"/v1/projects/{pid}/script/approve", headers=OWNER)  # asking again doesn't pile up cases
    assert r2.status_code == 409
    queue = (await client.get("/v1/admin/moderation", headers=OPS)).json()
    assert len(queue) == 1 and queue[0]["stage"] == "script" and "financial_promises" in queue[0]["reasons"]
    assert queue[0]["workspace_name"] == "Acme" and "guaranteed returns" in queue[0]["excerpt"]
    assert any(m["subject"] == "Content needs review" for m in registry.get_email().sent)
    mine = (await client.get(f"/v1/projects/{pid}/moderation", headers=OWNER)).json()
    assert mine[0]["status"] == "pending"
    async with maker() as s:
        assert (await s.get(Workspace, workspace)).credit_balance == Decimal(
            "10"
        ) - VIDEO  # nothing paid for steps while held

    d = await client.post(
        f"/v1/admin/moderation/{queue[0]['id']}/decision", json={"decision": "approve", "note": "ok"}, headers=OPS
    )
    assert d.status_code == 200
    assert any(m["subject"] == "Your content was approved" for m in registry.get_email().sent)
    again = await client.post(
        f"/v1/admin/moderation/{queue[0]['id']}/decision", json={"decision": "reject"}, headers=OPS
    )
    assert again.status_code == 409  # decisions are final
    r3 = await client.post(f"/v1/projects/{pid}/script/approve", headers=OWNER)
    assert r3.status_code == 200
    await get_queue().drain()
    assert (await client.get(f"/v1/projects/{pid}", headers=OWNER)).json()["state"] == "final_ready"
    async with maker() as s:
        assert (
            await s.execute(select(AuditLog).where(AuditLog.action == "moderation.approve"))
        ).scalar_one().actor == "ops@example.com"


async def test_rejection_explains_and_editing_requires_a_fresh_review(client, workspace):
    pid, body = await make_script(client, "Our supplement cures diabetes.")
    await client.post(f"/v1/projects/{pid}/script/approve", headers=OWNER)
    case = (await client.get("/v1/admin/moderation", headers=OPS)).json()[0]
    await client.post(
        f"/v1/admin/moderation/{case['id']}/decision",
        json={"decision": "reject", "note": "Remove the health claim."},
        headers=OPS,
    )
    r = await client.post(f"/v1/projects/{pid}/script/approve", headers=OWNER)
    assert r.status_code == 422 and "Remove the health claim." in r.json()["detail"]["message"]
    body["segments"] = [{"kind": "intro", "text": "Our supplement cures malaria."}]  # edited, still flagged: a NEW case
    await client.put(f"/v1/projects/{pid}/script", json=body, headers=OWNER)
    assert (await client.post(f"/v1/projects/{pid}/script/approve", headers=OWNER)).status_code == 409
    assert len((await client.get("/v1/admin/moderation", headers=OPS)).json()) == 1
    body["segments"] = [{"kind": "intro", "text": "Tonight we feature Acme."}]  # fixed: no review needed at all
    await client.put(f"/v1/projects/{pid}/script", json=body, headers=OWNER)
    assert (await client.post(f"/v1/projects/{pid}/script/approve", headers=OWNER)).status_code == 200


async def test_blocked_script_never_runs_and_is_recorded(client, workspace, maker):
    pid, _ = await make_script(client, "We are selling firearms to anyone who asks.")
    r = await client.post(f"/v1/projects/{pid}/script/approve", headers=OWNER)
    assert r.status_code == 422 and r.json()["detail"]["error"] == "content_blocked"
    async with maker() as s:
        case = (await s.execute(select(ModerationCase))).scalar_one()
        assert case.status == "blocked" and (await s.get(Workspace, workspace)).credit_balance == Decimal("10") - VIDEO
    assert (await client.get("/v1/admin/moderation?status=blocked", headers=OPS)).json()[0]["id"] == case.id
    assert (await client.get("/v1/admin/moderation", headers=OPS)).json() == []  # blocked items aren't "pending"
    assert (
        await client.post(f"/v1/admin/moderation/{case.id}/decision", json={"decision": "approve"}, headers=OPS)
    ).status_code == 409


async def test_log_only_mode_lets_review_content_through(client, workspace):
    await client.patch("/v1/admin/settings", json={"moderation_mode": "log_only"}, headers=OPS)
    pid, _ = await make_script(client, "Acme offers guaranteed returns.")
    assert (await client.post(f"/v1/projects/{pid}/script/approve", headers=OWNER)).status_code == 200


async def test_llm_verdict_is_merged_and_an_llm_outage_fails_safe(client, workspace):
    from app.integrations.llm.mock import MockScriptLLM

    class Wrapped(MockScriptLLM):
        async def moderate(self, text):
            return {"level": "review", "reasons": ["misleading"]}

    registry.override(llm=Wrapped())
    pid, _ = await make_script(client, "Tonight we feature Acme.")
    r = await client.post(f"/v1/projects/{pid}/script/approve", headers=OWNER)
    assert r.status_code == 409
    assert "llm:misleading" in (await client.get("/v1/admin/moderation", headers=OPS)).json()[0]["reasons"]

    class Down(MockScriptLLM):
        async def moderate(self, text):
            raise RuntimeError("anthropic down")

    registry.override(llm=Down())
    pid2, _ = await make_script(client, "Tonight we feature Acme two.")
    assert (
        await client.post(f"/v1/projects/{pid2}/script/approve", headers=OWNER)
    ).status_code == 409  # held for a human, never published


async def test_founder_words_are_screened_before_the_final_render(client, workspace):
    from app.integrations.transcription.base import Transcript

    class Pitchy:
        async def transcribe(self, url):
            return Transcript(
                "Honestly we offer guaranteed returns to every investor.", "1\n00:00:00,000 --> 00:00:02,000\nx\n", True
            )

    registry.override(transcription=Pitchy())
    pid = await make_awaiting_founder(client)
    token = await invite(client, pid)
    await record(client, token, 0)
    await record(client, token, 1)
    await client.post(f"/v1/interview/{token}/submit")
    r = await client.post(f"/v1/projects/{pid}/interview/merge", headers=OWNER)
    assert r.status_code == 409 and r.json()["detail"]["error"] == "in_review"
    assert (await client.get(f"/v1/projects/{pid}", headers=OWNER)).json()[
        "state"
    ] == "processing_founder"  # not merged
    case = (await client.get("/v1/admin/moderation", headers=OPS)).json()[0]
    assert case["stage"] == "interview" and "guaranteed returns" in case["excerpt"]
    await client.post(f"/v1/admin/moderation/{case['id']}/decision", json={"decision": "approve"}, headers=OPS)
    assert (await client.post(f"/v1/projects/{pid}/interview/merge", headers=OWNER)).status_code == 200
    await get_queue().drain()
    assert (await client.get(f"/v1/projects/{pid}", headers=OWNER)).json()["state"] == "final_ready"


async def test_moderation_endpoints_are_scoped(client, workspace, maker):
    pid, _ = await make_script(client, "We offer guaranteed returns.")
    await client.post(f"/v1/projects/{pid}/script/approve", headers=OWNER)
    assert (await client.get("/v1/admin/moderation", headers=OWNER)).status_code == 403
    case_id = (await client.get("/v1/admin/moderation", headers=OPS)).json()[0]["id"]
    assert (
        await client.post(f"/v1/admin/moderation/{case_id}/decision", json={"decision": "approve"}, headers=OWNER)
    ).status_code == 403
    assert (
        await client.post(f"/v1/admin/moderation/{case_id}/decision", json={"decision": "maybe"}, headers=OPS)
    ).status_code == 422
    from app.models import User

    async with maker() as s:
        ws = Workspace(name="Other")
        s.add(ws)
        await s.flush()
        s.add(User(email="other@example.com", workspace_id=ws.id))
        await s.commit()
    assert (
        await client.get(f"/v1/projects/{pid}/moderation", headers={"Authorization": "Bearer dev:other@example.com"})
    ).status_code == 404


async def test_an_approval_survives_resaving_identical_text_but_not_an_edit(client, workspace):
    pid, body = await make_script(client, "Acme offers guaranteed returns on every order.")
    await client.post(f"/v1/projects/{pid}/script/approve", headers=OWNER)
    case = (await client.get("/v1/admin/moderation", headers=OPS)).json()[0]
    await client.post(f"/v1/admin/moderation/{case['id']}/decision", json={"decision": "approve"}, headers=OPS)
    # the editor re-saves the script (a new version, same words) before every approve click
    await client.put(f"/v1/projects/{pid}/script", json=body, headers=OWNER)
    r = await client.post(f"/v1/projects/{pid}/script/approve", headers=OWNER)
    assert r.status_code == 200
