# Target architecture (as implemented)

A modular monolith with background workers. Nothing here introduces new infrastructure: the stack found in the repository was kept.

```
 customer app (React)        back office (React, own origin)
        │  REST + SSE                │  REST (/v1/admin*, operators only)
        ▼                            ▼
   ┌──────────────── FastAPI API (stateless) ────────────────┐
   │ auth · projects · interview · delivery · billing · ops  │
   │ system (ready, capabilities, metrics, HeyGen callback)  │
   └───────┬───────────────────────────────┬─────────────────┘
           │ enqueue(step)                 │ SQLAlchemy
           ▼                               ▼
   Celery workers (or inline in dev)    Postgres: projects, jobs, provider_requests, assets,
   pipeline/runner + steps              takes, scene_plan, ledger, webhook_events, audit_log
           │                               ▲
           ├── avatar provider (HeyGen / Synthesia / mock) ── submit → poll, id recorded first
           ├── LLM, TTS, transcription providers (mocks locally)
           ├── object storage (S3-compatible R2 / local dev), signed URLs only
           └── renderer service (Node): Remotion compositions + ffmpeg, bounded queue
```

## Mapping to the requested design
| Requirement | Where / status |
|---|---|
| Modular pipeline, per-scene tracking, retries | `pipeline/steps.py` (per-clip idempotent assets), `jobs`, `provider_requests`, scene plan; retry resumes, never repeats paid work |
| Structured, validated scene plan, persisted | `schemas`-style models in `services/scene_plan.py`, stored on `projects.scene_plan` |
| Provider abstraction | `integrations/*` interfaces with mocks; registry swaps real/mock; avatar chain with failover |
| HeyGen | `avatar/heygen.py` submit/poll; **contract unverified against live account** (see limitations) |
| Founder interview as a separate module | `routes/interview.py`, `guest.py`, `pipeline/takes.py`; real recordings, consent, chunked resumable upload, transcripts with timestamps |
| Remotion compositions | `renderer/src/compositions/`: `NewsStudio`, `InterviewMerge` with presenter, question, PiP / split / column / full-screen founder scenes, presenter clips, ticker, lower thirds, disclosures |
| Durable async pipeline | Postgres job/request rows; hourly reconciliation; Celery `acks_late` |
| Idempotency | job key `(project, stage, input_hash)`; request key `(project, provider, slot, request_hash)`; webhook `(provider, event_id)` |
| Cancellation, partial failure, scene retry | `cancelled` state; per-piece progress; retry resumes from the failed piece |
| Storage | S3-compatible (R2) or local; keys in DB, signed URLs minted per use; retention job deletes raw takes after 90 days unless kept |
| Multi-tenant isolation | every customer route resolves objects through the caller's workspace (`_owned`); operator routes via `operator` + Origin block; tests assert cross-tenant 404/403 |
| Security | server-side keys, magic-byte upload checks, malware scan (fail closed), HMAC-verified webhooks, rate limits, token redaction in logs, production refuses insecure config |
| Observability | JSON logs with correlation fields; `/health/ready`; operator `pipeline-metrics`; audit log |
| Cost control | spend guard reserve → settle/release per paid call; vendor budgets fail closed; per-vendor concurrency cap; clips reused by hash |

## Key decisions
- **Keep, don't rewrite.** The existing state machine, spend guard, job table and provider interfaces were sound; the gaps were crash-safety of
  paid vendor calls, error classification, cancellation, recovery, a persisted plan and honesty about demo mode.
- **Persist the vendor job before waiting for it**, and hold credits in the same commit as the request row (no leaked holds, no second purchase).
- **Webhooks wake, polling decides.** A forged or replayed callback cannot inject media or change a result.
- **The scene plan stores keys, not URLs**, so it stays valid after signed links expire and can be hashed.
- **Refuse what cannot be rendered** (`product_broll`) instead of approximating it.
- **Say when it is a demo**: `/v1/capabilities` and a dashboard banner when `USE_MOCKS` is on; production refuses to start with mocks.
- **No separate queues or services yet.** A render backlog can delay presenter steps on a shared Celery queue; splitting queues is the first scaling step (see next phase).

## Not implemented (honest list)
- **A real AI B-roll provider.** The abstraction, labelling, billing and UI exist and run against a mock; no vendor has been chosen or
  tested, and the request is synchronous (see the pipeline doc). Without a provider the product says AI shots are unavailable.
- **Scene editing for presenter-only videos** (they have no scene plan); editing a finished video makes it unavailable to download while it re-renders.
- Product footage with presenter voice-over (B-roll plays silent between the presenter and the interview).
- Live HeyGen verification, HeyGen webhooks and a cost model from real invoices.
