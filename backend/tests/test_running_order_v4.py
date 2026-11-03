"""Video Rulebook v4: one fixed running order for guided business interview videos (BIV-SCN-010). Opening, hand-overs, closing
remark with the web address, sign-off. The founder's name, role and business always come from that video's own details."""

import uuid
from types import SimpleNamespace

from app.integrations import registry
from app.integrations.avatar.mock import MockAvatarProvider
from app.models import ScriptVersion
from app.pipeline import steps
from app.services import broadcast_rules, conversation, presenters
from app.video_rules import value
from tests.conftest import OWNER
from tests.test_brand import KIT
from tests.test_guided_flow import interviewed


def test_the_opening_names_this_videos_founder_and_business():
    # covers("BIV-SCR-011")
    say = conversation.opening
    assert say("Onyeka Akumah", "", "Acme Farms") == (
        "Joining us in the studio today is Onyeka Akumah, founder of Acme Farms. Welcome to Cover Founder News, Onyeka. "
        "We're glad to have you."
    )
    assert "Ada Obi, CEO of Kora Pay." in say("Ada Obi", "CEO", "Kora Pay")  # a role is said with the business
    assert "Saheed Akinbile, Co-founder and CTO, Minicor." in say("Saheed Akinbile", "Co-founder and CTO, Minicor", "Minicor")
    assert "Tobi Oyinlola, CEO, Acme." in say("Tobi Oyinlola", "CEO, Acme", "Acme Farms")  # never "of Acme Farms" twice
    assert "Welcome to Cover Founder News, Chidi." in say("Chidi Okafor", "", "Bolt Logistics")  # the first name, per video
    assert say("", "", "Acme Farms").startswith("Joining us in the studio today is the founder of Acme Farms.")
    assert say("", "", "") == "Joining us in the studio today is our guest. Welcome to Cover Founder News. We're glad to have you."


def test_hand_overs_come_from_the_pool_never_repeat_in_a_video_are_stable_and_vary_between_videos():
    # covers("BIV-SCR-012")
    pool = value("BIV-SCR-012")
    assert len(pool) == 6 and "Thanks for sharing that." in pool and "That's an interesting insight." in pool
    ids = [uuid.uuid4().hex for _ in range(300)]
    for pid in ids:
        lines = conversation.handovers(pid, 4)  # five questions at most: four hand-overs
        assert len(set(lines)) == 4 and set(lines) <= set(pool)
        assert conversation.handovers(pid, 4) == lines  # a retried step asks for the same clips
    assert {conversation.handovers(pid, 1)[0] for pid in ids} == set(pool)  # videos open their hand-overs differently


def test_the_closing_remark_is_one_line_plus_the_web_address_said_aloud():
    # covers("BIV-SCR-013")
    line = "Acme Farms helps smallholder farmers sell produce directly to verified buyers on their phones"
    assert conversation.closing_remark(line, "https://www.acmefarms.com/about/") == (
        "Acme Farms helps smallholder farmers sell produce directly to verified buyers on their phones. "
        "Find out more at acmefarms dot com."
    )
    assert conversation.closing_remark(line, None) == line + "."  # no website: no address sentence
    long = " ".join(f"word{i}" for i in range(60))
    assert len(conversation.closing_remark(long, None).split()) == value("BIV-SCR-013")["max_words"]
    assert conversation.spoken_address("http://shop.kora.co.uk/pay") == "shop dot kora dot co dot uk"


def test_the_sign_off_is_said_exactly_as_written():
    # covers("BIV-SCR-014")
    assert presenters.STANDARD_OUTRO == "This is Cover Founder News. Until we bring you our next story, have a good day!"
    script = SimpleNamespace(
        segments=[
            {"kind": "intro", "text": conversation.opening("Tobi Oyinlola", "", "Acme Farms")},
            {"kind": "analysis", "text": "Acme Farms helps farmers. Find out more at acmefarms dot com."},
            {"kind": "outro", "text": presenters.STANDARD_OUTRO},
        ],
        story={"video_flow": 2},
    )
    texts = steps.segment_texts(script)  # the repeat filter must not cut "This is Cover Founder News." as an echo
    assert texts["outro"] == presenters.STANDARD_OUTRO
    assert texts["main"].startswith("Joining us in the studio today is Tobi Oyinlola")


def test_videos_written_before_v4_keep_their_old_running_order():
    # covers("BIV-SCN-010")
    project = SimpleNamespace(id="a" * 32, founder_name="Tobi Oyinlola", interview_enabled=True, flow="guided", interview_mode="live")
    old = SimpleNamespace(segments=[{"kind": "intro", "text": "An opening."}], interview_questions=["Q one?", "Q two?"], story={})
    new = SimpleNamespace(segments=old.segments, interview_questions=old.interview_questions, story={"video_flow": 2})
    old_lines, new_lines = steps.question_texts(project, old, [0, 1]), steps.question_texts(project, new, [0, 1])
    assert old_lines[0].startswith(conversation.welcome(project.id, project.founder_name))  # the old welcome in question 1
    assert new_lines[0] == "Q one?"  # v4: the opening already welcomed the guest
    assert new_lines[1] == f"{conversation.handovers(project.id, 1)[0]} Q two?"


def test_recording_an_answer_again_never_removes_the_closing_remark():
    # covers("BIV-SCN-010")
    remark = {"kind": "analysis", "text": "Acme Farms helps farmers."}
    script = ScriptVersion(segments=[{"kind": "intro", "text": "Hi."}, remark, {"kind": "outro", "text": "Bye."}], story={"video_flow": 2})
    broadcast_rules.enrich(script, "Tobi Oyinlola", {0: "First answer about farmers."})
    broadcast_rules.enrich(script, "Tobi Oyinlola", {0: "A different answer, recorded again."})
    assert script.segments.count(remark) == 1 and "startup_summary" not in script.story
    assert script.story["chyrons"]["0"].startswith("OYINLOLA:")  # the headline bars are still made per answer


async def test_the_founders_name_in_the_opening_uses_the_pronunciation_list(client, workspace):
    # covers("BIV-SCR-011")
    asked = []

    class Spy(MockAvatarProvider):
        async def generate(self, req):
            asked.append(req)
            return await super().generate(req)

    registry.override(avatar=Spy())
    assert (await client.put("/v1/brand-kit", json=KIT, headers=OWNER)).status_code == 200
    pid = await interviewed(client)
    assert (await client.post(f"/v1/projects/{pid}/interview/merge", headers=OWNER)).status_code == 200
    script = (await client.get(f"/v1/projects/{pid}/script", headers=OWNER)).json()
    body = {k: script[k] for k in ("segments", "ticker_lines", "lower_thirds", "interview_questions")}
    body["confirmed_claims"] = [c["text"] for c in script["claim_flags"]]
    await client.put(f"/v1/projects/{pid}/script", json=body, headers=OWNER)
    assert (await client.post(f"/v1/projects/{pid}/script/approve", json={}, headers=OWNER)).status_code == 200
    from app.pipeline.queue import get_queue

    await get_queue().drain()
    opening = next(r for r in asked if r.script_text.startswith("Joining us in the studio today is Tobi Oyinlola"))
    assert opening.pronunciation == {"Oyinlola": "oh-yin-LOH-lah"}


async def test_the_opening_closing_remark_and_sign_off_are_view_only_for_the_owner(client, workspace):
    # covers("BIV-SCN-010")
    pid = await interviewed(client)
    assert (await client.post(f"/v1/projects/{pid}/interview/merge", headers=OWNER)).status_code == 200
    script = (await client.get(f"/v1/projects/{pid}/script", headers=OWNER)).json()
    original = {x["kind"]: x["text"] for x in script["segments"]}
    assert set(original) == {"intro", "analysis", "outro"}

    def body(segments, **changes):
        out = {k: script[k] for k in ("ticker_lines", "lower_thirds", "interview_questions")}
        return {**out, "segments": segments, "confirmed_claims": [c["text"] for c in script["claim_flags"]], **changes}

    # edited texts are ignored: the three parts keep what we wrote
    edited = [{**x, "text": "Something the owner typed instead."} for x in script["segments"]]
    saved = (await client.put(f"/v1/projects/{pid}/script", json=body(edited), headers=OWNER)).json()
    assert {x["kind"]: x["text"] for x in saved["segments"]} == original
    # a page that leaves the sign-off out (it is not shown) still gets it back, in the right order
    without_sign_off = [x for x in script["segments"] if x["kind"] != "outro"]
    saved = (await client.put(f"/v1/projects/{pid}/script", json=body(without_sign_off), headers=OWNER)).json()
    assert [x["kind"] for x in saved["segments"]] == ["intro", "analysis", "outro"]
    assert saved["segments"][-1]["text"] == presenters.STANDARD_OUTRO
    # the news ticker is still the owner's to edit
    saved = (
        await client.put(
            f"/v1/projects/{pid}/script",
            json=body(script["segments"], ticker_lines=["My own ticker line"]),
            headers=OWNER,
        )
    ).json()
    assert saved["ticker_lines"] == ["My own ticker line"]
