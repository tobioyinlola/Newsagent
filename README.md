# Newsagent: AI newsroom video platform for startups

Turns a startup's text brief into a news-style video with an AI anchor, optionally merged with a recorded founder
interview. Status: **Phase 0** (see `docs/` for findings and open decisions).

```
apps/api          FastAPI API + Celery worker (one codebase)
apps/web          React + Vite app, typed client generated from the API's OpenAPI schema
services/renderer Node + Remotion render service
infra             docker-compose (postgres, redis, minio, mailpit)
docs              spike report, render benchmarks, decisions log
```

## Run locally
```bash
cp .env.example .env
docker compose -f infra/docker-compose.yml up -d          # postgres, redis, minio, mailpit
cd apps/api && uv sync && uv run alembic upgrade head
OPERATOR_EMAILS=you@example.com uv run uvicorn app.main:app --reload    # http://localhost:8000/docs
cd apps/web && pnpm install && pnpm dev                    # http://localhost:5173
cd services/renderer && pnpm install && RENDERER_SHARED_SECRET=dev-secret pnpm dev
```
`USE_MOCKS=true` (default locally) swaps every vendor (avatar, LLM, renderer, storage, email, transcription) for a mock,
so the full pipeline runs with no API keys. `ENVIRONMENT=local` accepts `Authorization: Bearer dev:<email>`;
other environments verify a real JWT (`AUTH_ISSUER`, `AUTH_AUDIENCE`). Signup is invite-only: an operator
(`OPERATOR_EMAILS`) calls `POST /v1/admin/invites`, then the invitee calls `POST /v1/auth/redeem`.
Operators also set budgets: `PUT /v1/admin/vendor-budgets` (the spend guard refuses any vendor without a budget).

## Test
```bash
cd apps/api && uv run ruff check . && uv run mypy app && uv run pytest      # 227 tests; add TEST_DATABASE_URL=postgresql+asyncpg://... to run on Postgres
cd apps/web && pnpm lint && pnpm build && pnpm test      # unit
cd apps/web && pnpm e2e                                    # browser journey; needs CHROMIUM_PATH locally, uses mocked vendors
cd services/renderer && pnpm build && pnpm test
cd services/renderer && pnpm smoke                                         # real render + analyze (first run scripts/make-standin-anchor.sh)
cd services/renderer && pnpm bench 10                                      # render benchmark
```
After changing API routes or schemas: `uv run python scripts/export_openapi.py && (cd apps/web && pnpm gen:api)`;
CI fails if the committed client is stale.

## API overview (v1, all under `/v1`)
Auth `POST /auth/redeem`, `GET /me` | Brand `GET|PUT /brand-kit`, `POST /brand-kit/import`, `POST /brand-kit/logo-upload`,
`GET /voices` | Projects `POST|GET /projects`, `/projects/{id}/script/{generate,approve}`, `PUT /script`, `POST /retry` |
Delivery `GET /projects/{id}/{downloads,captions,costs,events}` (events is SSE; use fetch streaming, not EventSource),
`POST|DELETE /projects/{id}/share`, public `GET /share/{token}` | Admin `POST /admin/invites`,
`PATCH /admin/workspaces/{id}`, `GET|PUT /admin/vendor-budgets`, `GET /admin/workspaces`. Uploads: `POST /brand-kit/uploads` then `/uploads/confirm`.
First operator: `cd apps/api && uv run python -m app.cli bootstrap-operator you@example.com 100`. Full contract: `/docs`.

## Founder interview (Phase 2)
Owner ticks "Include a founder interview" when approving the script. After the anchor and per-question clips render, the
project waits for the founder: the owner creates a private link (`/i/<token>`, 14 days, revocable, optionally emailed with
reminders at days 2/5/9). The founder records in the browser; chunks upload straight to storage and resume after a drop.
Each kept answer is cleaned up (ffmpeg), transcribed and quality-checked. After submit the owner reviews, picks PiP or
split layout, trims/reorders/drops answers, and makes the final video. Raw recordings are deleted 90 days after the video
is finished unless the owner keeps them. See `docs/gate-2.md` for what has and hasn't been verified.

Local real-stack run (real ffmpeg + Remotion, mocked HeyGen/Whisper/email):
`cd apps/web && E2E_QUESTIONS=5 pnpm e2e:real`. Periodic jobs: `celery -A app.pipeline.celery_app beat` (one instance).

## Operating it (Phase 3)
- **Operator console** (`/admin`): queue and jobs, review queue, costs and margin, credit packs, failover and an emergency
  pause, audit log. **Credits** page for customers: balance, test checkout, usage statements, history. **Your data**: export or delete.
- Billing: append-only credit ledger; payments via a provider-neutral signed webhook (a real provider adapter is still to be chosen).
- Moderation holds borderline briefs, scripts and founder answers for a human; blocks clearly disallowed content.
- `docs/runbook.md` (incidents), `docs/security-review.md`, `docs/gate-3.md` (what is and isn't done), `docs/render-benchmarks.md` (load test).
- Backups: `python scripts/backup.py --upload`; prove one restores: `python scripts/restore_test.py <file.dump>`.
- Renderer load test: `cd services/renderer && pnpm loadtest 6 5 2`.
- In staging/production the API **refuses to start** with an insecure configuration and lists every problem.

## Pipeline
Order: anchor render, then a half-resolution preview, then the final 16:9 + 9:16 renders, thumbnail and SRT.
`advance(project_id)` inspects state and enqueues the next idempotent step (`pipeline/`). Steps look up `jobs` by
`(project, stage, input_hash)` and reuse a finished result, so re-runs never double-charge. Every paid step calls
`SpendGuard.reserve` then `settle` (`services/spend_guard.py`); refusal moves the project to `limit_reached`.
Local `QUEUE_BACKEND=inline` runs steps in-process; `celery` uses Redis.

## Deploy (Railway)
Services: `web`, `api`, `worker`, `scheduler` (exactly one), `renderer` (private network only), Postgres, Redis.
`apps/api/railway.toml` runs `alembic upgrade head` as the pre-deploy step. Worker start command:
`celery -A app.pipeline.celery_app worker --concurrency 2`. Set the variables from `.env.example` per environment;
staging must use separate keys, database and low spend caps. **Staging is not deployed yet.**

## Remotion licence
Free for individuals and organisations of up to 3 people total. At 4+ a Company License is required ($0.01 per
render, $100/month minimum). Confirm team size before launch.
