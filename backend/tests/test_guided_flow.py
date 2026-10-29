"""The guided flow: details -> AI interview -> written story -> pictures -> video, spending as little as possible."""

from decimal import Decimal

from sqlalchemy import select

from app.integrations import registry
from app.integrations.avatar.mock import MockAvatarProvider
from app.models import Asset, Job, Project, ScriptVersion, Workspace
from app.pipeline.queue import get_queue
from tests.conftest import OWNER
from tests.helpers import record
from tests.test_broll import add_image
from tests.test_live_interview import start, state

DETAILS = {
    "brief_text": "Acme Farms raised a seed round to help farmers sell produce online.\n\nAnnouncement type: Funding round.",
    "founder_name": "Tobi Oyinlola",
    "founder_title": "CEO, Acme",
    "flow": "guided",
    "announcement_type": "funding_round",
}


async def guided_project(client):
    pid = (await client.post("/v1/projects", json=DETAILS, headers=OWNER)).json()["id"]
    r = await client.post(f"/v1/projects/{pid}/guided/start", headers=OWNER)
    assert r.status_code == 200, r.text
    return pid


async def interviewed(client, answers=(0, 1, 2, 3)):
    pid = await guided_project(client)
    token = (await start(client, pid)).json()["token"]
    for q in answers:
        await record(client, token, q)
    return pid


async def test_details_open_the_interview_and_spend_nothing(client, workspace, maker):
    pid = await guided_project(client)
    p = (await client.get(f"/v1/projects/{pid}", headers=OWNER)).json()
    assert p["state"] == "interviewing" and p["flow"] == "guided" and p["announcement_type"] == "funding_round"
    async with maker() as s:
        assert (await s.execute(select(Job).where(Job.project_id == pid))).scalars().all() == []
        assert (await s.get(Workspace, workspace)).credit_balance == Decimal("10")
        plan = (await s.execute(select(ScriptVersion).where(ScriptVersion.project_id == pid))).scalars().one()
        assert plan.approved and len(plan.interview_questions) == 4


async def test_finishing_the_interview_writes_the_story_for_review(client, workspace, maker):
    pid = await interviewed(client)
    r = await client.post(f"/v1/projects/{pid}/interview/merge", headers=OWNER)
    assert r.status_code == 200, r.text
    assert await state(client, pid) == "script_ready"
    story = (await client.get(f"/v1/projects/{pid}/story", headers=OWNER)).json()
    assert story["headline"] and story["sections"] and story["social"]["hook"] and story["social"]["post"]
    # press-release parts: the dateline carries today's date, the contact and "about" come from the details given
    from datetime import UTC, datetime

    assert str(datetime.now(UTC).year) in story["dateline"] and story["about"]
    assert story["contact"]["email"] and "company" in story["contact"]
    script = (await client.get(f"/v1/projects/{pid}/script", headers=OWNER)).json()
    assert (
        script["segments"][-1]["kind"] == "outro" and len(script["segments"][-1]["text"].split()) >= 40
    )  # a real sign-off, not one line
    assert len(script["interview_questions"]) == 4 and not script["approved"] and script["story"]["headline"]
    async with maker() as s:  # nothing from the presenter vendor yet: the owner reviews the story first
        stages = {j.stage for j in (await s.execute(select(Job).where(Job.project_id == pid))).scalars()}
        assert stages <= {"process_take"}
        assert len([a for a in (await s.get(Project, pid)).merge_plan["answers"] if a["include"]]) == 4


async def test_editing_the_story_keeps_the_questions_and_the_article(client, workspace):
    pid = await interviewed(client)
    await client.post(f"/v1/projects/{pid}/interview/merge", headers=OWNER)
    script = (await client.get(f"/v1/projects/{pid}/script", headers=OWNER)).json()
    body = {k: script[k] for k in ("segments", "ticker_lines", "lower_thirds")} | {"interview_questions": ["changed?"]}
    r = await client.put(f"/v1/projects/{pid}/script", json=body, headers=OWNER)
    assert r.status_code == 200
    assert r.json()["interview_questions"] == script["interview_questions"] and r.json()["story"] == script["story"]


async def test_all_four_answers_can_be_featured(client, workspace):
    pid = await interviewed(client)
    plan = {"layout": "column", "answers": [{"question_index": q, "include": True} for q in range(4)]}
    assert (await client.put(f"/v1/projects/{pid}/interview/plan", json=plan, headers=OWNER)).status_code == 200
    r = await client.post(f"/v1/projects/{pid}/interview/merge", headers=OWNER)
    assert r.status_code == 200, r.text


async def test_approval_needs_two_or_three_pictures_then_makes_the_video_cheaply(client, workspace, maker):
    class Spy(MockAvatarProvider):
        def __init__(self):
            super().__init__()
            self.texts: list[str] = []

        async def generate(self, req):
            self.texts.append(req.script_text)
            return await super().generate(req)

    spy = Spy()
    registry.override(avatar=spy)
    pid = await interviewed(client)
    await client.post(f"/v1/projects/{pid}/interview/merge", headers=OWNER)
    script = (await client.get(f"/v1/projects/{pid}/script", headers=OWNER)).json()
    body = {k: script[k] for k in ("segments", "ticker_lines", "lower_thirds", "interview_questions")}
    body["confirmed_claims"] = [c["text"] for c in script["claim_flags"]]
    await client.put(f"/v1/projects/{pid}/script", json=body, headers=OWNER)

    keys = [await add_image(client) for _ in range(2)]  # pictures are optional; they go with the written story
    items = [{"key": k, "caption": f"Picture {i + 1}", "seconds": 3} for i, k in enumerate(keys)]
    assert (await client.put(f"/v1/projects/{pid}/broll", json={"items": items}, headers=OWNER)).status_code == 200

    r = await client.post(f"/v1/projects/{pid}/script/approve", json={}, headers=OWNER)
    assert r.status_code == 200, r.text
    await get_queue().drain()
    assert await state(client, pid) == "final_ready"
    lead = "hear from the founder"
    assert len([t for t in spy.texts if lead in t]) == 1  # one hand-over in the whole programme, never two
    assert len(spy.texts) == 6  # opening, a question for each of the four answers, the sign-off
    # a published story (live share link) appears in other videos' tickers; an unshared one never does
    from app.services import cf_news

    async with maker() as s:
        assert await cf_news.ticker_items(s) == []
    assert (await client.post(f"/v1/projects/{pid}/share", headers=OWNER)).status_code == 200
    async with maker() as s:
        items = await cf_news.ticker_items(s)
        assert len(items) == 1 and items[0].startswith("ON COVER FOUNDER: ")
        assert await cf_news.ticker_items(s, exclude_project=pid) == []  # a video never lists itself
    async with maker() as s:
        kinds = {(a.type, a.format) for a in (await s.execute(select(Asset).where(Asset.project_id == pid))).scalars()}
        assert all(("question_clip", f"q{i}") in kinds for i in range(4))


def test_a_dollar_amount_with_a_decimal_point_is_one_claim_not_two():
    from app.services.claims import detect_claims

    flags = detect_claims("Minicor raised a $3.8M seed round led by IA Ventures. We are based in San Francisco.")
    texts = {f.text for f in flags}
    assert "Minicor raised a $3.8M seed round led by IA Ventures" in texts
    assert not any(t in {"Minicor raised a $3", "8M seed round led by IA Ventures"} for t in texts)


def test_the_product_address_is_shown_the_way_people_type_it():
    from app.pipeline.steps import display_url

    assert display_url("https://www.acme.com/") == "acme.com"
    assert display_url("http://shop.acme.com/products") == "shop.acme.com/products"
    assert display_url("acme.com") == "acme.com"


def test_the_presenter_always_has_an_opening():
    from app.integrations.llm.base import ScriptSegment
    from app.services.guided import _trim_words

    assert _trim_words(
        [ScriptSegment(kind="intro", text="Tonight, Acme. It matters."), ScriptSegment(kind="body", text="")], 90
    ) == [{"kind": "intro", "text": "Tonight, Acme. It matters."}]
    assert _trim_words([ScriptSegment(kind="intro", text=" . "), ScriptSegment(kind="body", text="")], 90) == []


async def test_the_owner_can_go_back_from_the_story_to_the_interview_and_produce_it_again(client, workspace):
    pid = await interviewed(client)
    await client.post(f"/v1/projects/{pid}/interview/merge", headers=OWNER)
    first = (await client.get(f"/v1/projects/{pid}/script", headers=OWNER)).json()["version"]
    r = await client.post(f"/v1/projects/{pid}/interview/reopen", headers=OWNER)
    assert r.status_code == 200 and r.json()["state"] == "interviewing"
    assert (
        await client.post(f"/v1/projects/{pid}/interview/reopen", headers=OWNER)
    ).status_code == 409  # only from the story
    r = await client.post(f"/v1/projects/{pid}/interview/merge", headers=OWNER)  # produce the story again
    assert r.status_code == 200 and r.json()["state"] == "script_ready"
    assert (await client.get(f"/v1/projects/{pid}/script", headers=OWNER)).json()["version"] > first


async def test_the_video_can_be_made_without_pictures(client, workspace):
    pid = await interviewed(client)
    await client.post(f"/v1/projects/{pid}/interview/merge", headers=OWNER)
    script = (await client.get(f"/v1/projects/{pid}/script", headers=OWNER)).json()
    body = {k: script[k] for k in ("segments", "ticker_lines", "lower_thirds", "interview_questions")}
    body["confirmed_claims"] = [c["text"] for c in script["claim_flags"]]
    await client.put(f"/v1/projects/{pid}/script", json=body, headers=OWNER)
    r = await client.post(f"/v1/projects/{pid}/script/approve", json={}, headers=OWNER)
    assert r.status_code == 200, r.text


def test_a_story_draft_accepts_single_strings_where_lists_are_expected():
    from app.integrations.llm.base import StoryDraft

    d = StoryDraft.model_validate(
        {
            "headline": "H",
            "dek": "D",
            "sections": [],
            "social": {"hook": "h", "post": "p"},
            "segments": [],
            "ticker_lines": "One line",
            "lower_thirds": {"title": "T", "subtitle": "S"},
            "unverified": "Akumah claims they will reach every market.",
            "chyrons": {"0": "AKUMAH: WE GROW"},
            "outro": ["Thanks.", "Goodbye."],
        }
    )
    assert d.unverified == ["Akumah claims they will reach every market."]
    assert d.ticker_lines == ["One line"] and d.chyrons == ["AKUMAH: WE GROW"]
    assert d.lower_thirds == [{"title": "T", "subtitle": "S"}] and d.outro == "Thanks. Goodbye."
