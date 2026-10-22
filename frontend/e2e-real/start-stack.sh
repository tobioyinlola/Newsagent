#!/usr/bin/env bash
# API for the real-renderer E2E: mocked HeyGen/Whisper/email, REAL renderer (ffmpeg + Remotion), shared local storage.
set -euo pipefail
cd "$(dirname "$0")/../../backend"
STORE=/tmp/newsagent-e2e-store
rm -rf "$STORE" e2e-real.db && mkdir -p "$STORE"
export DATABASE_URL="sqlite+aiosqlite:///./e2e-real.db" ENVIRONMENT=local USE_MOCKS=true QUEUE_BACKEND=inline \
  OPERATOR_EMAILS=ops@example.com APP_BASE_URL=http://localhost:5173 API_PUBLIC_URL=http://localhost:8000 \
  RENDERER_BACKEND=http RENDERER_URL=http://localhost:4000 RENDERER_SHARED_SECRET=e2e \
  LOCAL_STORAGE_DIR="$STORE" MOCK_ANCHOR_FILE="$(cd renderer && pwd)/public/bench-anchor.webm"
[ -f "$MOCK_ANCHOR_FILE" ] || bash renderer/scripts/make-standin-anchor.sh
uv run alembic upgrade head
uv run python -m app.cli bootstrap-operator ops@example.com 100
exec uv run uvicorn app.main:app --port 8000
