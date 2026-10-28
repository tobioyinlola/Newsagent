#!/bin/bash
# Runs the whole backend in one container: renderer (private, on localhost), Celery workers (one pool per lane), Celery scheduler, API.
# If any of them stops, the container stops, so Railway restarts everything and the problem is visible, not silent.
# Run exactly ONE replica of this service: two would mean two schedulers (reminders sent twice).
#
# Lanes (app/pipeline/queue.py) keep slow work from blocking quick work:
#   interactive  founder recordings being processed; a person is waiting on the page, so it must never queue behind a render
#   avatar       presenter clips: minutes of polling the avatar vendor
#   render       final and preview renders: minutes of waiting on the renderer
#   default      emails, reminders and the scheduled sweeps
# Size each with its env var. Each worker process is a Python process (~100 MB): keep the total within the container's memory.
# More capacity than one container gives? Run the lanes as separate services with the same image (celery -A ... worker -Q <lane>).
set -u

export RENDERER_URL="${RENDERER_URL:-http://127.0.0.1:4000}"

# First-time setup: create the operator's account (and a workspace holding BOOTSTRAP_OPERATOR_CREDITS) if it doesn't exist yet.
# Sign-in is invite-only and operators create the invites, so the first operator can't come from an invite. Safe to leave set:
# it does nothing when the account already exists. The operator then sets a password with "Forgot your password?".
if [ -n "${BOOTSTRAP_OPERATOR_EMAIL:-}" ]; then
  python -m app.cli bootstrap-operator "$BOOTSTRAP_OPERATOR_EMAIL" "${BOOTSTRAP_OPERATOR_CREDITS:-20}" || echo "operator bootstrap failed" >&2
fi

(cd renderer && PORT=4000 RENDER_CONCURRENCY="${RENDER_CONCURRENCY:-2}" RENDER_JOBS_CONCURRENCY="${RENDER_JOBS_CONCURRENCY:-1}" RENDER_LIGHT_CONCURRENCY="${RENDER_LIGHT_CONCURRENCY:-2}" exec node_modules/.bin/tsx src/server/index.ts) &
for spec in "interactive:${WORKER_INTERACTIVE:-3}" "avatar:${WORKER_AVATAR:-4}" "render:${WORKER_RENDER:-2}" "default:${WORKER_DEFAULT:-1}"; do
  lane="${spec%%:*}"; n="${spec##*:}"
  celery -A app.pipeline.celery_app worker -Q "$lane" -n "$lane@%h" --concurrency "$n" --loglevel INFO &
done
celery -A app.pipeline.celery_app beat --loglevel INFO --schedule /tmp/celerybeat-schedule &
uvicorn app.main:app --host 0.0.0.0 --port "${PORT:-8000}" --workers "${WEB_CONCURRENCY:-1}" --timeout-graceful-shutdown 25 &

wait -n
echo "a backend process exited; stopping the container so it restarts" >&2
kill 0
exit 1
