# Decisions log

## Open (need you)
1. **Option A vs B for the anchor** - spike not run (no vendor access). See `anchor-spike.md`.
2. **Render speed** - misses the 15 min target as built; choose a mitigation (see `render-benchmarks.md`).
3. **Transcription vendor** - spec says "Whisper-class". Hosted (OpenAI/Groq/Replicate) or self-hosted?
4. **Auth provider** - Clerk or Auth0. The API verifies any RS256 JWT with an `email` claim via JWKS; local dev uses
   `Bearer dev:<email>`.
5. **Railway staging deploy** - deferred by the user.

## Decided
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
- Mandatory disclosure labels and the fictional channel identity are constants in `pipeline/steps.py`, are passed
  as Remotion props, and are asserted by the quality gate. Banned real-network names are checked in overlays.
- The in-memory rate limiter is fine for one API instance; move it to Redis before running several.
- `docs/BUILD_SPEC.md` is not committed. Please add the spec file there.
