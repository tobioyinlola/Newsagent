#!/bin/bash
# Runs the whole backend in one container: renderer (private, on localhost), Celery worker, Celery scheduler, API.
# If any of them stops, the container stops, so Railway restarts everything and the problem is visible, not silent.
# Run exactly ONE replica of this service: two would mean two schedulers (reminders sent twice).
set -u

export RENDERER_URL="${RENDERER_URL:-http://127.0.0.1:4000}"

(cd renderer && PORT=4000 RENDER_JOBS_CONCURRENCY="${RENDER_JOBS_CONCURRENCY:-1}" exec node_modules/.bin/tsx src/server/index.ts) &
celery -A app.pipeline.celery_app worker --concurrency "${WORKER_CONCURRENCY:-2}" --loglevel INFO &
celery -A app.pipeline.celery_app beat --loglevel INFO --schedule /tmp/celerybeat-schedule &
uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" &

wait -n
echo "a backend process exited; stopping the container so it restarts" >&2
kill 0
exit 1
