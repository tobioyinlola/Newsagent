#!/usr/bin/env bash
# Starts the real API against a throwaway SQLite DB with every vendor mocked. Used by Playwright.
set -euo pipefail
cd "$(dirname "$0")/../../../backend"
rm -f e2e-admin.db
export DATABASE_URL="sqlite+aiosqlite:///./e2e-admin.db" ENVIRONMENT=local USE_MOCKS=true QUEUE_BACKEND=inline \
  OPERATOR_EMAILS=ops@example.com APP_BASE_URL=http://localhost:5173 ADMIN_BASE_URL=http://localhost:5174
uv run alembic upgrade head
uv run python -m app.cli bootstrap-operator ops@example.com 100
exec uv run uvicorn app.main:app --port 8000
