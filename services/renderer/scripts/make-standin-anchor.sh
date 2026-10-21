#!/usr/bin/env bash
# Creates public/bench-anchor.webm: a 30 s transparent VP9 clip with a tone, standing in for a HeyGen anchor.
set -euo pipefail
cd "$(dirname "$0")/.."
mkdir -p public
ffmpeg -y -loglevel error -f lavfi -i "color=c=black@0.0:s=640x720:r=30:d=30,format=yuva420p,drawbox=x=120:y=300:w=400:h=420:color=0x1c2b4a@1:t=fill,drawbox=x=240:y=120:w=160:h=190:color=0xd9c2a7@1:t=fill,drawbox=x='300+20*sin(t*8)':y=250:w=40:h=12:color=0x7a2e2e@1:t=fill" \
  -f lavfi -i "sine=frequency=220:d=30" -c:v libvpx-vp9 -pix_fmt yuva420p -b:v 1M -c:a libopus -shortest public/bench-anchor.webm
