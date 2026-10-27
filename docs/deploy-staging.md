# Deploying staging (Railway + Vercel) and the first real run

> **Current design (supersedes the longer service list in section 1 where they differ).** Railway runs **three** things: Postgres,
> Redis, and **one `backend` service** built from `backend/Dockerfile` (API, worker, scheduler and renderer together, started by
> `backend/start.sh`; run exactly one replica). The customer app (`frontend/`) and the back office (`admin/`) are two separate
> **Vercel** projects, each with its own address, which is what keeps them separate sites. Files go to **Cloudflare R2**. There is no
> malware-scanner service: staging sets `ALLOW_UNSCANNED_UPLOADS=true` (uploads accepted unscanned; the API refuses that setting in
> production). To try the backend image on your own computer first, free and in demo mode: `docker compose -f infra/docker-compose.backend.yml up --build`.

Written so someone can follow it top to bottom. **Nothing here has been run**: this environment cannot reach Railway, Cloudflare,
Resend or the other hosts, so every step below is untested against the real services. Where something is a guess, it says so.
Staging uses its **own keys, database and bucket, with small spend limits**. Never reuse production keys.

## 0. What you need before starting

| Account | For | Notes |
| --- | --- | --- |
| Railway | hosting all services, Postgres, Redis | one project, environment `staging` |
| Cloudflare R2 | media storage | a private bucket, e.g. `cf-staging`; an API token (read/write that bucket) |
| Resend (or any SMTP-compatible provider the app supports) | sign-in codes, invites, "your video is ready" | verify the sending domain's DNS first |
| HeyGen | the AI presenter | already funded; make a **separate staging API key** if you can |
| Anthropic | writing the interview questions and the story | small model by default (`claude-haiku-5-5`) |
| OpenAI (or any OpenAI-compatible endpoint) | the interviewer's voice (`tts`) and transcripts (`whisper-1`) | one key can serve both |
| LiveKit Cloud | the interview room (optional) | see `docs/livekit-interview.md` |
| Two domains | `app.<yours>` for customers, `admin.<yours>` for the back office | they **must differ**; the API refuses to start otherwise |

Decide before you start: **payments.** There is no real payment adapter yet. Staging runs with `BILLING_PROVIDER=manual`: the
Credits page says "added by our team", and an operator tops workspaces up in the back office (Billing → record an offline payment).

## 1. Services

Create these in the Railway project. All build from this repository.

| Service | Root directory | Start command | Public? | Count |
| --- | --- | --- | --- | --- |
| `postgres` | Railway plugin (Postgres 16) | | no | 1 |
| `redis` | Railway plugin | | no | 1 |
| `api` | `backend` | default (`uvicorn`); `railway.toml` runs `alembic upgrade head` first | yes | 1 |
| `worker` | `backend` | `celery -A app.pipeline.celery_app worker --concurrency 2 --loglevel INFO` | no | 1 |
| `scheduler` | `backend` | `celery -A app.pipeline.celery_app beat --loglevel INFO` | no | **exactly 1** |
| `renderer` | `backend/renderer` | default (Dockerfile) | **no, private network only** | 1 |
| `clamav` | image `clamav/clamav:stable` | default | no | 1 (port 3310) |
| `web` | `frontend` | default (Caddy) | yes, `app.<yours>` | 1 |
| `admin` | `admin` | default (Caddy) | yes, `admin.<yours>` | 1 |
| `agent` | `agent` | default (`python interviewer.py start`) | no | 1, only if you use LiveKit |

The renderer needs ~4 vCPU and a few GB of memory (see `docs/render-benchmarks.md`); keep `RENDER_JOBS_CONCURRENCY=1` at first.

## 2. Generate the secrets (once, on your machine)

```
python -c "from cryptography.fernet import Fernet;print(Fernet.generate_key().decode())"   # SECRET_KEY
python -c "import secrets;print(secrets.token_urlsafe(32))"                                  # RENDERER_SHARED_SECRET
```
Keep them in a password manager. **Never paste secrets into chat**, issues, or commits; set them as Railway variables.

## 3. Variables

Use Railway's reference variables for the database, Redis and the private renderer address.

**`api`, `worker` and `scheduler` (the same values on all three):**

| Variable | Value |
| --- | --- |
| `ENVIRONMENT` | `staging` |
| `USE_MOCKS` | `false` |
| `QUEUE_BACKEND` | `celery` |
| `TRUST_PROXY_HEADERS` | `true` |
| `DATABASE_URL` | `postgresql+asyncpg://…` (from the Postgres plugin; note the `+asyncpg`) |
| `REDIS_URL` | from the Redis plugin |
| `SECRET_KEY` | the Fernet key |
| `OPERATOR_EMAILS` | your email(s), comma separated |
| `APP_BASE_URL` / `ADMIN_BASE_URL` | `https://app.<yours>` / `https://admin.<yours>` |
| `API_PUBLIC_URL` | the API's public `https://` address |
| `RENDERER_BACKEND` | `http` is local-only: leave it unset; set `RENDERER_URL` to the renderer's private address |
| `RENDERER_URL`, `RENDERER_SHARED_SECRET` | private URL, e.g. `http://renderer.railway.internal:4000`; the shared secret |
| `STORAGE_ENDPOINT` | `https://<account-id>.r2.cloudflarestorage.com` |
| `STORAGE_BUCKET`, `STORAGE_ACCESS_KEY`, `STORAGE_SECRET_KEY` | the R2 bucket and token |
| `CLAMD_HOST` | the `clamav` service's private host (`CLAMD_PORT` 3310). Uploads are refused without it |
| `EMAIL_API_KEY`, `EMAIL_FROM` | Resend key; `Cover Founder <no-reply@your-domain>` |
| `BILLING_PROVIDER` | `manual` |
| `HEYGEN_API_KEY` | staging key |
| `HEYGEN_DEFAULT_AVATAR_ID` | `ca98f45881f1ba5ee6ad7a44d64855e5` (the man) |
| `HEYGEN_FULLFRAME_AVATAR_IDS` | as in `.env.example` (the three looks, `:plain` for the two news-desk ones) |
| `HEYGEN_FEATURED_PRESENTERS` | as in `.env.example` |
| `LLM_PROVIDER` | `openai` to write the questions, story and content check with the OpenAI key below (default `anthropic`, which needs `ANTHROPIC_API_KEY`). `LLM_MODEL` empty = a small default (`gpt-4o-mini` / `claude-haiku-5-5`) |
| `TTS_API_KEY`, `TRANSCRIPTION_API_KEY` | OpenAI key (`TTS_API_URL` / `TRANSCRIPTION_API_URL` default to OpenAI) |
| `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET` | optional, from LiveKit Cloud |
| `SENTRY_DSN` | optional but recommended |

**`renderer`:** `RENDERER_SHARED_SECRET` (same value), `PORT=4000`, `RENDER_JOBS_CONCURRENCY=1`,
`RENDERER_ALLOWED_HOSTS=<your R2 host>`, `REMOTION_LICENSE_KEY` if your team is over three people (see README).
Do **not** give it a public domain.

**`web` (build arguments, because they are baked into the Content-Security-Policy):** `VITE_API_URL` and `API_ORIGIN` = the API's
public URL; `STORAGE_ORIGIN` = the R2 host (`https://<account-id>.r2.cloudflarestorage.com`); optional `LIVEKIT_ORIGIN` =
`wss://<project>.livekit.cloud`; optional `PRESENTER_IMG_ORIGINS` (defaults to HeyGen's preview hosts). **`admin`:** `VITE_API_URL`,
`API_ORIGIN`, `STORAGE_ORIGIN`.

**`agent`:** `LIVEKIT_URL`, `LIVEKIT_API_KEY`, `LIVEKIT_API_SECRET`, `TTS_API_KEY`; optional `TTS_MODEL`, `TTS_VOICE`.
`LIVEKIT_AGENT_NAME` on the API and `AGENT_NAME` on the agent must match (both default to `cf-interviewer`).

## 4. R2 bucket

- Private (no public access, no custom public domain). Object versioning off for media.
- **CORS**: allow origin `https://app.<yours>` (and `https://admin.<yours>`), methods `PUT, GET`, header `Content-Type`. Without this,
  the browser's upload of interview answers and pictures fails with a CORS error.

## 5. Order of deployment

1. Postgres, Redis, `clamav` (give ClamAV a few minutes to download its signatures; it will refuse scans until then).
2. `renderer`; open its `/health` through Railway's private networking (or check its logs): it should answer `ok`.
3. `api`. The pre-deploy step runs the migrations. If it refuses to start, **read its log**: `runtime_checks` lists *every* wrong
   setting at once. Fix them all, redeploy. `GET /health` must then return `ok`.
4. `worker`, then `scheduler` (one only: two schedulers send reminders twice).
5. `web` and `admin`; attach the two domains; wait for HTTPS.
6. Create the first operator: in a Railway shell on `api`: `python -m app.cli bootstrap-operator you@your-domain 20`
   (20 credits). Sign in at `https://admin.<yours>` with that email (the sign-in code is emailed).
7. `agent` last, if using LiveKit.

## 6. Limits before anything real runs (back office → Setup)

Fail-closed: a vendor with no budget is refused, so set these first. Suggested staging values:

| Vendor | Monthly budget | Why |
| --- | --- | --- |
| `heygen` | **$5** | ~4 videos at ~$1.20; the hard stop on the biggest cost |
| `tts` | $2 | interviewer voice, pennies |
| `transcription` | $2 | answers |
| `renderer` | $5 | internal cost estimate |

Per workspace: give the test workspace **20 credits** and a **spend cap** near what you are willing to lose. Also keep the HeyGen
wallet balance low on a staging key. **Emergency stop:** back office → Overview → *Pause all paid steps* (nothing is lost; videos
resume with Retry).

## 7. Smoke test (no spend), then the first real run

No-spend checks, signed in as the owner of a new test workspace (invite one from the back office, Setup → Invites):

- `GET /v1/capabilities` (the app calls it) shows `"demo_mode": false`, `"presenter": "heygen"`, `"interviewer_voice": "synthetic"`,
  `"transcription": "available"`, `"payments": "manual"`, and `"interview_room": "livekit"` if you set LiveKit.
- The "Tell us about your announcement" page lists the three house presenters, the man first with "(default)".
- Details → the interview opens (this calls Anthropic for the questions: pennies).

**First real run** (spends: about **$1.00 to $1.20 of HeyGen** with two featured answers, plus pennies of voice/transcription):

1. Use a real announcement (the Minicor article is a good one) and answer the four questions on camera, about four minutes.
2. Feature two answers, **Write my story**, read the story it produced, add two pictures you own, **Make my video**.
3. Expect, in the back office Jobs/Costs tabs: `anchor_render` (opening + sign-off), two `question_clips`, then `merge_render`.
4. **Watch for, and write down:** does the story read well and avoid inventing facts (it should hedge the funding figure and list what
   the company did not disclose)? Does the presenter's voice sound right? Does the lip-sync match? Does the video play on a phone?
5. **Stop immediately** (Pause all paid steps) if a step is retrying and the HeyGen spend rises with nothing to show.

Do the second run on the same presenter and voice and confirm the **sign-off is reused** (`reused presenter clip … no vendor cost` in the
`worker` log, and the Costs tab shows nothing for it).

## 8. Backups, monitoring, and what is still open

- Run `scripts/backup.py --upload` daily from a Railway cron service, and rehearse `scripts/restore_test.py` (see the runbook, section 2.9).
- Sentry on all three Python services and the renderer; check the runbook's "first five minutes" once so it is not new at 3 a.m.
- **Open decisions** (not blockers for staging): a real payment adapter (Stripe/Paystack/Flutterwave), the Remotion company licence if the
  team is four or more, a production domain and email-domain reputation, the data-protection review in `docs/security-review.md`,
  and written consent for any real person whose picture is used as a presenter.
- Rotate any key that was ever pasted into a chat or issue before using it here.
