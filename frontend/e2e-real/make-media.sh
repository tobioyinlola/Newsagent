#!/usr/bin/env bash
# Fake camera + microphone files for Chrome's --use-file-for-fake-*-capture flags (continuous "speech-like" sound, a bright picture).
set -euo pipefail
cd "$(dirname "$0")"
mkdir -p .media
[ -f .media/speech.wav ] || ffmpeg -y -loglevel error -f lavfi -i "sine=frequency=180:sample_rate=48000,tremolo=f=4:d=0.6" -af volume=0.35 -t 40 -ac 1 .media/speech.wav
[ -f .media/face.mjpeg ] || ffmpeg -y -loglevel error -f lavfi -i "testsrc2=s=640x480:r=30:d=40" -c:v mjpeg -q:v 6 .media/face.mjpeg
