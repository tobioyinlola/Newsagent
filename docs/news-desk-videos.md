# News Desk breaking-news videos

News Desk is independent of business interview generation. It uses `NewsStory`, `NewsImage` and `NewsVideo`, its own `newsdesk` Celery worker, and the `NewsBreaking` Remotion composition. It never creates customer projects, customer pipeline jobs or wallet ledger entries. The only shared visual components are the existing read-only brand intro/outro. Migration: `0034`.

- Written article: 200–300 words; spoken script: 60–95 words. Invalid drafts may be saved for editing, but cannot be published or generated.
- Final limit: **60 seconds including all media/audio**. Five-second brand intro + two-second breaking-news sting + at most 47 seconds of presenter narration + six-second brand outro. Renderer frame count and measured video/audio/container durations are checked. No speed-up or speech truncation is used to fit an overlong recording.
- The continuous presenter recording supplies the spoken audio. Selected pictures move and crossfade over it, returning to the presenter between pictures and before the outro. Picture timings are fitted to the available narration time.
- Select a verified cover image separately from gallery order. Public cards use that image. Publishing creates an immutable editorial snapshot with a ready video reference; edits never change the live version until republished.
- Generation requires source attribution, approved copy, a cover and selected pictures. Concurrent requests for the same revision reuse a single job. A save creates a new revision; publishing without changes can reuse an identical completed recording.
- `WORKER_NEWS_DESK` defaults to 1. The dedicated recovery sweep resends queued jobs and recovers stale running jobs after one hour. `NEWS_DESK_AVATAR_ID` optionally overrides the editorial presenter; otherwise `HEYGEN_DEFAULT_AVATAR_ID` is used.
- Company presenter-vendor budget and the paid-step pause switch are enforced without charging customer credits. Provider IDs, media and measured durations are persisted. Ambiguous paid submissions require reconciliation rather than automatic resubmission. Renderer retries reuse stored presenter footage. Errors and progress are visible in Admin → News Desk.
- All active back-office members retain News Desk access. Customer login defaults to `portal=customer`; admin login sends `portal=admin`. The server rejects the wrong portal, preserves admin email-code verification, and prevents team email addresses from customer signup or customer invitations.

The generated business-video distribution prompt is a separate frontend component, shown once per workspace/project with “Yes, choose outlets” and “Maybe later”. It opens distribution with the finished project selected and never initiates payment.
