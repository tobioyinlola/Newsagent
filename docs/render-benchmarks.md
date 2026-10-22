# Render benchmarks (Phase 0)

Measured with `pnpm bench [seconds] [noanchor]` in `services/renderer`, Remotion 4.0.250.

## Environment (important caveat)
Cloud sandbox container: 4 vCPU, 16 GB RAM, no GPU, Remotion's own headless-shell Chrome with software GL
(`swangle`). **This is not a Railway instance, so absolute numbers will differ.** Run `pnpm bench` on the real
renderer service on Railway staging and update this file before relying on any cost figure. Relative findings
(what is expensive) should carry over.

## Results (1920x1080 and 1080x1920, 30 fps, H.264 + AAC)

**Root cause of the slow first benchmark: the renderer forced `chromiumOptions.gl = "swangle"`.** Using Chrome's
default is 2-3x faster for this composition. Nothing else needed changing.

| Case | Video length | 16:9 render | 9:16 render | Peak RSS (node + chrome + ffmpeg) |
| --- | --- | --- | --- | --- |
| Graphics only, `swangle` (before) | 10 s | 79 s | 78 s | ~1.5 GB |
| With transparent VP9+alpha anchor, `swangle` (before) | 10 s | 130 s | 112 s | ~1.8 GB |
| Graphics only, default GL (after) | 10 s | 28.5 s | 27.6 s | ~1.5 GB |
| With transparent VP9+alpha anchor, default GL (after) | 10 s | 38.3 s | 34.9 s | ~2.0 GB |
| With transparent VP9+alpha anchor, default GL (after) | 30 s | 102 s | 98 s | ~2.0 GB |

Effective speed after the fix: **~8.8 fps with the anchor clip** (3.8x faster than before), ~10.5 fps graphics only.

## Against the 15 minute target (90 s video, two formats)
- 2,700 frames at ~8.8 fps is about **5.1 min per format, ~10.3 min for both formats on one 4 vCPU instance**,
  rendered one after the other. This meets the target for the render step, but it leaves only ~4.5 minutes for
  everything else (HeyGen generation time, upload/download, quality gate), and HeyGen latency is still unmeasured.
  Running the two formats on two instances would bring the render step to ~5 min.
- Memory is under 2 GB, so a renderer instance fits a normal Railway plan. CPU is the constraint.
- Caveat: these are sandbox numbers (4 vCPU, no GPU), not Railway. Re-run `pnpm bench 30` on the real service.

## Things tried that did not help (do not repeat)
- Pre-rendering the static studio layers (gradient, panels, channel bug, disclosures) once as an image: 38.3 s vs
  37.1 s without it. Removed to keep the composition simple.
- Higher `concurrency` (2 vs 4): no change. Lower JPEG quality: negligible.
- Hiding the ticker, banner and lower-third made no measurable difference: the cost was per-frame browser overhead,
  not our graphics.

## Remaining levers if Railway is slower than the sandbox
- Render the two formats on separate renderer instances (the API already treats them as separate outputs).
- Split one render into frame ranges across instances and concatenate.
- Anchor decoding (VP9 alpha through `OffthreadVideo`) costs about 30% (10.5 fps down to 8.8 fps); a pre-composite step
  in FFmpeg is possible if needed.
- Compute cost per video is still unknown; the code uses a placeholder of $0.05 per output. Replace it with the
  measured Railway cost.

## Remotion licence
Free tier in use (organisations of up to 3 people). A Company License ($0.01 per render, $100/month minimum) is
required at 4 or more.

## Renderer smoke test (`pnpm smoke`)
Starts the renderer service, renders a preview (0.5 scale), a 9:16 final and a thumbnail from a stand-in
transparent anchor served over HTTP, then calls `/analyze` on each. Verified: durations match the anchor, audio is
present, finals land at about -16 LUFS after normalisation, previews are left un-normalised by design, and a
960x540 preview is produced. The stand-in clip comes from a script:
Run `services/renderer/scripts/make-standin-anchor.sh` to create it.

## Correction: the stand-in anchor was invisible in the earlier benchmarks
The first stand-in clip was entirely transparent (`drawbox` does not write opaque alpha), so earlier renders decoded
the clip but never showed an anchor. Decode and compositing cost was still paid, so the timings above remain a fair
guide, but the clip is now built with a colour key (real alpha, ~43% opaque) and the composition was visually
checked: **Remotion's OffthreadVideo honours VP9 alpha and composites the anchor over the studio plate.** This
confirms the compositing half of Option B; whether HeyGen's matted output looks clean is still part of the spike.

## Interview merge render (`pnpm smoke:merge`)
10 s merged video (anchor, question, 4 s founder answer with PiP + lower-third, outro): 28 s for 16:9 PiP and 26 s
for 9:16 split on the 4 vCPU sandbox, about 10 fps. Founder portrait video is letterboxed in 16:9 (shown large,
not cropped). Takes processing (`/process`: join chunks, trim silence, denoise, loudnorm, flags) runs in 2-5 s for an
8 s take.
