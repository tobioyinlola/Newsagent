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


def test_the_invitation_is_said_once_however_the_writer_worded_it():
    model_outro = "That was our look at Acme. If you want to get featured on Cover Founder, get in touch with us today. Thank you for watching."
    text = steps.with_invite(model_outro)
    assert text == model_outro  # not added again
    assert sum(polish.is_invite(s) for s in polish.sentences(text)) == 1
    # a worded-differently invite in the opening is dropped in favour of the closing one
    sc = script(
        [
            {
                "kind": "intro",
                "text": "Tonight, Acme. Want your story featured? Get in touch with Cover Founder. Let's hear from the founder.",
            },
            {"kind": "outro", "text": "Thanks to the founder. Thank you for watching."},
        ]
    )
    t = steps.segment_texts(sc)
    assert not polish.has_invite(t["main"]) and sum(polish.is_invite(s) for s in polish.sentences(t["outro"])) == 1
    assert t["outro"].endswith("Thank you for watching.")  # the invitation sits before the sign-off line


def test_only_one_thank_you_for_watching():
    out = polish.remove_repeats(["Great. Thank you for watching.", "That is all. Thank you for watching."])
    assert sum("watching" in p for p in out) == 1 and "watching" in out[1]


def test_the_standard_sign_off_is_unchanged_so_its_presenter_clip_is_still_reused():
    t = steps.segment_texts(script([{"kind": "outro", "text": presenters.STANDARD_OUTRO}]))
    assert t["outro"] == f"That was Cover Founder News. {steps.FEATURE_INVITE} Thank you for watching."


def test_the_first_question_does_not_hand_over_again_when_the_opening_already_did():
    project = SimpleNamespace(flow="guided")
    opening = [{"kind": "intro", "text": "Tonight, Acme raises a round. Let's hear from the founder now."}]
    qs = ["What made you start Acme?", "Where do you want it in a year?"]
    spoken = steps.question_texts(project, script(opening, qs), [0, 1])
    assert spoken[0] == "What made you start Acme?"  # no second "let's hear from the founder"
    plain = [{"kind": "intro", "text": "Tonight, Acme raises a round."}]
    assert steps.question_texts(project, script(plain, qs), [0, 1])[0].startswith("Let's hear from the founder. ")


def test_a_question_that_repeats_an_earlier_line_is_trimmed_but_never_emptied():
    project = SimpleNamespace(flow="classic")
    sc = script(
        [{"kind": "intro", "text": "Tonight, Acme."}], ["What made you start Acme?", "What made you start Acme?"]
    )
    spoken = steps.question_texts(project, sc, [0, 1])
    assert (
        spoken[0] == "What made you start Acme?" and spoken[1] == "What made you start Acme?"
    )  # asked as written, not blank


def test_the_presenter_only_script_is_deduplicated_and_ends_with_one_invitation():
    sc = script(
        [
            {"kind": "intro", "text": "Acme raised money. Acme raised money."},
            {"kind": "body", "text": "It will hire people."},
            {"kind": "outro", "text": "Get featured on Cover Founder by getting in touch. Thank you for watching."},
        ]
    )
    text = steps.presenter_only_text(sc)
    assert text.count("Acme raised money") == 1
    assert sum(polish.is_invite(s) for s in polish.sentences(text)) == 1


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
