#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../../backend/renderer"
mkdir -p /tmp/newsagent-e2e-store
# Playwright's Chrome is not Remotion's, so CHROMIUM_PATH is never inherited. Set RENDERER_CHROMIUM_PATH to a
# headless shell to use instead of Remotion's own download (e.g. in a sandbox that can't reach it).
unset CHROMIUM_PATH
[ -n "${RENDERER_CHROMIUM_PATH:-}" ] && export CHROMIUM_PATH="$RENDERER_CHROMIUM_PATH"
export RENDERER_SHARED_SECRET=e2e LOCAL_OUTPUT_DIR=/tmp/newsagent-e2e-store PORT=4000 RENDER_JOBS_CONCURRENCY=1
[ -f public/bench-anchor.webm ] || bash scripts/make-standin-anchor.sh
exec npx tsx src/server/index.ts
