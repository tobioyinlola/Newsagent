# How video work is queued

Every slow piece of work (presenter clips, renders, founder recordings) runs on a queue, never inside a web request.
`QUEUE_BACKEND=celery` in staging and production; `inline` (in-process) for local development and tests only.

## Lanes

| Lane | Runs | Why it is separate | Size with |
|---|---|---|---|
| `interactive` | processing a founder's recording | a person is waiting on the page; it must never sit behind a render | `WORKER_INTERACTIVE` (3) |
| `avatar` | presenter clips (opening, explanation, questions, closing) | minutes of polling the avatar vendor | `WORKER_AVATAR` (4) |
| `render` | preview, final and merge renders | minutes of waiting on the renderer | `WORKER_RENDER` (2) |
| `default` | emails, reminders, scheduled sweeps | | `WORKER_DEFAULT` (1) |

`backend/start.sh` starts one worker pool per lane. Each worker process is about 100 MB. To go beyond one container, run the same image as
separate services, each with `celery -A app.pipeline.celery_app worker -Q <lane> --concurrency N` (keep exactly one `beat`).
The renderer has the same split: `RENDER_JOBS_CONCURRENCY` (heavy renders, default 1) and `RENDER_LIGHT_CONCURRENCY` (recording clean-up, default 2).

## What keeps it safe under load

- **A vendor with no free slot is a place in line, not a failure.** The job goes back in line (delayed 5-60 s) without using an attempt.
  It is only reported as failed after 3 hours of waiting. Slots are claimed under a Postgres advisory lock so concurrent workers cannot exceed the vendor limit.
- **One owner per job.** A job is claimed with a single atomic UPDATE; a duplicate or late delivery does nothing.
- **A step only acts on a project in the state that step expects**, so a late message for a failed or cancelled video is ignored.
- **No duplicate messages.** The same step for the same project waits in line once (a Redis marker, cleared when a worker picks it up).
- **A broker outage never breaks a request.** Publishing retries briefly, then logs; the sweep (every 5 minutes) re-sends work for any project stuck for 20 minutes.
- **A killed worker loses nothing** (`acks_late` + `reject_on_worker_lost`); a hung step is killed after 2h50m.
- **A restarted renderer is a retry**, not a failed video. A render that makes no progress for 20 minutes is cancelled and retried.
- **Locks are short.** No database row stays locked while a recording is processed or a render runs.
- **Database connections are bounded:** `DB_POOL_SIZE`, `DB_MAX_OVERFLOW`, `DB_POOL_TIMEOUT_S` per process. Keep `(size + overflow) x processes` under Postgres's `max_connections`.

## Watching it

`GET /health/ready` reports the database, storage, renderer and queue, plus `queue_depth` per lane. A depth that keeps growing means that lane needs more workers.
Customers see "about N videos ahead of yours" on the progress panel while they wait.

## Not covered yet

- A worker is held while it polls the avatar vendor (up to 15 minutes). Lane sizing bounds the damage; the proper fix is to release the worker and resume on the vendor's webhook.
- The renderer keeps its own line in memory (a restart loses queued renders, which are then retried). Several renderers would need a shared line.
- No load test has been run against real vendors; run `renderer/src/loadtest.ts` and a staging soak before launch traffic.
