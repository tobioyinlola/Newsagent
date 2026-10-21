# Render benchmarks (Phase 0)

Measured with `pnpm bench [seconds] [noanchor]` in `services/renderer`, Remotion 4.0.250.

## Environment (important caveat)
Cloud sandbox container: 4 vCPU, 16 GB RAM, no GPU, Remotion's own headless-shell Chrome with software GL
(`swangle`). **This is not a Railway instance, so absolute numbers will differ.** Run `pnpm bench` on the real
renderer service on Railway staging and update this file before relying on any cost figure. Relative findings
(what is expensive) should carry over.

## Results (1920x1080 and 1080x1920, 30 fps, H.264 + AAC)
| Case | Video length | 16:9 render | 9:16 render | Peak RSS (node + chrome + ffmpeg) |
| --- | --- | --- | --- | --- |
| Graphics only (placeholder anchor) | 10 s | 79 s | 78 s | ~1.5 GB |
| With transparent VP9+alpha anchor clip | 10 s | 130 s | 112 s | ~1.8 GB |
| Graphics only, concurrency 2 vs 4 | 5 s | 40.6 s vs 39.2 s | n/a | 1.4 / 1.8 GB |
| Trivial 1080p frame (floor: solid colour + frame number) | 5 s | 12.2 s | n/a | n/a |

Effective speed: about **3.8 fps** for graphics only, **~2.3 fps** with the anchor clip, versus ~12 fps for a
trivial frame on the same box. Raising concurrency from 2 to 4 changed nothing (CPU-bound), and lowering JPEG
quality changed little.

## What this means for the targets
- Target: script approved to final render under 15 minutes for a 90 s video (2,700 frames, two formats).
- Extrapolating linearly: ~12 min per format graphics-only, ~20 min per format with the anchor, i.e. roughly
  **25-40 minutes for both formats on one 4 vCPU instance. The 15 minute target is NOT met as built.**
- Memory is modest (< 2 GB), so a renderer instance fits in a normal Railway plan. CPU is the constraint.

## Where the time goes (observed, not fully profiled)
1. Per-frame Chrome screenshot cost in software GL (the floor test alone is 12 fps).
2. Our composition costs ~3x the floor: full-frame gradient, skewed translucent panels and a wide animated ticker are
   repainted every frame.
3. VP9-with-alpha decoding through `OffthreadVideo` adds ~0.17 s/frame.

## Options to get under 15 minutes (pick in Gate 0)
- Optimise the composition: pre-render the static studio plate to a single image/video once per accent, keep only
  the ticker, banner and lower-third dynamic. Likely 2-3x.
- Render the two formats in parallel on two renderer instances (the API already treats them as separate outputs).
- Split one render into frame ranges across instances and concatenate (Remotion supports frame ranges).
- Remotion Lambda or similar elastic rendering (adds a vendor and licence cost; not in the spec).
- Pre-composite anchor + plate with FFmpeg instead of rendering the anchor through Chrome.
- Cost: a render is billed on instance-minutes. At ~15 min x 2 formats the compute cost per video is not yet
  known; I used a placeholder `$0.05` per output in the code. Replace it with measured Railway cost.

## Remotion licence
Free for individuals and organisations of up to 3 people in total headcount. At 4 or more a Company License is
required ($0.01 per render, $100 monthly minimum). **Please confirm the team size.**
