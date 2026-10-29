# Newsagent: AI newsroom video platform for startups

Turns a startup's text brief into a news-style video with an AI anchor, optionally merged with a recorded founder
interview. Status: **Phase 0** (see `docs/` for findings and open decisions).

```
backend            FastAPI API + Celery worker (one codebase)
backend/renderer   Node + Remotion render service (called by the API over HTTP)
frontend           React + Vite app, typed client generated from the API's OpenAPI schema
infra              docker-compose (postgres, redis, minio, mailpit)
docs              spike report, render benchmarks, decisions log
```

## Run locally
```bash
cp .env.example .env
docker compose -f infra/docker-compose.yml up -d          # postgres, redis, minio, mailpit
cd backend && uv sync && uv run alembic upgrade head
OPERATOR_EMAILS=you@example.com uv run uvicorn app.main:app --reload    # http://localhost:8000/docs
cd frontend && pnpm install && pnpm dev                    # customers: http://localhost:5173
# the operator back office is part of the same app: http://localhost:5173/admin
cd backend/renderer && pnpm install && RENDERER_SHARED_SECRET=dev-secret pnpm dev
```
`USE_MOCKS=true` (default locally) swaps every vendor (avatar, LLM, renderer, storage, email, transcription) for a mock,
so the full pipeline runs with no API keys. `ENVIRONMENT=local` accepts `Authorization: Bearer dev:<email>`;
real sign-in is in-house: email + password (scrypt), a 6-digit code emailed at sign-up to prove the address
(the local mock mailbox is readable at `GET /v1/dev/last-email?to=`), forgot-password by emailed code, and revocable
server-side sessions that end after **1 hour idle**. Operators also confirm each sign-in with an emailed code. Sign-up is
invite-only: an operator (`OPERATOR_EMAILS`) calls `POST /v1/admin/invites`; the invitee opens the link, chooses a password
(`/auth/signup/start`) and enters the code (`/auth/signup/verify`). A new operator has no password: use *Forgot password*.
Operators also set budgets: `PUT /v1/admin/vendor-budgets` (the spend guard refuses any vendor without a budget).

## Test
```bash
cd backend && uv run ruff check . && uv run mypy app && uv run pytest      # 350+ tests; add TEST_DATABASE_URL=postgresql+asyncpg://... to run on Postgres
cd frontend && pnpm lint && pnpm build && pnpm test      # unit
cd frontend && pnpm e2e                                    # browser journey; needs CHROMIUM_PATH locally, uses mocked vendors
cd backend/renderer && pnpm build && pnpm test
cd backend/renderer && pnpm smoke                                         # real render + analyze (first run scripts/make-standin-anchor.sh)
cd backend/renderer && pnpm bench 10                                      # render benchmark
```
After changing API routes or schemas: `uv run python scripts/export_openapi.py && (cd frontend && pnpm gen:api)`;
CI fails if the committed client is stale.

## API overview (v1, all under `/v1`)
Auth `/auth/signup/*`, `/auth/login`, `/auth/password/*`, `/auth/sessions`, `/auth/logout`, `GET /me` | Brand `GET|PUT /brand-kit`, `POST /brand-kit/import`, `POST /brand-kit/logo-upload`,
`GET /voices` | Projects `POST|GET /projects`, `/projects/{id}/script/{generate,approve}`, `PUT /script`, `POST /retry` |
Delivery `GET /projects/{id}/{downloads,captions,costs,events}` (events is SSE; use fetch streaming, not EventSource),
`POST|DELETE /projects/{id}/share`, public `GET /share/{token}` | Admin `POST /admin/invites`,
`PATCH /admin/workspaces/{id}`, `GET|PUT /admin/vendor-budgets`, `GET /admin/workspaces`. Uploads: `POST /brand-kit/uploads` then `/uploads/confirm`.
First operator: `cd backend && uv run python -m app.cli bootstrap-operator you@example.com 100`. Full contract: `/docs`.

## AI interview on the dashboard (live)
When a founder pastes their news, the system reads it and shows what it understood (company, announcement, who it is for).
The dashboard then offers **an AI interview** (default) or the invite-link interview below. In the live interview the AI
greets the founder by first name, asks 4 questions (the script's questions; 4 by default) with a synthetic voice, and the
founder answers on camera. The camera is required (no camera, no interview). The whole interview is capped at 5 minutes;
each answer gets a time window computed from the number of questions. A snapshot is taken for every answer. The founder
reviews, then **Make my video**: the AI presenter introduces the company and the recorded answers are merged in with a
column beside the founder's video that shows the question and what they said, line by line, in sync (layout `column`;
`pip` and `split` remain available). Nothing paid runs until the founder proceeds.
- Voice: `TTS_API_KEY` (+ `TTS_API_URL`, `TTS_MODEL`, `TTS_VOICE`) for an OpenAI-compatible `/audio/speech`; needs a `tts`
  vendor budget. Without it, the browser's own voice speaks and the interview still works.
- The questions are generated when the script is written (not adaptive follow-ups).
- Real-stack check: `cd frontend && pnpm e2e:real` (invite flow plus `live-interview.spec.ts`).

### Presenter clips (real presenter footage)
Operators upload TV-style presenter clips in the back office (**Presenter clips**, `frontend/src/admin/`): an *opening shot* (3-20 s), *cutaways*
(2-10 s) and a *sign-off* (3-20 s). MP4, MOV or WebM, landscape, 720p or more, up to 150 MB, sound kept. Uploads are checked
(real file type, malware scan, real length and size read by the renderer) and the operator confirms they own or license the
footage and the presenter agreed. Interview videos then open with an active opening shot, cut away to the presenter between
answers, and close with a sign-off; clips are chosen per project from what is switched on. Clips are not used in the
presenter-only video made when the founder skips the interview. The "AI-generated anchor" label stays on screen throughout.
The stand-in presenter used in local runs is an illustrated anchor (`AnchorFigure.tsx`); `scripts/make-standin-anchor.sh` renders it.

## Founder interview by invite link (Phase 2)
Owner ticks "Include a founder interview" when approving the script. After the anchor and per-question clips render, the
project waits for the founder: the owner creates a private link (`/i/<token>`, 14 days, revocable, optionally emailed with
reminders at days 2/5/9). The founder records in the browser; chunks upload straight to storage and resume after a drop.
Each kept answer is cleaned up (ffmpeg), transcribed and quality-checked. After submit the owner reviews, picks PiP or
split layout, trims/reorders/drops answers, and makes the final video. Raw recordings are deleted 90 days after the video
is finished unless the owner keeps them. See `docs/gate-2.md` for what has and hasn't been verified.

Local real-stack run (real ffmpeg + Remotion, mocked HeyGen/Whisper/email):
`cd frontend && E2E_QUESTIONS=5 pnpm e2e:real`. Periodic jobs: `celery -A app.pipeline.celery_app beat` (one instance).

## Operating it (Phase 3)
- **Back office** (`frontend/src/admin/`, served by the customer app's site under `/admin`, set `ADMIN_BASE_URL`): business overview, customers, payments and
  revenue, queue and jobs, review queue, costs and margin, credits, failover and an emergency pause, audit log. It is not
  part of the customer app, and the API refuses `/v1/admin*` calls from the customer app's origin. Operators sign in with
  password plus emailed code. **Credits** page for customers: balance, test checkout, usage statements, history. **Your data**: export or delete.
- Billing: append-only credit ledger; payments via a provider-neutral signed webhook (a real provider adapter is still to be chosen).
- Moderation holds borderline briefs, scripts and founder answers for a human; blocks clearly disallowed content.
- `docs/runbook.md` (incidents), `docs/security-review.md`, `docs/gate-3.md` (what is and isn't done), `docs/render-benchmarks.md` (load test).
- Backups: `python scripts/backup.py --upload`; prove one restores: `python scripts/restore_test.py <file.dump>`.
- Renderer load test: `cd backend/renderer && pnpm loadtest 6 5 2`.
- In staging/production the API **refuses to start** with an insecure configuration and lists every problem.

## Reliability and operations
Paid presenter clips are crash-safe (`provider_requests`: the vendor's job id is stored before waiting, so a retry polls the same job instead of
buying another). Failures are classified (auth / invalid input fail fast; rate limits and outages back off with jitter). Owners can cancel
and retry (`/projects/{id}/cancel`, `/retry`), see per-piece progress (`/projects/{id}/progress`) and the saved scene plan
(`/projects/{id}/scene-plan`). Operators get `/health/ready`, `/v1/admin/pipeline-metrics` and an hourly reconciliation of stuck projects.
Finished interview videos can be edited scene by scene (new presenter words, per-answer layout, trims, product footage) and re-rendered, paying only for what changed.
Full detail: `docs/video-generation-pipeline.md`, `docs/target-architecture.md`, `docs/architecture-audit.md`.

Real HeyGen check (spends credit, off by default): `HEYGEN_LIVE=1 HEYGEN_API_KEY=... HEYGEN_TEST_AVATAR_ID=... pytest backend/tests/live -q -s`.

## Pipeline
Order: anchor render, then a half-resolution preview, then the final 16:9 + 9:16 renders, thumbnail and SRT.
`advance(project_id)` inspects state and enqueues the next idempotent step (`pipeline/`). Steps look up `jobs` by
`(project, stage, input_hash)` and reuse a finished result, so re-runs never double-charge. Every paid step calls
`SpendGuard.reserve` then `settle` (`services/spend_guard.py`); refusal moves the project to `limit_reached`.
Local `QUEUE_BACKEND=inline` runs steps in-process; `celery` uses Redis.

## Deploy (Railway)
Services: `web`, `api`, `worker`, `scheduler` (exactly one), `renderer` (private network only), Postgres, Redis.
`backend/railway.toml` runs `alembic upgrade head` as the pre-deploy step. Worker start command:
`celery -A app.pipeline.celery_app worker --concurrency 2`. Set the variables from `.env.example` per environment;
staging must use separate keys, database and low spend caps. **Staging is not deployed yet.**

## Remotion licence
Free for individuals and organisations of up to 3 people total. At 4+ a Company License is required ($0.01 per
render, $100/month minimum). Confirm team size before launch.
