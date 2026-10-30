# Decisions log

## Open (need you)
1. **Option A vs B for the anchor** - spike not run (no vendor access). See `anchor-spike.md`.
2. **Render speed** - resolved in the sandbox (forced `swangle` GL was the cause); re-verify on Railway.
3. **Transcription vendor** - OpenAI (decided). `whisper-1` via `/audio/transcriptions`; set `TRANSCRIPTION_API_KEY` (an OpenAI key). Roughly $0.006 per audio minute at list price (verify on OpenAI's pricing page); set a `transcription` vendor budget in the console or the spend guard refuses the step.
4. **Auth** - built in-house (decided; replaces Clerk/Auth0). Email + password (scrypt, min 10 chars, common-password check).
   Sign-up is invite-only: choose a password, then verify a 6-digit emailed code (10 min, 5 tries, single use, HMAC-hashed)
   that proves control of the invited address. Forgot-password uses the same kind of code. No authenticator-app (TOTP) by
   decision. Operators confirm every sign-in with an emailed code instead. Sessions are random `nas_` bearer tokens stored as
   SHA-256 and revocable: **1 hour idle** for everyone, 30 days absolute (operators 8 h). Local dev still accepts
   `Bearer dev:<email>` (only when `ENVIRONMENT=local`). Trade-off: we own the security of this code, the token sits in
   localStorage so the CSP is its main protection, and per-email login throttling lets someone lock a victim out for ~10 min.
5. **Railway staging deploy** - deferred by the user.

## Phase 3 decisions
- **Credits are an append-only ledger.** Every balance change goes through `ledger.apply`; a test asserts the ledger
  always sums to the balance. A failed attempt rolls back whole (nothing recorded, nothing charged).
- **A video costs one credit** (`CREDITS_PER_VIDEO`), charged when the project is created; a credit is sold at `USD_PER_CREDIT` ($2.70).
  New sign-ups get `SIGNUP_CREDITS` (1) free. With no credit left, `POST /v1/projects` answers 402 `insufficient_credits` and the app
  shows a "buy credits" popup. Customers buy fixed amounts (`CREDIT_PURCHASE_USD`: 1, 10, 50, 100, 200) and get amount / price credits
  (rounded to 0.01). Per-step charging is off (`CREDIT_MARKUP=0`); vendor cost is still recorded for budgets and margin.
- **Payments**: provider-neutral interface, HMAC-signed webhook, idempotent by ledger ref, amount must match the checkout.
  The provider (Stripe / Paystack / Flutterwave) is **undecided**; only a mock exists. Mock provider and dev-pay route are local-only.
- **Moderation is fail-safe**: LLM outage => hold for a human; unclear LLM answer => review. Approvals are keyed to a
  fingerprint of the content, so any edit needs a new review. Operators can switch to log-only (shown with a warning).
- **Failover** tries providers in order, each against its own vendor budget, releasing the failed attempt's hold. A
  provider whose monthly budget is spent is skipped. Green-screen output (Synthesia) is keyed to alpha by the renderer.
- **The emergency pause is a database switch** read on every reserve, so it takes effect immediately across all workers.
- **Workspace deletion keeps the ledger** (anonymised) because financial records must be retained; everything else goes.
- **The API refuses to start** with an insecure production config (mocks on, default keys, no scanner, http base URL...).
- **Chose not to** add: billing-provider SDKs, multi-currency, taxes/invoices, SSO, a human-support inbox, a separate
  moderation service. Each is a real need before scale, none was needed to prove the unit economics.

## Phase 2 decisions
- **Chunked uploads, not S3 multipart.** MediaRecorder emits ~2 s chunks; S3 multipart needs >= 5 MB parts. Each chunk
  is its own object (`takes/<id>/raw/00007`), confirmed server-side by index; the renderer joins them. This makes
  resume trivial (the server's confirmed list is the truth) and keeps large files off the API.
- **Reminder links need the raw token**, which the spec says is stored hashed. We store the SHA-256 hash for lookups
  AND a Fernet-encrypted copy (`SECRET_KEY`) used only to re-send the same link in reminders. The encrypted copy is
  deleted when the founder submits, the owner revokes/merges, or the link expires.
- **Takes are processed as soon as the founder keeps them** (not at submit) so a dark or silent take is caught while
  they are still on the page. Retakes are unlimited before submission; per-recording size/duration checks and per-token/IP request throttling still apply.
- **Take failures never change the project state** (take-level `failed` + retry); only the owner-visible pipeline
  steps move the project.
- **Interview cut renders two anchor clips** (intro+body, then outro) plus one clip per question. Costs 2 + N avatar
  generations instead of 1; needed so the interview can sit between body and outro.
- **Skip interview** from `awaiting_founder` uses the merge path with no answers (anchor intro + outro).
- Whisper: any OpenAI-compatible `/audio/transcriptions` endpoint (OpenAI, Groq, self-hosted). No vendor lock decided.
- Magic-link and share tokens are scrubbed from access logs and Sentry; the app sends `Referrer-Policy: no-referrer` via
  meta tag and the founder page is `noindex`.
- Avatar videos are now copied into our own storage (vendor URLs expire). Not yet exercised against real HeyGen.

## Made (assumed
- Remotion: free tier (team of 3 or fewer). Revisit if headcount reaches 4.
- Email: Resend (`integrations/email/resend.py`). Needs `EMAIL_API_KEY` and a verified sending domain (SPF/DKIM/DMARC).
- Railway staging deploy deferred.

## Made (assumed; change if you disagree)
- Credits and costs are USD-denominated decimals (`Numeric(12,4)`).
- Spend guard **fails closed**: no `VendorBudget` row for the current month means the step is refused.
- Cheap stages (brief parsing, script writing) are not metered by the guard; they are rate limited only.
- `limit_reached` is an extra project state (spec: "clear limit reached state"). Operator raises credits, the
  owner presses retry, and the pipeline resumes from the same step; the idempotent steps never double-charge.
- A project that fails keeps `failed_from`, so retry resumes at the failing step.
- Pipeline for Phase 0 is anchor-only: `script_approved -> rendering_anchor -> anchor_ready -> final_ready`
  (final render is auto-enqueued from `anchor_ready`). Preview render and the interview branch come with Phases 1/2.
- Uploads: the browser sends files straight to storage; `POST /brand-kit/uploads/confirm` re-reads the object, checks real size
  and magic bytes, rejects active content in SVG/PDF, and malware-scans it. No scanner configured (`CLAMD_HOST`) means uploads
  are refused outside mock mode. Fail closed: a scanner outage leaves the file pending, never clean.
- Quality gate fails a video on: wrong length (>5% / 1 s), no audio, clipping, audio/video length drift, missing labels,
  banned names. Loudness is normalised to -16 LUFS by the renderer (not failed on). Lip-sync is approximated by
  audio/video duration drift; true A/V sync testing needs the real HeyGen output.
- On-screen text limits (lower-third 40/60 chars, ticker 90 chars / 8 lines) are enforced at approval.
- Rate limiting: Redis in staging/production, memory locally; fails OPEN if Redis is down (logged). Set
  `TRUST_PROXY_HEADERS=true` behind Railway so per-IP limits see real client IPs.
- Mandatory disclosure labels and the channel identity (Cover Founder, our own brand) are constants in `pipeline/steps.py`, are passed
  as Remotion props, and are asserted by the quality gate. Banned real-network names are checked in overlays.
- The in-memory rate limiter is fine for one API instance; move it to Redis before running several.
- `docs/BUILD_SPEC.md` is not committed. Please add the spec file there.

## Live AI interview and the separate back office
- The interview happens **before** any paid render. Script approval with `interview_mode=live` moves the project to
  `interviewing`; the owner records at the dashboard; "Make my video" validates every answer, runs moderation, then
  starts the anchor and merge. A founder who abandons costs nothing but the voice lines.
- Questions are pre-generated with the script (exactly 4 by default), not adaptive. Adaptive follow-ups would need an LLM
  call between answers plus the transcription delay inside a 5-minute window; revisit once real timings exist.
- Voice is a provider (`integrations/tts`) with its own spend budget; lines are cached by text hash. Voice failure never
  blocks the interview (the browser voice is the fallback). Audio is not recorded from the speaker, the camera take is video-only.
- Camera is required. Each answer stores a snapshot (`Take.snapshot_key`), used as the answer thumbnail, the column's avatar
  and a fallback when a clip is unusable. The full clip, not the snapshot, is the footage in the video.
- Interview time: 300 s total, answer window 15 to 75 s computed from the question count (9 s speaking overhead, 14 s closing).
- The column layout is a Remotion composition: per-answer cues (relative to the trimmed start) reveal transcript lines in sync.
- Back office is a separate app (`admin/`) on its own origin. Defence in depth: the API rejects `/v1/admin*` requests whose
  Origin is the customer app, CORS lists both origins, CSP is per site. The admin app copies a few UI files from `frontend/`
  rather than sharing a package (cheap now; extract a package if they drift).
- Revenue figures count card checkouts only; offline/manual payments show up as credits granted, not revenue.

## Presenter clips
- Real presenter footage is a platform-wide library managed by operators in the back office, not per customer. It frames the AI
  presenter (opening shot, cutaways between answers, sign-off); it does not replace the avatar's lip-synced reading of the script,
  which pre-recorded clips cannot do.
- Rights are an explicit, audited attestation on upload (who confirmed, when). We cannot verify rights ourselves.
- A clip's length must suit its role so cutaways cannot bury the founder; clips are not transcribed, so captions are shifted around them.
- Selection is deterministic per project (project id picks among active clips), so re-rendering a project does not change its shots;
  changing the library changes the merge input hash and re-renders.
- Not yet used in the presenter-only (no interview) video.
