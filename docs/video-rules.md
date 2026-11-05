# Video rules: business interview videos

Generated from `backend/app/video_rules/rulebook.py` (rulebook version 5). Do not edit by hand: change the
rulebook, then run `uv run python ../scripts/export_video_rules.py` from `backend/`. How rules may change is written at
the top of the rulebook; in short, rules are added, never deleted, and every change is versioned and tested.

## The AI interview

| Id | Rule | Value |
|---|---|---|
| `BIV-INT-001` | **Questions asked.** The writer prepares this many short, open interview questions (each under 25 words, never yes/no). | 4 |
| `BIV-INT-002` | **Most questions in one interview.** No interview has more questions than this; a question that repeats another in different words is dropped. | 5 |
| `BIV-INT-003` | **Camera required.** The founder is recorded on camera. No camera, no interview; a camera that drops pauses the interview. | true |
| `BIV-INT-004` | **Answer window (seconds).** Each answer gets a full minute. It is never shortened to fit an overall time. | 60 |
| `BIV-INT-005` | **Shortest answer window (seconds).** No answer window is ever shorter than this. | 15 |
| `BIV-INT-007` | **Round-up time after the window (seconds).** When the minute is up, the founder gets this much extra time to finish their sentence. | 5 |
| `BIV-INT-008` | **Interview length estimate (seconds).** The whole interview is estimated at about six minutes. It is an estimate only and never cuts an answer. | 360 |
| `BIV-INT-009` | **Answers that must be recorded again.** An answer with no speech, that is too short, too dark, or contains abusive language must be re-recorded. | ["abusive_language", "dark_video", "no_speech", "too_short"] |
| `BIV-INT-010` | **Answer checks (thresholds).** No speech: under 1 s of speech or average level below -50 dB. Too short: under 2 s between first and last speech. Too dark: average brightness below 25 (of 255). Loud sound is accepted and levelled, never a reason to re-record. | {"min_speech_s": 1.0, "min_mean_db": -50, "min_span_s": 2, "min_brightness": 25} |
| `BIV-INT-011` | **Answer clean-up.** Each kept answer is cleaned (rumble filter, noise reduction), trimmed to the speech, and levelled to -16 LUFS. | {"loudness_lufs": -16, "true_peak_db": -1.5, "lra": 11} |
| `BIV-INT-012` | **Countdown before each answer (seconds), recorded.** A countdown runs before each answer so the founder is ready, and the recording runs through it from its first second: nothing said early or right at the end of the countdown is lost. The lead-in is trimmed off with the other silence when the answer is cleaned up (BIV-INT-011). | 5 |

## What the presenter says

| Id | Rule | Value |
|---|---|---|
| `BIV-SCR-001` | **Nothing paid before approval.** The story and presenter script are written after the interview; nothing paid runs until the owner approves. | true |
| `BIV-SCR-004` | **Nothing said twice.** No sentence is repeated from the opening to the sign-off (the recap is allowed to revisit facts), and the press release never says a sentence twice. | true |
| `BIV-SCR-008` | **Claims are flagged, not asserted.** Sentences with money, funding, user numbers, rankings or superlatives are flagged for review; claims a founder makes are listed as unconfirmed, never stated as fact. | ["revenue", "funding", "users", "ranking", "superlative"] |
| `BIV-SCR-009` | **Nothing made up in the press release.** Dateline and media contact come only from what was given at sign-up and on the details page; what the company did not disclose is listed, not invented. | true |
| `BIV-SCR-010` | **The founder's words are never rewritten.** A founder's recorded answer is their own statement in the video; it is never replaced or reworded. | true |
| `BIV-SCR-011` | **The opening.** Right after the brand intro the presenter welcomes the founder by name and names the business. Name, role and business come from that video's details: role is 'founder of <business>' when no role is given, '<role> of <business>' when one is, and just '<role>' when the role already names the business (it contains a comma, as in 'CEO, Acme', or the business's first word). | {"with_name": "Joining us in the studio today is {name}{role}. Welcome to Cover Founder News, {first_name}. We're glad to have you.", "without_name": "Joining us in the studio today is {role}. Welcome to Cover Founder News. We're glad to have you.", "default_role": "founder of {company}", "role_of": "{title} of {company}"} |
| `BIV-SCR-012` | **Hand-over lines between answers.** From the second question on, the presenter opens with one of these lines, then asks the question. Each video takes its own order from its id, so videos differ, and never uses a line twice. | ["Thanks for sharing that.", "That's an interesting insight.", "Thanks for the insight.", "That's really helpful, thank you.", "Great point, thank you.", "I appreciate you sharing that."] |
| `BIV-SCR-013` | **Closing remark.** After the last answer the presenter says one line about the business (written from that video's own story, facts only, at most this many words), then the web address the way people say it. No website: no address sentence. | {"max_words": 25, "address": "Find out more at {address}."} |
| `BIV-SCR-014` | **The sign-off.** Every video ends with these words, so the sign-off clip is made once per presenter and voice, then reused. | “This is Cover Founder News. Until we bring you our next story, have a good day!” |

## How the video is put together

| Id | Rule | Value |
|---|---|---|
| `BIV-SCN-002` | **No cutaway after the last answer.** Library cutaways go between answers only, never after the last one. | true |
| `BIV-SCN-003` | **Shortest answer kept (seconds).** An answer shorter than this after trimming is left out of the video. | 1.0 |
| `BIV-SCN-004` | **Answer layouts.** Each answer is shown full screen (guided default), picture-in-picture, split screen, or as a column with the question and the founder's words in sync. The layout can be set per answer. | {"default": "full", "allowed": ["column", "full", "pip", "split"]} |
| `BIV-SCN-005` | **Brand intro and outro (seconds).** Every video opens with the Cover Founder intro and closes with the outro (BRAND_CARDS setting). | {"intro": 5.0, "outro": 6.0} |
| `BIV-SCN-006` | **Presenter library clips (seconds).** Real presenter footage frames the AI presenter: an opening shot, up to 4 cutaways, a sign-off shot. Lengths are limited per role; at least 720p. Chosen per project so a re-render keeps the same shots. | {"intro": [3.0, 20.0], "cutaway": [2.0, 10.0], "outro": [3.0, 20.0], "max_cutaways": 4, "min_height": 720} |
| `BIV-SCN-007` | **Product pictures belong to the written story.** In the guided video, the owner's pictures appear in the press release, not in the video. | true |
| `BIV-SCN-008` | **Product footage (classic flow).** The older script-first flow may show up to 5 product images (3-8 s each) or clips (2-8 s, silent). | {"max_items": 5, "image_s": [3.0, 8.0], "video_s": [2.0, 8.0]} |
| `BIV-SCN-009` | **Files delivered.** 16:9 in HD and Light, a thumbnail and captions (SRT). Vertical 9:16 only when RENDER_VERTICAL is on. | ["16x9", "16x9-light", "thumbnail", "captions"] |
| `BIV-SCN-010` | **Running order (guided business interview videos).** Brand intro, opening shot (if any), the presenter's opening, then for each answer: the presenter asks (from the second question on, after a hand-over line), the founder answers, a cutaway (if any, never after the last answer); then the closing remark with the web address card, the sign-off, the sign-off shot (if any) and the brand outro. Videos written before rulebook v4 keep their old running order. | ["brand_intro", "presenter_clip:opening shot", "anchor_intro:opening", "anchor_question+founder_answer", "handover+anchor_question+founder_answer+presenter_clip:cutaway", "anchor_analysis:closing_remark+url_card", "news_closing:sign_off", "presenter_clip:sign-off", "brand_outro"] |

## On-screen graphics

| Id | Rule | Value |
|---|---|---|
| `BIV-GFX-001` | **No AI-anchor or 'Featured' labels on screen.** The video carries no 'AI-generated anchor' or 'Featured' label (removed 2026-10-28). | true |
| `BIV-GFX-009` | **No 'Featured' or 'AI-generated anchor' wording around the video.** Not in the render data, the quality check, social captions, the download or share pages, or the presenter-only video's banner. (How founders are told an AI presenter is used, in consent and emails, is separate and unchanged.) | true |
| `BIV-GFX-002` | **LIVE badge location.** The LIVE badge shows the reporter's location while the presenter is on, and the founder's own location during their answers. | Toronto, Canada |
| `BIV-GFX-003` | **Ticker limits.** At most 8 ticker lines of 90 characters. | {"max_lines": 8, "max_chars": 90} |
| `BIV-GFX-004` | **Lower-third text limits.** Lower-third title up to 40 characters, subtitle up to 60. | {"title": 40, "subtitle": 60} |
| `BIV-GFX-005` | **Answer headline bar.** Each answer has its own headline bar: the founder's surname and a short line from that answer. | Founder: Shares the story behind the business |
| `BIV-GFX-010` | **Name card stays for the whole speaker turn (seconds).** When a speaker's turn starts (presenter: opening, questions, recap, sign-off; founder: an answer), their name card slides in after a short delay and the headline bar comes in with it. Both then stay fully on screen, still, until that speaker's turn ends. Back-to-back presenter scenes are one turn: no re-entry between them. Nothing fades out while someone is talking; the card leaves with the cut to the next speaker. Library clips and product footage have no card. | {"name_delay": 0.5, "ramp": 0.4} |
| `BIV-GFX-008` | **Pictures cut, never fade.** Scenes join with a clean picture cut. Only the sound gets a very short ramp at the join. | true |
| `BIV-GFX-011` | **Web address card for the whole closing remark.** The business's web address card comes in when the closing remark starts and stays still on screen until that line ends (no website, no card). | true |

## Sound

| Id | Rule | Value |
|---|---|---|
| `BIV-AUD-001` | **Broadcast loudness.** Finished videos are levelled to -16 LUFS with a -1.5 dB true-peak ceiling. | {"loudness_lufs": -16, "true_peak_db": -1.5, "lra": 11} |
| `BIV-AUD-002` | **Sound ramp at each cut (frames).** A very short sound ramp at every join, so cuts never click. | 5 |
| `BIV-AUD-003` | **Light version keeps the HD sound.** The Light download copies the HD file's sound instead of re-encoding it, so it cannot clip where HD does not. | true |

## Quality check before delivery

| Id | Rule | Value |
|---|---|---|
| `BIV-QC-001` | **Length matches the plan.** Each file's length must be within 5% (or 1 s, whichever is larger) of the planned length. | {"ratio": 0.05, "min_s": 1.0} |
| `BIV-QC-002` | **Has sound.** Every video file must have a sound track. | true |
| `BIV-QC-003` | **No clipping (dB).** The sound's true peak must stay below this level. | -0.1 |
| `BIV-QC-004` | **Sound and picture in step (seconds).** Sound and picture lengths may differ by at most this much. | 0.5 |
| `BIV-QC-005` | **All files rendered.** Every expected output file must exist before the video is ready. | true |
| `BIV-QC-006` | **Media checked before rendering.** Every file a scene needs must exist and be non-empty before any render time is spent. | true |

## Cost and paid vendors

| Id | Rule | Value |
|---|---|---|
| `BIV-COST-001` | **Price of a video (credits).** A video costs this many credits, whatever the vendors charge (CREDITS_PER_VIDEO setting). | 1 |
| `BIV-COST-002` | **Identical presenter clips are never bought twice.** A clip is keyed by words, presenter, voice and pronunciations, and reused within a video and across customers. | true |
| `BIV-COST-003` | **Presenter clips made at once.** At most this many presenter clips are generated in parallel. | 3 |
| `BIV-COST-004` | **Paid steps reserve budget first.** Every paid step holds budget before calling a vendor; no budget, or the pause switch, means no paid step. | true |
| `BIV-COST-005` | **Retries never pay twice.** A vendor job id is saved before waiting on it, so a retry resumes the same job instead of buying another. | true |

## Safety and editorial

| Id | Rule | Value |
|---|---|---|
| `BIV-SAFE-001` | **No real news network names.** Briefs, overlays and graphics may not name real news networks. | ["cnn", "bbc", "fox news", "sky news", "al jazeera", "msnbc", "reuters", "bloomberg tv", "nbc news", "abc news", "cbs news", "channels tv", "arise news", "dw news", "france 24", "cnbc"] |
| `BIV-SAFE-002` | **Moderation.** Briefs, scripts and founder transcripts are moderated: clearly disallowed content is blocked, borderline content waits for a person (MODERATION_HOLD_FOR_REVIEW). | true |

## Retired rules (kept as history)

| Id | Rule | Replaced by |
|---|---|---|
| `BIV-INT-006` | **Countdown before each answer (seconds).** A countdown runs before recording starts, so the founder is ready. | `BIV-INT-012` |
| `BIV-SCR-002` | **Presenter opening length (words).** The presenter's opening is cut to at most this many words: every second of presenter video is paid for. | `BIV-SCR-011` |
| `BIV-SCR-003` | **Fixed sign-off.** Every video ends with the same sign-off words, so the closing clip is made once per presenter and reused. | `BIV-SCR-014` |
| `BIV-SCR-005` | **Welcome before the first question.** The presenter welcomes the founder by first name before the first question, with a line chosen per video. | `BIV-SCR-011` |
| `BIV-SCR-006` | **Hand-over to the next question.** Between answers the presenter acknowledges the previous answer, using a line the writer grounded in that answer; if there is none, a short line from the standard pool. Then straight into the next question. | `BIV-SCR-012` |
| `BIV-SCR-007` | **Recap after the last answer (words).** After the last answer the presenter recaps the business in this many spoken words, before the sign-off. | `BIV-SCR-013` |
| `BIV-SCN-001` | **Scene order.** Brand intro, opening shot (if any), presenter opening, explanation (if any), then for each answer: presenter asks, founder answers, cutaway (if any); then the recap, the sign-off, the sign-off shot (if any) and the brand outro. | `BIV-SCN-010` |
| `BIV-GFX-006` | **Product web address at the sign-off (seconds).** The product's web address shows top right for this long, starting when the presenter signs off. | `BIV-GFX-011` |
| `BIV-GFX-007` | **Name card timing (seconds).** A speaker's name card slides in after a short delay and holds for a fixed time, then slides out, in every scene. | `BIV-GFX-010` |

## Changelog

- v1 (2026-11-02): rulebook created. Every business interview video rule recorded exactly as the code behaved on this date; no behaviour changed.
- v2 (2026-11-02): added BIV-GFX-009. The 'Featured' / 'AI-generated anchor' wording that was left after the on-screen labels were removed is gone from the render data, the quality check, social captions, the download and share pages and the presenter-only video's 'Featured startup' banner. Founder consent text is unchanged.
- v3 (2026-11-02): added BIV-GFX-010, retiring BIV-GFX-007. A speaker's name card and headline bar now come in once when their turn starts and stay still on screen until the turn ends (no 6-second fade-out, no re-entry between the presenter's own scenes).
- v4 (2026-11-02): one fixed running order for guided business interview videos (BIV-SCN-010): a set opening that names the founder and the business (BIV-SCR-011), a hand-over line from a pool of six between answers (BIV-SCR-012), a one-line closing remark with the web address said and shown on a card for the whole line (BIV-SCR-013, BIV-GFX-011), and a new sign-off (BIV-SCR-014). Retires BIV-SCR-002, BIV-SCR-003, BIV-SCR-005, BIV-SCR-006, BIV-SCR-007, BIV-GFX-006 and BIV-SCN-001. Videos written before v4 keep their old running order.
- v5 (2026-11-05): added BIV-INT-012, retiring BIV-INT-006. The recording of each answer now runs from the first second of the countdown (it used to start only when the countdown ended, so the first words could be lost); the countdown length is unchanged and the lead-in is trimmed off with the rest of the silence when the answer is cleaned up.
