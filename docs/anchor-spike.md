# Anchor spike (build spec section 9)

**Status: NOT RUN. This is the one Phase 0 item I could not complete, and the Option A / B decision is still open.**

## Why it did not run
The session has no `HEYGEN_API_KEY` (or Synthesia key) and HeyGen account access. The spike has to generate
real videos and look at them, so I did not fabricate results.

## What is ready
- `scripts/anchor_spike.py` generates 3 transparent-WebM videos through `HeyGenProvider` (Option B), prints
  wall-clock latency, media duration, estimated cost and an ffprobe of the pixel format/alpha tag.
- The `NewsStudio` Remotion composition already composites an anchor clip over an original studio plate
  (`services/renderer`), so an Option B anchor can be dropped in as soon as it exists. A stand-in transparent
  VP9 clip was used for the benchmarks (see `render-benchmarks.md`).
- `AvatarProvider` is the only way the pipeline reaches an avatar vendor, so A and B are interchangeable
  behind it. The pipeline runs today on `MockAvatarProvider`.

## What I need from you to finish it
1. A HeyGen API key (staging) and the id of an avatar trained with matting.
2. For Option A, access to the HeyGen newsroom template: build one with startup name, logo and ticker as
   variables, generate 3 videos through the API, and judge branding control. I cannot assess this without
   an account; the build spec itself marks API support as unverified.

## What to check in the results
| Question | Option A (template) | Option B (transparent + Remotion) |
| --- | --- | --- |
| Can a startup's logo/colors/ticker be injected per video? | ? | Yes, by us (Remotion props) |
| Does it look like an original channel, not a lookalike of a real network? | ? | Yes, we own the plate |
| Does the avatar have clean alpha edges (hair, no fringing)? | n/a | ? |
| Cost per anchor minute | ? | ? |
| Latency per 60-90 s clip | ? | ? |
| Locked broadcast layout enforceable? | ? | Yes |

## Provisional recommendation (unverified)
Option B. We already own and can lock the layout, disclosure labels and channel identity (hard rules 1 and 2) in
Remotion, and re-rendering for an accent change touches graphics only. Option A could win on speed to a good
look but gives up that control. Treat this as a hypothesis until the spike is run.

