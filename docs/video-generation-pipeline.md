# Video generation pipeline

How a video is made, what is persisted at each step, and what happens when something goes wrong. This describes the code as it
is. "Mock" means the provider is a stand-in used for local runs and tests; nothing here claims a mock result is real.

## 1. States
`draft → script_ready → script_approved → (interviewing) → rendering_anchor → anchor_ready → (awaiting_founder → processing_founder) →
merging → final_ready`, plus `failed`, `limit_reached` and `cancelled` (all three resume with `POST /projects/{id}/retry`).
`app/services/state_machine.py` is the only place transitions are allowed; every transition stamps `state_changed_at`.

Two interview modes feed the same pipeline. *Live*: the owner is interviewed on the dashboard **before** anything paid runs;
pressing "Make my video" starts the presenter and the merge. *Invite*: the presenter and question clips are made first, then a founder
records from a private link. In both, the interview is separate from presenter generation: the founder's footage is their own
recording and is never replaced by synthetic narration.

## 2. Steps (idempotent, in `app/pipeline/`)
| Step | Does | Paid vendor | Persisted |
|---|---|---|---|
| `anchor_render` | AI presenter reads the script (opening + closing when an interview is included) | avatar (HeyGen; Synthesia as failover) | `assets`, `provider_requests`, `jobs` |
| `question_clips` | One presenter clip per interview question | avatar | `assets` per question |
| `process_take` | ffmpeg clean-up, transcription, quality flags for a founder answer | transcription | `takes` |
| `merge_render` | Builds the **scene plan**, validates its media, renders the interview video | renderer | `projects.scene_plan`, `assets`, `jobs` |
| `final_render` / `preview_render` | Presenter-only video | renderer | `assets` |

`advance(project_id)` looks at the state and enqueues the next step; it is safe to call repeatedly. Each step's idempotency key is
`(project, stage, input_hash)` in `jobs`, so the same inputs never run twice, and finished clips are reused per asset hash.

## 3. A paid presenter clip, in order (no double payment)
1. `provider_requests.begin`: in **one commit**, hold the customer's credits (spend guard) and write the request row
   (`project, provider, slot=storage key, request_hash`). A refused hold changes nothing.
2. Concurrency cap: if the vendor already has `max_concurrency` jobs in flight, raise `busy` (retried later).
3. `avatar.submit` → the vendor's id is written to the row **immediately**. From here a crash, a retry, a duplicate task or a webhook all find
   the same row and only poll that id.
4. Poll until `completed` / `failed` / the step's time budget. Budget exhausted ⇒ `ProviderPending`: nothing failed; the hold stays on
   the row and the next attempt resumes polling.
5. Completed ⇒ download into our own storage, settle the hold against the actual cost, clear the hold, save the asset (one commit).
6. Vendor says `failed` ⇒ release the hold; the next attempt may submit a fresh job. Any other error while a job is in flight keeps the hold.

Residual risk: a crash in the instant between the vendor accepting the job and our write of its id can still buy a second video.
The mitigation would be a vendor-side idempotency key; HeyGen's support for one is unverified. The window is a single database write.

## 4. Errors and retries (`app/integrations/errors.py`, `app/pipeline/runner.py`)
Every failure is classified: `invalid_input` and `auth` are permanent (fail fast, no retry); `rate_limited` (honours `Retry-After`, capped
at 120 s), `temporary`, `timeout`, `busy`, `unknown` retry up to the vendor policy's `max_attempts` with exponential backoff and ±50 %
jitter. Auth failures also email the operators. The job records `[category] message` and `failure_category`; the owner sees a plain
sentence and, for missing media, which scene is affected. `limit_reached` (credits, caps, vendor budget, pause switch) is never retried.

## 5. Cancel, retry, recovery
- **Cancel** (`POST /projects/{id}/cancel`): allowed while work is in flight or waiting on a person. The runner stops before the next
  attempt; the polling loop notices within one poll interval. A vendor job already running **cannot be recalled** (no vendor cancel is
  relied on): it may still be charged, and its id stays recorded so **retry** reuses the video if it finishes. Clips already made are kept.
- **Retry** resumes from the state the project was in; finished clips are not regenerated or paid for again.
- **Restart safety**: job and request rows are in Postgres. `jobs.reconcile_projects` (hourly) re-drives any project that should be moving
  but has had no state change for 20 minutes and has no fresh running job. A lost queue message therefore costs at most one hour.
- Celery uses `acks_late` with a 3 h visibility timeout (longer than the slowest step).

## 6. The scene plan (`app/services/scene_plan.py`)
`merge_render` builds a `ScenePlan` from the approved script, the answers, the question clips, the presenter clips and the owner's
choices, then:
1. validates it (contiguous order, unique ids, durations add up, every scene has the media it needs, only scene types the renderer can
   draw: `product_broll` is refused until it exists);
2. checks every referenced file exists and is non-empty **before** any render time is spent (a missing founder clip fails with
   "scene 4 (founder column): take video is missing");
3. stores it on the project (`scene_plan`, `scene_plan_hash`; asset keys only, never signed URLs) and exposes it at
   `GET /projects/{id}/scene-plan`;
4. mints short-lived signed URLs and hands the renderer its scene list.
Scenes carry `provenance` (`owner_script`, `founder_statement`, `presenter_footage`), and claim-like sentences in a founder's transcript are
listed in `unconfirmed_claims` rather than asserted as fact. Rebuilding is deterministic for unchanged inputs, so the hash identifies
a video; changing the answers, plan or clip library changes the hash and the merge's input hash, which re-renders.

Scene types produced today: `anchor_intro`, `anchor_question`, `founder_picture_in_picture`, `founder_split`, `founder_column`,
`founder_fullscreen`, `news_closing`, `presenter_clip`. Declared but not generated yet: `anchor_explanation`, `anchor_analysis`
(they would need extra presenter clips) and `product_broll` (not drawable).

## 7. Output checks
The renderer normalises loudness and the **quality gate** (`steps.quality_gate`) measures each rendered file: length against the plan,
audio present, no clipping, audio/video length drift, mandatory labels present, no banned names. A video is `final_ready` only after the gate
passes; a failing gate fails the project (not retryable without a change).

## 8. Progress and operations
- `GET /projects/{id}/progress`: each piece with `done | working | waiting | pending | failed | paused | cancelled`, percent, retry/cancel flags.
- `GET /health` (liveness), `GET /health/ready` (database required; storage and renderer reported), `GET /v1/admin/pipeline-metrics`
  (projects by state, jobs and failure categories in 24 h, average step time, vendor jobs in flight, possibly stuck projects).
- Logs are JSON lines carrying `project_id, job_id, stage, provider, vendor_id, slot, attempt, category, duration_s`; signed tokens are redacted.
- `POST /v1/webhooks/heygen`: disabled until `HEYGEN_WEBHOOK_SECRET` is set; verifies an HMAC of the raw body, ignores repeats
  (`webhook_events`) and only **wakes** the pipeline; results are always read back from the vendor API. The signature scheme and payload keys are
  unverified assumptions (see below).
