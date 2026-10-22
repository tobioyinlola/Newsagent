# Operations runbook

Written for whoever is on call, possibly at 3 a.m. Each playbook says what you see, what to do, and how to know it
worked. Everything here can be done from the **operator console** (`/admin`) unless a command is shown.
Commands assume the API's environment variables (`DATABASE_URL`, ...) are set, e.g. in a Railway shell.

> Fill in before launch: on-call contact __________, vendor status pages (HeyGen, Synthesia, Anthropic, Resend, Railway,
> Cloudflare), who can approve spend, who can talk to customers, who talks to a regulator.

## 0. First five minutes (any incident)
1. **Is it us or a vendor?** `/health` on `api` and `renderer`; Overview tab in the console (queue counts, jobs failing); Sentry.
2. **Is money at risk?** Overview shows vendor spend; Costs tab shows today's per-video cost. If spend looks wrong:
   **Pause all paid steps** (Overview). Nothing is lost: running videos move to "limit reached" and resume with Retry.
3. **Write down the time** and what you changed. The audit log records console actions automatically.
4. Tell affected customers plainly (templates in section 10) if videos will be late.

## 1. Console map
| Tab | Use it to |
| --- | --- |
| Overview | queue counts, **emergency pause**, avatar failover, moderation mode |
| Review queue | approve/reject content held for review (owners wait on this) |
| Jobs | find failed or **stuck** jobs, retry a customer's video |
| Costs | cost, credits charged and margin per video; CSV |
| Billing | credit packs, record an offline payment |
| Setup | invites, vendor monthly budgets, per-workspace limits, suspend, disable sharing |
| Audit log | who did what |

## 2. Playbooks

### 2.1 Videos are failing at the anchor step (HeyGen outage or errors)
- **See**: Jobs tab shows `anchor_render` / `question_clips` failed; owners see "We couldn't finish this step".
- **Do**: Overview → **Avatar provider failover**: set primary = the healthy provider, or set a secondary and tick
  *Fail over automatically*. Then Jobs → **Retry video** on the failed ones. Failed attempts are never charged.
- **Check**: new jobs succeed; Costs tab shows the new vendor. The secondary needs its own **monthly budget** (Setup →
  Vendor budgets) or it is refused (fail closed).
- **Note**: Synthesia's API is unverified against the live service; the first failover should be watched.

### 2.2 The renderer is slow, down, or returning "busy"
- **See**: jobs stuck in `rendering`; `/health` on the renderer shows a long `queued`; logs show 429.
- **Meaning**: 429 is by design. The API waits and retries for up to 15 minutes before failing a video.
- **Do**: add renderer instances (Railway) rather than raising per-instance concurrency. Measured on 4 vCPU:
  concurrency 2 is the sweet spot (+46% throughput); 3 adds 1.5 GB of memory for ~4% more (see `render-benchmarks.md`).
  Restart a wedged instance; stuck jobs older than the timeout are picked up again automatically.
- **Check**: `queued` falls; Jobs → status "running" count drops.

### 2.3 Spend is higher than expected (runaway cost)
- **Do**: **Pause all paid steps** immediately. Then Costs tab: sort by vendor cost; find the workspace/video. Setup →
  lower that workspace's credits/cap or **Suspend** it. Lower the vendor's monthly budget.
- **Why it can't run away**: every paid step reserves against credits, the workspace cap, and the vendor's monthly budget
  first, and a vendor with no budget is refused. If spend still exceeded budget, that is a bug: keep the pause on and
  capture the job ids.
- **Reconcile**: the credit ledger sums to every balance, and each video's vendor cost sums to its project cost. The restore
  test checks the first; the Costs tab shows the second.

### 2.4 A step is stuck "running" forever
- Jobs tab flags jobs as **stuck** (running longer than 30 min or 1.5x the vendor timeout). **Retry video**.
- Founder takes stuck in "processing" are re-queued every hour by the scheduler. If the **scheduler is not running**,
  nothing re-queues and no reminders or retention deletions happen: check the `scheduler` service (exactly one instance).

### 2.5 Content problem (something got through, or a customer complaint)
1. Setup → the workspace → **Disable sharing** (kills every share link at once) and/or **Suspend**.
2. Review queue shows what was held; Audit log shows who approved what.
3. To remove a specific video: ask the owner to delete it, or delete the project via the database (files are removed by
   the same purge code the API uses: do it through the API as the owner if possible).
4. Tune `services/moderation.py` rules and add a test with the offending text (never commit the raw content).

### 2.6 Payment webhook failing (customers paid, no credits)
- **See**: customer says they paid; Billing tab has no purchase; provider shows webhook errors (401 = signature).
- **Do**: confirm `BILLING_WEBHOOK_SECRET` matches the provider's signing secret. Then either replay the event from the
  provider dashboard (safe: it is idempotent) or record it manually: Billing → *Record an offline payment* with the
  provider payment id as the reference (a repeat is a no-op).

### 2.7 A magic link or share link leaked
- Founder link: owner opens the project → **Revoke link** (or creates a new one, which replaces the old). Operator can
  revoke by suspending the workspace. Share link: owner **Revoke all links**; operator **Disable sharing**.
- Links are 256-bit; the risk is *exposure*, not guessing. After revoking, check the Audit log and tell the owner.

### 2.8 A secret leaked (API key, `SECRET_KEY`, webhook secret, shared secret)
| Secret | Rotate by | Side effects |
| --- | --- | --- |
| Vendor API keys (HeyGen, Anthropic, Resend, transcription) | new key at the vendor, update Railway variable, redeploy `api`+`worker` | none |
| `RENDERER_SHARED_SECRET` | change on `renderer` **and** `api`/`worker` together | brief render errors during rollout |
| `BILLING_WEBHOOK_SECRET` | change at the provider and in Railway together | webhooks fail between the two changes: replay them |
| `SECRET_KEY` (Fernet) | generate a new key, deploy | stored founder-reminder links become unreadable: reminders for open interviews stop and the owner must create a new link; **founder links themselves keep working** |
| R2 keys | new token in Cloudflare, update Railway, redeploy | in-flight signed URLs are invalidated |
| `SECRET_KEY` also keys sign-in code hashes and password-reset codes | see above | **pending codes stop working** (passwords keep working) |
Then run `git log -p | grep` style scan if the leak might be in the repo; the history is clean as of this review.

### 2.9 Restore the database
1. **Don't** restore over production first. Create a new Postgres, restore into it, check it, then repoint `DATABASE_URL`.
2. Get the newest backup (`backups/db/<env>/*.dump` and its `.json` manifest) from R2.
3. Verify and rehearse: `python scripts/restore_test.py <file.dump>`. It restores into a throwaway database and checks the
   checksum, the migration revision, every table's row count, that the credit ledger equals each balance, and that
   nothing is orphaned. It prints PASS/FAIL per check and exits non-zero on any failure.
4. Restore for real: `createdb newdb && pg_restore --no-owner --no-privileges -d newdb file.dump`, then
   `alembic upgrade head`, then repoint and restart `api`/`worker`/`scheduler`.
5. **Media is not in the database backup.** Files live in R2. Protect them with R2 durability, and decide whether to
   enable bucket replication (note the deletion caveat in `security-review.md` section 7).
- **Targets (proposed, not yet measured at scale)**: RPO 24 h (daily backup), RTO 1 h. The only measured restore was a
  small seeded database (52 KB, 0.2 s): re-measure on staging with realistic data before relying on RTO.

### 2.9a A user (or operator) can't sign in
- Forgotten password: they use **Forgot your password?** on the sign-in page (a code is emailed; resetting signs out every device).
- New operator, or an operator locked out: same flow with their email (an operator has no password until they set one).
- Locked out after too many tries: wait 10 minutes. If the code email never arrives, check Resend status and the sending-domain DNS.
- Suspected stolen session or password: the user's **Security** page → *Sign out everywhere* / *Change password*; or reset the
  password as above, which revokes every session.

### 2.10 Someone asks for their data, or to be deleted
- Owner: they can self-serve **Your data** (export, delete workspace). Founder: the **Delete all of my recordings** button on
  their page. Operator on request: ask the owner to do it, or do it as them.
- Deletion removes files and rows; **backups keep the data until they expire** (say so; propose 30-day backup retention).
- Billing records are kept, anonymised, by design.

### 2.11 Suspected personal-data breach
1. Contain (pause, revoke, rotate secrets as above). 2. Preserve logs and the audit trail; don't delete anything.
3. Establish what data, whose, since when. 4. **Notify your lawyer immediately**: many regimes require notifying the
regulator within **72 hours** of awareness (GDPR/UK GDPR; others differ) and sometimes the people affected.
5. Customers first if their founders' footage is involved. 6. Write the post-mortem.

## 3. Routine operations
| When | What |
| --- | --- |
| Daily | Overview: queue, failures, pending reviews (owners are waiting). Vendor spend vs budget |
| Daily (automatic) | `scripts/backup.py --upload` from a Railway cron service; the scheduler's daily job deletes raw founder takes past retention |
| Weekly | `scripts/restore_test.py` on the newest backup. A failing restore is a P1 |
| Monthly | Vendor budgets reset by month key; set next month's budgets *before* the 1st or paid steps are refused. Review the Costs report and margin |
| On every deploy | migrations run as a release step; keep them backward compatible with the previous release so rollback is safe |

**Rollback**: redeploy the previous image. Because migrations are additive, the previous API runs against the new schema.
Never run a destructive migration in the same release that stops using the column.

## 4. Capacity guide (from measurements, 4 vCPU instance)
- ~4.5 videos/min at concurrency 1, ~6.6 at concurrency 2, for 5 s clips. A 90 s video takes ~5 min per format.
- Memory: ~1.7 GB per running render pipeline; plan 2 GB per slot.
- The queue is capped (`MAX_QUEUE`, default 20 waiting jobs); beyond that the renderer answers 429 and the API waits.

## 5. Severity guide
| Sev | Meaning | Example | Response |
| --- | --- | --- | --- |
| P1 | Data exposure, runaway spend, nothing renders, restore failing | leaked links, spend 10x | now; pause first |
| P2 | One vendor down, queue backed up, payments failing | HeyGen outage | within 1 hour; failover |
| P3 | A customer's video failed; slow reviews | stuck job | same day |

## 10. Customer message templates
- **Delay**: "Your video is taking longer than usual because of an issue with one of our providers. You haven't been
  charged for anything that failed, and we'll email you the moment it's ready."
- **Held for review**: "A member of our team is checking your script before it's made. This is usually quick."
- **Breach (after legal review)**: what happened, what data, what we've done, what you should do, who to contact.
