# Architecture audit (initial state, 2026-10-24)

Scope: the whole repository at commit `d764b81` on `staging`. Written from reading the code and running its tests, not from
the original spec. "Verified" means exercised by a test or command in this session; "unverified" means not exercised against
the real vendor.

## 1. Stack and shape
Modular monolith in a monorepo.
- `backend/` FastAPI + SQLAlchemy (async) + Alembic (Postgres in prod, SQLite in tests), Pydantic v2. Pipeline steps in `app/pipeline/`
  run inline (dev/tests) or on Celery + Redis. Provider interfaces with mocks in `app/integrations/` (avatar, llm, tts,
  transcription, renderer, storage, email, billing, malware).
- `backend/renderer/` Node/TypeScript service: Remotion 4 compositions (`NewsStudio`, `InterviewMerge`), ffmpeg processing of founder
  takes, loudness normalisation, media analysis. Own bounded queue (`MAX_QUEUE`).
- `frontend/` React/Vite customer app. `admin/` separate operator back office. Storage: S3-compatible (R2) or local dev storage.
- CI: GitHub Actions (api, renderer, web, admin, e2e, e2e-admin, e2e-real).

## 2. What works (verified)
- Auth (password + emailed OTP), workspaces, invite-only sign-up, 1 h idle logout, rate limits.
- Brief → script (LLM) → approval → anchor generation → render → quality gate → delivery; credit ledger, spend guard that fails closed.
- Two interview modes: invite-link and live dashboard interview (camera required, chunked resumable uploads, transcription, snapshots).
- Remotion merge with PiP / split / answers-column layouts; presenter-clip library (operator uploaded) mixed into merges.
- Idempotent steps keyed by `(project, stage, input_hash)` in the `jobs` table; completed paid clips are reused (per-asset hash).
- Moderation, retention (raw takes deleted after 90 days), privacy export/delete, back office, audit log.
- 300 backend tests (SQLite and Postgres), 29 renderer tests, frontend/admin Playwright suites, real-stack e2e with real Remotion/ffmpeg.

## 3. Incomplete or not real
| Area | Reality |
|---|---|
| HeyGen | Adapter exists (`avatar/heygen.py`). Voices listing verified live earlier; video creation contract and pricing **unverified** (HeyGen account has no credit; developer docs unreachable from this sandbox, so webhook contract could not be read). Synthesia adapter is the failover and equally unverified. |
| Provider webhooks | Only billing has a webhook. HeyGen status is polled **inside** the worker task. |
| Scene plan | No persisted, validated scene-plan schema. Scenes are built ad hoc inside `merge_render` and only a props summary is kept. A video cannot be re-rendered reproducibly from a stored plan. |
| Scene types | Renderer supports anchor, question, answer (pip/split/column), presenter clip. The requested `anchor_explanation`, `anchor_analysis`, `product_broll`, `founder_fullscreen` do not exist. |
| B-roll | No product footage or AI B-roll in videos (brand-kit product images exist but are unused in renders). |
| Cancellation | None. |
| Progress | Only the coarse project state; no per-scene progress. |
| Concurrency caps | Renderer has a queue cap; no cap on concurrent paid avatar generations per vendor. |
| Observability | JSON logs with token redaction; no job/project/scene correlation fields; `/health` is a constant; no readiness or metrics. |
| Demo-mode honesty | With `USE_MOCKS=true` the UI looks identical to a real run. Production refuses to start in mock mode (good), but nothing tells a local/staging user the presenter is a stand-in. |

## 4. Critical bugs and reliability risks
- **P0, double payment on crash.** `HeyGenProvider.generate` submits, then polls inside one call and only returns the `video_id` at the end.
  If the worker dies mid-poll, the retry submits a **second paid video** for the same clip; the first is orphaned. The provider id is never persisted.
- **P0, no stale-work recovery for project steps.** A job left `running` is only taken over if the same step is enqueued again;
  nothing re-enqueues a project stuck in `rendering_anchor`/`merging` after a restart (inline queue loses tasks; Celery acks late but
  a lost message is not re-issued). `requeue_stuck` covers founder takes only.
- **P1, indiscriminate retries.** `_attempt_loop` retries every exception the same way: an invalid avatar id or auth error is retried
  `max_attempts` times with no jitter, and rate limits (`429`, `Retry-After`) are not honoured.
- **P1, no cancel**, so an owner who realises the brief is wrong keeps paying for the remaining clips.
- **P1, merge cannot validate assets before spending render time**: a missing or zero-length clip fails inside the renderer.
- P2, temp files: the renderer removes its temp dirs in `finally`, but dirs orphaned by a crash are never swept.

## 5. Security and isolation
Mostly sound: every customer route resolves the project through the principal's workspace; guest links are hashed tokens;
operator routes use `operator` and (for `/v1/admin*`) an Origin block; uploads are magic-byte checked and malware scanned (fail closed);
signed URLs are short lived; secrets stay server-side; production refuses to start with insecure config.
Gaps: no webhook endpoint exists for HeyGen yet (so none to verify); signed URL lifetimes for finished-video downloads are not
re-checked against project ownership at redemption (they are bearer links by design: documented); cross-tenant tests exist for
projects/interviews/billing but not for every asset route (added in this pass).

## 6. Scalability
API is stateless. Pipeline durable state is in Postgres. Bottlenecks: worker holds a task for the whole HeyGen generation (up to the
vendor timeout); one Celery queue for avatar and render work (a render backlog delays avatar steps); no vendor concurrency caps.

## 7. Recommended changes
- **P0** Persist provider requests (submit → store provider id → poll/resume) so a crash never double-pays; reconcile stuck projects.
- **P1** Classify errors (permanent vs retryable vs rate-limited), bounded exponential backoff with jitter and `Retry-After`;
  cancellation; persisted validated scene plan + asset pre-validation; per-scene progress API + UI; HeyGen webhook receiver
  (hint-only, signature verified, idempotent); readiness/metrics; correlation ids in logs; demo-mode banner.
- **P2** Vendor concurrency cap; sweep orphaned renderer temp dirs; more failure-path tests.
- **P3** Product B-roll scenes, `anchor_explanation`/`anchor_analysis` split generation, AI B-roll provider abstraction, scene editor UI.

## 8. Migration plan (no rewrites)
Additive migrations only (`provider_requests`, `projects.scene_plan`). Existing steps keep their names and idempotency keys. The
avatar provider interface gains `submit`/`poll`; `generate` stays as a compatibility wrapper for providers that cannot split.

## 9. Assumptions needing verification
1. HeyGen `POST /v3/videos` body, `GET /v3/videos/{id}` statuses, webhook event names and signature scheme (could not read the docs here).
2. HeyGen transparent WebM output quality and cost per minute.
3. That Celery with Redis `acks_late` is deployed with a visibility timeout longer than the vendor timeout.
4. Azure Blob Storage is **not** used: storage is S3-compatible (R2). Nothing to migrate.
5. The "supplied reference design" for the studio look was not in the repository; the Cover Founder brand guideline was used instead.

## 10. Status after the hardening pass (same day)
| Finding | Status |
|---|---|
| P0 double payment on crash | **Fixed**: `provider_requests` (vendor id stored first, hold committed with the row); tests simulate the crash and assert one submit and one hold |
| P0 stuck projects after restart | **Fixed**: `jobs.reconcile_projects` (hourly, also in `run_hourly`) |
| P1 indiscriminate retries | **Fixed**: classification, jitter, `Retry-After`, no retry for auth/invalid input |
| P1 no cancel | **Fixed** (`cancelled` state, API, UI); vendor jobs cannot be recalled and the docs say so |
| P1 plan not persisted / media not pre-validated | **Fixed**: `scene_plan`, hash, `GET /scene-plan`, asset check before render |
| P1 progress, readiness, metrics, correlation logs, demo honesty | **Done** |
| P1 HeyGen webhook | **Receiver built, off by default; contract unverified** |
| P2 vendor concurrency cap, temp sweep, Celery visibility timeout | **Done** |
| P3 explanation/analysis scenes, product B-roll (uploads), scene editor, clips in presenter-only video | **Done** (see video-generation-pipeline.md) |
| P3 AI-generated B-roll | **Abstraction, labelling, billing, UI done; no real provider exists** |
| HeyGen live verification | **Blocked**: account has no credit and the developer docs were unreachable from the sandbox. `tests/live/test_heygen_live.py` is ready |
