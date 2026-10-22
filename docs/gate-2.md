# Gate 2: founder interview

Gate criterion: *a 5-question interview completes on a mid-range phone over 4G, including a resumed upload after a
dropped connection.*

## What was verified (automated, repeatable)
`cd frontend && E2E_QUESTIONS=5 pnpm e2e:real` (about 6 minutes, needs ffmpeg and a Chromium; first run downloads
Remotion's headless shell). One real browser test drives the whole path against the real stack:

| Step | How it is exercised |
| --- | --- |
| Phone | Chromium with the **Pixel 5** device profile (viewport, touch, mobile UA) |
| 4G | CDP network emulation: 4 Mbps down, 1.5 Mbps up, 60 ms latency, for the whole session |
| Camera / mic | Chromium fake devices fed from a video file and a continuous tone, through the real `getUserMedia` + `MediaRecorder` |
| Page weight | 307 KB (uncompressed, production build) before the camera starts; limit was 1 MB. About 95 KB gzipped |
| Dropped connection | `setOffline(true)` in the middle of the **3rd** answer, still offline when the founder stops. The page shows "No connection... safe on this device", Keep waits, then reconnecting resumes: only missing chunks are sent |
| Processing | Real ffmpeg: join chunks, trim silence, denoise, loudnorm, quality flags (`frontend` e2e + `backend/renderer` tests) |
| Merge | Real Remotion render (anchor question, founder answer, PiP/split, name lower-third, outro), both formats + thumbnail |
| Result | Downloaded and probed with ffprobe: 1920x1080, has audio, duration matches (46.5 s for 5 questions) |
| Quality gate | Passed (length, audio, clipping, A/V drift, disclosures) |

The same run was green with 2 questions (about 3 minutes). Backend behaviour (resume by chunk index, retries, flags,
attempt caps, token scoping, reminders, retention, spend limits) has 50+ unit/API tests.

## What was NOT verified (be honest about this before calling the gate closed)
- **A real phone.** Emulation reproduces viewport, UA and network, not a mid-range device's CPU, thermal limits,
  camera pipeline or memory. Please run the flow once on a real Android phone (Chrome) and once on an iPhone.
- **iOS Safari.** The recorder falls back to `video/mp4` (fragmented MP4) when WebM is unavailable and the server accepts
  `.mp4` takes, but byte-concatenating Safari's chunks and processing them has only been reasoned about, not run.
  This is the most likely place for a surprise. Test it on a real iPhone before pilots with iOS founders.
- **Real network behaviour.** CDP throttling is smoother than a real 4G connection (handovers, packet loss, captive
  portals). Uploads retry with backoff and resume by chunk, but real-world flapping is untested.
- **Real HeyGen question clips and real Whisper.** Avatar and transcription are mocked in every test; the Whisper adapter
  is contract-tested against a fake OpenAI-compatible server only.
- **Real speech.** The fake microphone plays a tone, so silence-trim and `no_speech` thresholds are tuned on synthetic
  audio. Expect to adjust them (`backend/renderer/src/process.ts`) after hearing real founder recordings.
- **Firefox / desktop Safari**, and an interview with a founder who denies camera access (the audio-only + photo path is
  API-tested but not browser-tested).

## Known limitations
- Founder portrait video is letterboxed in the 16:9 PiP layout (shown large, not cropped). The split layout crops.
- Captions are built from Whisper's SRT and shifted onto the timeline; anchor lines are timed by word count.
- A take that fails processing never changes the project's state; the founder retries or re-records.
