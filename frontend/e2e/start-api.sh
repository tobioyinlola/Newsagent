#!/usr/bin/env bash
# Starts the real API against a throwaway SQLite DB with every vendor mocked. Used by Playwright.
set -euo pipefail
cd "$(dirname "$0")/../../backend"
rm -f e2e.db
export BANK_TRANSFER_REVIEW_ENABLED="${BANK_TRANSFER_REVIEW_ENABLED:-false}"
export OUTLET_PLANNER="${OUTLET_PLANNER:-on}" # the suggested-plans tests need it on; it is off unless set in production
export CORS_ORIGIN_REGEX="${CORS_ORIGIN_REGEX:-http://localhost:517[34]}" # the app runs on two ports in the browser tests
export DATABASE_URL="sqlite+aiosqlite:///./e2e.db" ENVIRONMENT=local USE_MOCKS=true QUEUE_BACKEND=inline \
  OPERATOR_EMAILS=ops@example.com APP_BASE_URL=http://localhost:5173 SIGNUP_PER_IP_PER_HOUR=1000 SIGNUP_VERIFY_PER_IP=1000
uv run alembic upgrade head
uv run python -m app.cli bootstrap-operator ops@example.com 100
uv run python ../frontend/e2e/seed-customer.py
exec uv run uvicorn app.main:app --port 8000
