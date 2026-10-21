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
cd apps/api && uv run ruff check . && uv run mypy app && uv run pytest      # 21 tests
cd apps/web && pnpm lint && pnpm build && pnpm test
cd services/renderer && pnpm build && pnpm test
cd services/renderer && pnpm bench 10                                      # render benchmark
```
After changing API routes or schemas: `uv run python scripts/export_openapi.py && (cd apps/web && pnpm gen:api)`;
CI fails if the committed client is stale.

## Pipeline
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
