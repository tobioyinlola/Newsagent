"""The Video Rulebook: every rule that decides how a business interview video is made, in one place.

How to change a rule (CI enforces all of this; see tests/test_video_rules.py):
- New behaviour is a NEW rule with a new id. Ids are never reused.
- A rule is never deleted. To stop using one, set status="retired" and replaced_by="<new id>".
- Changing a rule's value, or adding or retiring a rule, needs: VERSION + 1, one CHANGELOG line, and the lock file refreshed
  (`python scripts/export_video_rules.py`), so the change is visible in review.
- Every active rule is covered by at least one test that mentions its id (`covers("BIV-...")` in Python, `// covers: BIV-...`
  in TypeScript tests).
- One rule change per commit, named in the commit message. Video rules never ride along in unrelated feature commits.

Code reads values through `value("BIV-...")`; the renderer and the web app read the same values from the generated
`videoRules.generated.json`. docs/video-rules.md is generated from this file: the readable list for the whole team.
"""

from dataclasses import dataclass, field
from typing import Any, Literal

Area = Literal["interview", "script", "scene-order", "graphics", "audio", "quality", "cost", "safety"]
AREA_TITLES: dict[str, str] = {
    "interview": "The AI interview",
    "script": "What the presenter says",
    "scene-order": "How the video is put together",
    "graphics": "On-screen graphics",
    "audio": "Sound",
    "quality": "Quality check before delivery",
    "cost": "Cost and paid vendors",
    "safety": "Safety and editorial",
}


@dataclass(frozen=True)
class Rule:
    id: str
    area: Area
    title: str
    description: str
    value: Any = None
    since: int = 1  # the rulebook VERSION that introduced it
    status: Literal["active", "retired"] = "active"
    replaced_by: str | None = None
    enforced_in: tuple[str, ...] = field(default_factory=tuple)  # where the code applies it


VERSION = 1
CHANGELOG: list[str] = [
    "v1 (2026-11-02): rulebook created. Every business interview video rule recorded exactly as the code behaved on this date; "
    "no behaviour changed.",
]

RULES: list[Rule] = [
    # ---- the AI interview ----
    Rule("BIV-INT-001", "interview", "Questions asked",
         "The writer prepares this many short, open interview questions (each under 25 words, never yes/no).",
         4, enforced_in=("integrations/llm/json_llm.py",)),
    Rule("BIV-INT-002", "interview", "Most questions in one interview",
         "No interview has more questions than this; a question that repeats another in different words is dropped.",
         5, enforced_in=("services/interview.py", "services/guided.py")),
    Rule("BIV-INT-003", "interview", "Camera required",
         "The founder is recorded on camera. No camera, no interview; a camera that drops pauses the interview.",
         True, enforced_in=("frontend interview room",)),
    Rule("BIV-INT-004", "interview", "Answer window (seconds)",
         "Each answer gets a full minute. It is never shortened to fit an overall time.",
         60, enforced_in=("services/interview.py", "frontend interview/timing.ts")),
    Rule("BIV-INT-005", "interview", "Shortest answer window (seconds)",
         "No answer window is ever shorter than this.",
         15, enforced_in=("services/interview.py", "frontend interview/timing.ts")),
    Rule("BIV-INT-006", "interview", "Countdown before each answer (seconds)",
         "A countdown runs before recording starts, so the founder is ready.",
         5, enforced_in=("frontend interview/timing.ts",)),
    Rule("BIV-INT-007", "interview", "Round-up time after the window (seconds)",
         "When the minute is up, the founder gets this much extra time to finish their sentence.",
         5, enforced_in=("frontend interview/timing.ts",)),
    Rule("BIV-INT-008", "interview", "Interview length estimate (seconds)",
         "The whole interview is estimated at about six minutes. It is an estimate only and never cuts an answer.",
         360, enforced_in=("services/interview.py", "frontend interview/timing.ts")),
    Rule("BIV-INT-009", "interview", "Answers that must be recorded again",
         "An answer with no speech, that is too short, too dark, or contains abusive language must be re-recorded.",
         ["abusive_language", "dark_video", "no_speech", "too_short"], enforced_in=("services/interview.py",)),
    Rule("BIV-INT-010", "interview", "Answer checks (thresholds)",
         "No speech: under 1 s of speech or average level below -50 dB. Too short: under 2 s between first and last speech. "
         "Too dark: average brightness below 25 (of 255). Loud sound is accepted and levelled, never a reason to re-record.",
         {"min_speech_s": 1.0, "min_mean_db": -50, "min_span_s": 2, "min_brightness": 25},
         enforced_in=("renderer/src/process.ts",)),
    Rule("BIV-INT-011", "interview", "Answer clean-up",
         "Each kept answer is cleaned (rumble filter, noise reduction), trimmed to the speech, and levelled to -16 LUFS.",
         {"loudness_lufs": -16, "true_peak_db": -1.5, "lra": 11}, enforced_in=("renderer/src/process.ts",)),
    # ---- what the presenter says ----
    Rule("BIV-SCR-001", "script", "Nothing paid before approval",
         "The story and presenter script are written after the interview; nothing paid runs until the owner approves.",
         True, enforced_in=("services/guided.py",)),
    Rule("BIV-SCR-002", "script", "Presenter opening length (words)",
         "The presenter's opening is cut to at most this many words: every second of presenter video is paid for.",
         65, enforced_in=("services/guided.py",)),
    Rule("BIV-SCR-003", "script", "Fixed sign-off",
         "Every video ends with the same sign-off words, so the closing clip is made once per presenter and reused.",
         "This is Cover Founder News. Want to join us as a guest on the show? Visit coverfounder.com to sign up and produce "
         "your news coverage for free. Until our next story, have a great day!",
         enforced_in=("services/presenters.py", "services/guided.py")),
    Rule("BIV-SCR-004", "script", "Nothing said twice",
         "No sentence is repeated from the opening to the sign-off (the recap is allowed to revisit facts), and the press "
         "release never says a sentence twice.",
         True, enforced_in=("services/script_polish.py", "services/guided.py", "pipeline/steps.py")),
    Rule("BIV-SCR-005", "script", "Welcome before the first question",
         "The presenter welcomes the founder by first name before the first question, with a line chosen per video.",
         True, enforced_in=("services/conversation.py", "pipeline/steps.py")),
    Rule("BIV-SCR-006", "script", "Hand-over to the next question",
         "Between answers the presenter acknowledges the previous answer, using a line the writer grounded in that answer; "
         "if there is none, a short line from the standard pool. Then straight into the next question.",
         True, enforced_in=("services/broadcast_rules.py", "pipeline/steps.py")),
    Rule("BIV-SCR-007", "script", "Recap after the last answer (words)",
         "After the last answer the presenter recaps the business in this many spoken words, before the sign-off.",
         [50, 80], enforced_in=("integrations/llm/json_llm.py", "services/broadcast_rules.py", "pipeline/steps.py")),
    Rule("BIV-SCR-008", "script", "Claims are flagged, not asserted",
         "Sentences with money, funding, user numbers, rankings or superlatives are flagged for review; claims a founder makes "
         "are listed as unconfirmed, never stated as fact.",
         ["revenue", "funding", "users", "ranking", "superlative"], enforced_in=("services/claims.py",)),
    Rule("BIV-SCR-009", "script", "Nothing made up in the press release",
         "Dateline and media contact come only from what was given at sign-up and on the details page; what the company did "
         "not disclose is listed, not invented.",
         True, enforced_in=("services/guided.py",)),
    Rule("BIV-SCR-010", "script", "The founder's words are never rewritten",
         "A founder's recorded answer is their own statement in the video; it is never replaced or reworded.",
         True, enforced_in=("pipeline/steps.py",)),
    # ---- how the video is put together ----
    Rule("BIV-SCN-001", "scene-order", "Scene order",
         "Brand intro, opening shot (if any), presenter opening, explanation (if any), then for each answer: presenter asks, "
         "founder answers, cutaway (if any); then the recap, the sign-off, the sign-off shot (if any) and the brand outro.",
         ["brand_intro", "presenter_clip:opening shot", "anchor_intro", "anchor_explanation",
          "anchor_question+founder_answer+presenter_clip:cutaway", "anchor_analysis", "news_closing",
          "presenter_clip:sign-off", "brand_outro"],
         enforced_in=("pipeline/steps.py",)),
    Rule("BIV-SCN-002", "scene-order", "No cutaway after the last answer",
         "Library cutaways go between answers only, never after the last one.",
         True, enforced_in=("pipeline/steps.py",)),
    Rule("BIV-SCN-003", "scene-order", "Shortest answer kept (seconds)",
         "An answer shorter than this after trimming is left out of the video.",
         1.0, enforced_in=("services/interview.py", "pipeline/steps.py")),
    Rule("BIV-SCN-004", "scene-order", "Answer layouts",
         "Each answer is shown full screen (guided default), picture-in-picture, split screen, or as a column with the "
         "question and the founder's words in sync. The layout can be set per answer.",
         {"default": "full", "allowed": ["column", "full", "pip", "split"]}, enforced_in=("services/scene_plan.py",)),
    Rule("BIV-SCN-005", "scene-order", "Brand intro and outro (seconds)",
         "Every video opens with the Cover Founder intro and closes with the outro (BRAND_CARDS setting).",
         {"intro": 5.0, "outro": 6.0}, enforced_in=("pipeline/steps.py", "renderer brand cards")),
    Rule("BIV-SCN-006", "scene-order", "Presenter library clips (seconds)",
         "Real presenter footage frames the AI presenter: an opening shot, up to 4 cutaways, a sign-off shot. Lengths are "
         "limited per role; at least 720p. Chosen per project so a re-render keeps the same shots.",
         {"intro": [3.0, 20.0], "cutaway": [2.0, 10.0], "outro": [3.0, 20.0], "max_cutaways": 4, "min_height": 720},
         enforced_in=("services/presenter.py",)),
    Rule("BIV-SCN-007", "scene-order", "Product pictures belong to the written story",
         "In the guided video, the owner's pictures appear in the press release, not in the video.",
         True, enforced_in=("pipeline/steps.py",)),
    Rule("BIV-SCN-008", "scene-order", "Product footage (classic flow)",
         "The older script-first flow may show up to 5 product images (3-8 s each) or clips (2-8 s, silent).",
         {"max_items": 5, "image_s": [3.0, 8.0], "video_s": [2.0, 8.0]}, enforced_in=("services/broll.py",)),
    Rule("BIV-SCN-009", "scene-order", "Files delivered",
         "16:9 in HD and Light, a thumbnail and captions (SRT). Vertical 9:16 only when RENDER_VERTICAL is on.",
         ["16x9", "16x9-light", "thumbnail", "captions"], enforced_in=("pipeline/steps.py",)),
    # ---- on-screen graphics ----
    Rule("BIV-GFX-001", "graphics", "No AI-anchor or 'Featured' labels on screen",
         "The video carries no 'AI-generated anchor' or 'Featured' label (removed 2026-10-28).",
         True, enforced_in=("renderer/src/compositions/Chrome.tsx",)),
    Rule("BIV-GFX-002", "graphics", "LIVE badge location",
         "The LIVE badge shows the reporter's location while the presenter is on, and the founder's own location during "
         "their answers.",
         "Toronto, Canada", enforced_in=("services/broadcast_rules.py", "renderer/src/compositions/InterviewMerge.tsx")),
    Rule("BIV-GFX-003", "graphics", "Ticker limits",
         "At most 8 ticker lines of 90 characters.",
         {"max_lines": 8, "max_chars": 90}, enforced_in=("services/safety.py",)),
    Rule("BIV-GFX-004", "graphics", "Lower-third text limits",
         "Lower-third title up to 40 characters, subtitle up to 60.",
         {"title": 40, "subtitle": 60}, enforced_in=("services/safety.py",)),
    Rule("BIV-GFX-005", "graphics", "Answer headline bar",
         "Each answer has its own headline bar: the founder's surname and a short line from that answer.",
         "Founder: Shares the story behind the business", enforced_in=("services/broadcast_rules.py", "pipeline/steps.py")),
    Rule("BIV-GFX-006", "graphics", "Product web address at the sign-off (seconds)",
         "The product's web address shows top right for this long, starting when the presenter signs off.",
         5, enforced_in=("renderer/src/compositions/InterviewMerge.tsx",)),
    Rule("BIV-GFX-007", "graphics", "Name card timing (seconds)",
         "A speaker's name card slides in after a short delay and holds for a fixed time, then slides out, in every scene.",
         {"delay": 0.5, "hold": 6, "ramp_max": 0.4}, enforced_in=("renderer/src/compositions/LowerThird.tsx",)),
    Rule("BIV-GFX-008", "graphics", "Pictures cut, never fade",
         "Scenes join with a clean picture cut. Only the sound gets a very short ramp at the join.",
         True, enforced_in=("renderer/src/compositions/SceneEdge.tsx",)),
    # ---- sound ----
    Rule("BIV-AUD-001", "audio", "Broadcast loudness",
         "Finished videos are levelled to -16 LUFS with a -1.5 dB true-peak ceiling.",
         {"loudness_lufs": -16, "true_peak_db": -1.5, "lra": 11}, enforced_in=("renderer/src/media.ts",)),
    Rule("BIV-AUD-002", "audio", "Sound ramp at each cut (frames)",
         "A very short sound ramp at every join, so cuts never click.",
         5, enforced_in=("renderer/src/compositions/SceneEdge.tsx",)),
    Rule("BIV-AUD-003", "audio", "Light version keeps the HD sound",
         "The Light download copies the HD file's sound instead of re-encoding it, so it cannot clip where HD does not.",
         True, enforced_in=("renderer/src/media.ts",)),
    # ---- quality check ----
    Rule("BIV-QC-001", "quality", "Length matches the plan",
         "Each file's length must be within 5% (or 1 s, whichever is larger) of the planned length.",
         {"ratio": 0.05, "min_s": 1.0}, enforced_in=("pipeline/steps.py",)),
    Rule("BIV-QC-002", "quality", "Has sound", "Every video file must have a sound track.", True,
         enforced_in=("pipeline/steps.py",)),
    Rule("BIV-QC-003", "quality", "No clipping (dB)",
         "The sound's true peak must stay below this level.", -0.1, enforced_in=("pipeline/steps.py",)),
    Rule("BIV-QC-004", "quality", "Sound and picture in step (seconds)",
         "Sound and picture lengths may differ by at most this much.", 0.5, enforced_in=("pipeline/steps.py",)),
    Rule("BIV-QC-005", "quality", "All files rendered",
         "Every expected output file must exist before the video is ready.", True, enforced_in=("pipeline/steps.py",)),
    Rule("BIV-QC-006", "quality", "Media checked before rendering",
         "Every file a scene needs must exist and be non-empty before any render time is spent.", True,
         enforced_in=("services/scene_plan.py",)),
    # ---- cost ----
    Rule("BIV-COST-001", "cost", "Price of a video (credits)",
         "A video costs this many credits, whatever the vendors charge (CREDITS_PER_VIDEO setting).", "1",
         enforced_in=("services/credits.py",)),
    Rule("BIV-COST-002", "cost", "Identical presenter clips are never bought twice",
         "A clip is keyed by words, presenter, voice and pronunciations, and reused within a video and across customers.",
         True, enforced_in=("pipeline/steps.py",)),
    Rule("BIV-COST-003", "cost", "Presenter clips made at once",
         "At most this many presenter clips are generated in parallel.", 3, enforced_in=("pipeline/steps.py",)),
    Rule("BIV-COST-004", "cost", "Paid steps reserve budget first",
         "Every paid step holds budget before calling a vendor; no budget, or the pause switch, means no paid step.", True,
         enforced_in=("services/spend_guard.py",)),
    Rule("BIV-COST-005", "cost", "Retries never pay twice",
         "A vendor job id is saved before waiting on it, so a retry resumes the same job instead of buying another.", True,
         enforced_in=("services/provider_requests.py",)),
    # ---- safety ----
    Rule("BIV-SAFE-001", "safety", "No real news network names",
         "Briefs, overlays and graphics may not name real news networks.",
         ["cnn", "bbc", "fox news", "sky news", "al jazeera", "msnbc", "reuters", "bloomberg tv", "nbc news",
          "abc news", "cbs news", "channels tv", "arise news", "dw news", "france 24", "cnbc"],
         enforced_in=("services/safety.py",)),
    Rule("BIV-SAFE-002", "safety", "Moderation",
         "Briefs, scripts and founder transcripts are moderated: clearly disallowed content is blocked, borderline content "
         "waits for a person (MODERATION_HOLD_FOR_REVIEW).", True, enforced_in=("services/moderation_flow.py",)),
]

_BY_ID = {r.id: r for r in RULES}


def rule(rule_id: str) -> Rule:
    return _BY_ID[rule_id]


def value(rule_id: str) -> Any:
    return _BY_ID[rule_id].value


def active() -> list[Rule]:
    return [r for r in RULES if r.status == "active"]
