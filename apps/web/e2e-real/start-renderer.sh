#!/usr/bin/env bash
set -euo pipefail
cd "$(dirname "$0")/../../../services/renderer"
mkdir -p /tmp/newsagent-e2e-store
unset CHROMIUM_PATH  # Playwright's Chrome is not Remotion's; let Remotion use its own headless shell
export RENDERER_SHARED_SECRET=e2e LOCAL_OUTPUT_DIR=/tmp/newsagent-e2e-store PORT=4000 RENDER_JOBS_CONCURRENCY=1
[ -f public/bench-anchor.webm ] || bash scripts/make-standin-anchor.sh
exec npx tsx src/server/index.ts
