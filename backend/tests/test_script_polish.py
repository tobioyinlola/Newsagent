"""The presenter never says the same thing twice, anywhere from the opening to the sign-off."""

from types import SimpleNamespace

from app.pipeline import steps
from app.services import presenters
from app.services import script_polish as polish


def script(segments, questions=()):
    return SimpleNamespace(segments=segments, interview_questions=list(questions))


def test_sentences_keep_abbreviations_together():
    s = polish.sentences("Onyeka & Sons Ltd. raised money. Mr. Akumah said so! Is it big?")
    assert s == ["Onyeka & Sons Ltd. raised money.", "Mr. Akumah said so!", "Is it big?"]


def test_repeats_are_removed_across_pieces_but_different_sentences_stay():
    out = polish.remove_repeats(
        [
            "Onyeka and Sons raised one hundred million dollars. The company makes radios.",
            "The company makes radios. It plans to hire more people.",
        ]
    )
    assert out == [
        "Onyeka and Sons raised one hundred million dollars. The company makes radios.",
        "It plans to hire more people.",
    ]
    # genuinely different sentences that share a few words are not touched
    keep = polish.remove_repeats(["The company raised $100 million.", "The company plans to raise more next year."])
    assert keep[0] and keep[1]


def test_a_reworded_repeat_is_still_a_repeat():
    out = polish.remove_repeats(
        [
            "We want to take the business global within twelve months.",
            "Take the business global within twelve months, we want.",
        ]
    )
    assert out[1] == ""


def test_the_invitation_to_get_featured_is_never_spoken():
    sc = script(
        [
            {
                "kind": "intro",
                "text": "Tonight, Acme. Want your story featured? Get in touch with Cover Founder. Joining us is Ada.",
            },
            {
                "kind": "outro",
                "text": "Thanks, Ada. If you want to get featured on Cover Founder, get in touch with us. Thank you for watching.",
            },
        ]
    )
    t = steps.segment_texts(sc)
    assert not polish.has_invite(t["main"]) and not polish.has_invite(t["outro"])
    assert t["outro"] == "Thanks, Ada. Thank you for watching."


def test_the_programme_rounds_off_once():
    out = steps.segment_texts(
        script(
            [
                {
                    "kind": "outro",
                    "text": "That's all for this edition of Cover Founder. Thank you, Ada, for coming in. Thank you for watching. Have a wonderful day.",
                }
            ]
        )
    )["outro"]
    # two separate round-ups: the last one stays (and its two lines are one round-up); the earlier one goes
    assert out == "Thank you, Ada, for coming in. Thank you for watching. Have a wonderful day."


def test_only_one_thank_you_for_watching():
    out = polish.remove_repeats(["Great. Thank you for watching.", "That is all. Thank you for watching."])
    assert sum("watching" in p for p in out) == 1 and "watching" in out[1]


def test_the_standard_sign_off_is_just_the_sign_off():
    t = steps.segment_texts(script([{"kind": "outro", "text": presenters.STANDARD_OUTRO}]))
    assert t["outro"] == presenters.STANDARD_OUTRO


def test_the_opening_does_not_hand_over():
    t = steps.segment_texts(
        script([{"kind": "intro", "text": "Tonight, Acme raises a round. Joining us is Ada. Let's hear from her now."}])
    )
    assert t["main"] == "Tonight, Acme raises a round. Joining us is Ada."


def test_the_first_question_welcomes_the_guest_by_name_and_later_ones_acknowledge_the_answer():
    project = SimpleNamespace(flow="guided", interview_mode="live", id="abc123", founder_name="Onyeka Akumah")
    qs = ["What made you start Acme?", "What does the money change?", "Where next?", "Any advice?"]
    spoken = steps.question_texts(
        project, script([{"kind": "intro", "text": "Tonight, Acme raises a round."}], qs), [0, 1, 2, 3]
    )
    assert spoken[0].startswith("Onyeka") or "Onyeka" in spoken[0].split("?")[0]
    assert spoken[0].endswith("What made you start Acme?")
    assert "let's hear from" not in " ".join(spoken.values()).lower()
    bridges = [spoken[i].replace(qs[i], "").strip() for i in (1, 2, 3)]
    assert all(b for b in bridges) and len(set(bridges)) == 3  # each gap is acknowledged, differently
    assert (
        spoken[3].lower().count("last")
        + spoken[3].lower().count("finally")
        + spoken[3].lower().count("finish")
        + spoken[3].lower().count("one more")
        >= 1
    )


def test_different_videos_greet_and_bridge_differently_but_one_video_is_stable():
    def run(pid):
        project = SimpleNamespace(flow="guided", interview_mode="live", id=pid, founder_name="Ada Obi")
        return steps.question_texts(
            project, script([{"kind": "intro", "text": "Tonight."}], ["Q one?", "Q two?", "Q three?"]), [0, 1, 2]
        )

    assert run("aaaaaa") == run("aaaaaa")
    openers = {run(f"{i:06x}")[0].split("Q one?")[0] for i in range(40)}
    assert len(openers) >= 4  # not the same hook on every video


def test_with_no_name_the_welcome_still_reads_naturally():
    project = SimpleNamespace(flow="guided", interview_mode="live", id="zzz", founder_name="")
    spoken = steps.question_texts(project, script([{"kind": "intro", "text": "Tonight."}], ["Q one?"]), [0])
    assert "{name}" not in spoken[0] and spoken[0].endswith("Q one?") and not spoken[0].startswith(",")


def test_the_new_flow_never_costs_the_presenter_vendor_more_words_than_the_old_one():
    """Presenter clips are paid for by the second. The old programme: an opening up to 90 words ending with a hand-over, four
    questions (the first prefixed with a 5-word hand-over), and a closing of up to 140 words plus the 23-word invitation. The new
    one welcomes and bridges (a few words per question) but has shorter, single-purpose opening and closing."""
    words = lambda s: len(s.split())  # noqa: E731
    old_total = 90 + (5 + 4 * 14) + (140 + 23)
    project = SimpleNamespace(flow="guided", interview_mode="live", id="abc123", founder_name="Onyeka")
    opening = " ".join(["word"] * 65)  # the most the new opening can be (guided.PRESENTER_WORDS)
    closing = " ".join(["word"] * 70)  # the most the new prompt asks the closing to be
    qs = ["Why did you start this company and what problem were you solving?"] * 4
    qs = [f"{q.rstrip('?')} number {i}?" for i, q in enumerate(qs)]  # distinct, ~14 words each
    spoken = steps.question_texts(project, script([{"kind": "intro", "text": opening}], qs), [0, 1, 2, 3])
    new_total = words(opening) + sum(words(t) for t in spoken.values()) + words(closing)
    assert new_total <= old_total, (new_total, old_total)


def test_a_question_that_repeats_an_earlier_line_is_trimmed_but_never_emptied():
    project = SimpleNamespace(flow="classic")
    sc = script(
        [{"kind": "intro", "text": "Tonight, Acme."}], ["What made you start Acme?", "What made you start Acme?"]
    )
    spoken = steps.question_texts(project, sc, [0, 1])
    assert (
        spoken[0] == "What made you start Acme?" and spoken[1] == "What made you start Acme?"
    )  # asked as written, not blank


def test_the_presenter_only_script_is_deduplicated_and_has_no_invitation():
    sc = script(
        [
            {"kind": "intro", "text": "Acme raised money. Acme raised money."},
            {"kind": "body", "text": "It will hire people."},
            {"kind": "outro", "text": "Get featured on Cover Founder by getting in touch. Thank you for watching."},
        ]
    )
    text = steps.presenter_only_text(sc)
    assert text.count("Acme raised money") == 1
    assert not polish.has_invite(text) and text.endswith("Thank you for watching.")


def test_only_listed_questions_play_once_each():
    project = SimpleNamespace(
        merge_plan={"order": [1, 0, 1, 2], "answers": [{"question_index": i, "include": True} for i in range(3)]}
    )
    assert steps.needed_questions(project, 3) == [1, 0, 2]


def test_the_press_release_never_repeats_a_sentence_across_paragraphs():
    from app.services.guided import _unrepeated_sections

    out = _unrepeated_sections(
        [
            {
                "heading": "",
                "paragraphs": [
                    "Acme sells radios to farmers.",
                    "Acme sells radios to farmers. It plans five new countries.",
                ],
            },
            {"heading": "More", "paragraphs": ["Acme sells radios to farmers."]},
        ]
    )
    assert out == [{"heading": "", "paragraphs": ["Acme sells radios to farmers.", "It plans five new countries."]}]
