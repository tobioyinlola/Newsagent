#!/usr/bin/env bash
# Creates public/bench-anchor.webm: the illustrated stand-in presenter as a 30 s VP9 clip WITH A REAL ALPHA CHANNEL and a
# tone, standing in for a HeyGen transparent anchor. Needs CHROMIUM_PATH (or Remotion's own browser download).
set -euo pipefail
cd "$(dirname "$0")/.."
pnpm exec tsx src/make-standin-anchor.ts
