# Gate 3: launch readiness

Criteria (from the build spec): *pilot customers can download and share finished videos; cost per video is known for 10
pilot videos; the security and privacy review is closed.* **None of the three is met yet.** This page says exactly what is
built and what is left, so the gate can be called honestly.

## 1. Pilot customers can download and share finished videos
| Piece | State |
| --- | --- |
| Download MP4 (16:9, 9:16), SRT, thumbnail; revocable share link; copy-ready captions with the mandatory disclosure | Built and tested end to end |
| Founder interview merged into the video | Built; verified on emulated 4G with real ffmpeg + Remotion (`docs/gate-2.md`) |
| Anchor from a **real** avatar provider | **Blocked**: needs a HeyGen key and avatar id (and the Option A/B spike). Everything else runs on mocks for the avatar and transcription |
| Real sign-in | **Blocked**: Clerk or Auth0 not chosen |
| Deployed environment | **Not created** (deferred by you) |

## 2. Cost per video known for 10 pilot videos
Built: every paid step is recorded in an append-only credit ledger with project, step, vendor and **vendor cost**; the console
Costs tab and `GET /v1/admin/cost-report(.csv)` give, per video: vendor cost by vendor, credits charged, and margin, plus
the average over finished videos. `CREDIT_MARKUP` and `USD_PER_CREDIT` set pricing; both are 1 until you decide.

**Not possible yet**: real numbers. HeyGen's price per minute in the code is a placeholder (`$1.00`), the renderer's cost per
output is a placeholder (`$0.05`), and transcription's is an estimate. Until the pilot runs on real vendors the report
shows placeholder arithmetic, which proves the plumbing, not the margin. To close this item: run 10 videos on real vendors in
staging, export the CSV, and replace the placeholder rates (`avatar/heygen.py`, `renderer/http.py`, `pipeline/takes.py`) with
the measured ones.

## 3. Security and privacy review closed
See `docs/security-review.md`. Summary: engineering review done: 10 findings fixed and 1 mitigated (including 2 critical dependency
advisories and 2 SSRF paths), 3 accepted with reasons, 3 open. **Still needed before this can be closed**: a lawyer on the
section 8 items, a third-party penetration test of a deployed staging, and the infrastructure checklist in section 9.

## 4. Phase 3 deliverables
| Deliverable (spec section 15) | State |
| --- | --- |
| Billing and usage metering | **Built**: ledger, packs, checkout, signed idempotent webhook, usage statements, low-balance alert. **Payment provider adapter not built** (provider undecided): a mock provider with the real flow shape is in place |
| Operator console: job queue, cost per project, content review queue, vendor failover switch | **Built** (+ emergency pause, audit log) |
| Moderation of briefs and scripts | **Built** (rules + optional LLM; also screens founder transcripts). Rules are starter rules for a human to tune |
| Security and privacy review | **Drafted**, see above; not closed |
| Restore test from backup | **Done and repeatable**: `scripts/backup.py`, `scripts/restore_test.py`; 7 checks pass; fails correctly on a corrupted backup. Small dataset only; media files not covered by DB backups |
| Load test of the renderer | **Done** on one 4 vCPU instance (below). Not run on Railway; API-level load test not done |
| Runbook for incidents | **Written**: `docs/runbook.md` (not yet rehearsed with a person on call) |

## 5. Load test summary (renderer, 4 vCPU / 16 GB sandbox, 6 concurrent 5 s renders)
| Job concurrency | Wall time | Videos/min | Median / last completion | Peak memory |
| --- | --- | --- | --- | --- |
| 1 | 80 s | 4.5 | 54 s / 80 s | 1.7 GB |
| 2 | 55 s | **6.6** | 37 s / 55 s | 3.2 GB |
| 3 | 53 s | 6.8 | 52 s / 53 s | 4.7 GB |
Overload (8 jobs, concurrency 1, queue cap 2): 3 accepted, **5 rejected with 429**, 0 failed, memory flat at 1.7 GB.
Recommendation: concurrency 2 per 4 vCPU; scale by adding instances. Sandbox numbers: repeat on Railway.

## 6. What I need from you to finish Gate 3
1. A HeyGen key and avatar id (anchor spike; real cost per minute).
2. Clerk or Auth0 decision, a payment provider decision (Stripe / Paystack / Flutterwave), a transcription vendor.
3. Prices: credit packs, markup, and what a credit is worth (`USD_PER_CREDIT`).
4. A lawyer, and someone to own moderation policy.
5. Permission to deploy staging (Railway) so the checklist and a real pen test can happen.
