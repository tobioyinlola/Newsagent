# Anchor spike (build spec section 9)

**Status: PARTLY RUN. The key works, but no video was generated: the account has a $0.00 wallet and HeyGen returned
`402 insufficient_credit`. The Option A / B decision is still open.**

## What the live API told us (2026-10-22)
- Auth works with `x-api-key`. `GET /v3/users/me` shows a **wallet billing** account with `remaining_balance: 0.0`.
- `GET /v3/avatars` (paginated) returns avatar *groups* (e.g. Dante, 27 looks). `GET /v3/avatars/looks` returns the looks,
  each with `avatar_type` (the ones seen are `photo_avatar`), `supported_api_engines` (`avatar_v`, `avatar_iv`, `avatar_iii`)
  and `default_voice_id`. Nothing in these listings says a look supports transparent/webm output; that is still unconfirmed.
- `GET /v3/voices` works and is paginated; voices carry `language` and `gender`, not an accent field.
- `POST /v3/videos` with `{type:"avatar", avatar_id, script, output_format:"webm"}` was refused at the credit check, so the
  request shape is still unproven. `avatar_id` may need to be a *look* id rather than a group id.
- The older `/v2` endpoints are legacy and sunset on 2026-10-31; we use `/v3` only.
- `developers.heygen.com` (the API reference) is not reachable from this environment's network policy.


## Why it did not run
The session has no `HEYGEN_API_KEY` (or Synthesia key) and HeyGen account access. The spike has to generate
real videos and look at them, so I did not fabricate results.

## What is ready
- `scripts/anchor_spike.py` generates 3 transparent-WebM videos through `HeyGenProvider` (Option B), prints
  wall-clock latency, media duration, estimated cost and an ffprobe of the pixel format/alpha tag.
- The `NewsStudio` Remotion composition already composites an anchor clip over an original studio plate
  (`backend/renderer`), so an Option B anchor can be dropped in as soon as it exists. A stand-in transparent
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

