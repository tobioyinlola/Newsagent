# Marketing (segments, email copy, workflows): plan

Status: **plan, nothing built yet.** Admin-side only (Back office > Marketing). Email only for now; the shape leaves room for other channels later.

## 1. What we are building

Three things an operator can do without a developer:

1. **Segments**: save a group of users defined by rules, mainly *when they joined* (e.g. joined 3 to 7 days ago) combined with *what they have or haven't done* in the product.
2. **Copies**: a library of email copy (subject, preview line, body) with merge tags like `{{first_name}}`, `{{company}}`, `{{credit_balance}}`, previewed in the existing branded email shell and testable with "send to myself".
3. **Workflows**: a builder that connects a segment (or an event) to a sequence of steps: *send email*, *wait N days*, *if/else on behaviour*, *stop*. Plus **one-off campaigns** (segment + copy + a send time) for quick sends such as "email every existing user who has made 0 videos, today".

## 2. What already exists and gets reused

| Need | Already in the repo |
|---|---|
| Send mail | `integrations/email` (`EmailProvider`: Resend, SMTP, mock). Supports `headers`, so `List-Unsubscribe` works with no change. |
| Branded HTML | `services/email_templates.render()` (heading, body, button, footer). Marketing copy renders through it, so it matches every other email. |
| Background jobs | Celery beat in `pipeline/celery_app.py`. `outreach.deliver` already does "send held emails when their time comes, spaced and capped" (`services/outreach.py`); the marketing sender copies that pacing pattern. |
| Admin shell, auth, audit | `frontend/src/admin` (routes in `App.tsx`, `useCan`), RBAC in `services/rbac.py`, `services/audit.py`. |
| Facts to segment on | `users` (created_at, last_login_at, workspace), `workspaces` (industry, country, plan, credit_balance), `projects` (state, created_at), `credit_transactions`, `checkouts`, `distribution_requests`, `referrals`. Enough for v1 with **no new event tracking**. |
| Opt-out precedent | `outreach_optouts` (outlets only). Users have no marketing consent or unsubscribe state today. This is new and is step one. |

Note: the existing Outreach feature emails *outlets* about placements. Marketing emails *our own users*. They are separate (separate tables, separate sender identity), but share the delivery pattern.

## 3. Data model (one Alembic migration, `0040_marketing`)

- `marketing_segments`: `id, name, description, rules (JSON), created_by, archived_at`. Rules are a small tree: groups of conditions joined by AND/OR. Segments are **dynamic** (re-evaluated each time they are used); a send or enrolment records who was matched at that moment.
- `marketing_copies` and `marketing_copy_versions`: `name, category (onboarding|activation|billing|win-back|product), subject, preheader, body, button_label, button_url`. Each edit makes a new version; sends point at a version, so history is never rewritten.
- `marketing_workflows`: `name, status (draft|active|paused), trigger (JSON), steps (JSON graph), settings (JSON: send window, re-entry rule, goal/exit condition)`. Steps stored as JSON nodes with `id, type, config, next[]`. v1 UI edits it as a vertical list, but the stored shape is a graph so a canvas editor can come later with no migration.
- `marketing_enrollments`: `workflow_id, user_id, status (active|completed|exited|failed), current_step, next_run_at, entered_at, exit_reason`. Unique on `(workflow_id, user_id)` unless re-entry is allowed.
- `marketing_sends`: `user_id, copy_version_id, workflow_id|campaign_id, enrollment_id, status (queued|sent|failed|skipped), skip_reason, provider_message_id, scheduled_for, sent_at`. A unique key on `(enrollment_id, step_id)` makes every step send **at most once**, even if the worker retries.
- `marketing_campaigns`: one-off sends (`segment_id, copy_version_id, send_at, status, audience_snapshot_count`).
- `marketing_prefs`: `user_id, marketing_opt_out_at, source, unsubscribe_token`. Plus a suppression list for hard bounces and spam complaints.

Permissions: `marketing.view` and `marketing.manage` added to `services/rbac.py`; sending/activating needs `manage`. Every create, activate, pause and send is written to the audit log.

## 4. Segments

**Time (the main axis)**
- Joined between *A* and *B* days ago (e.g. 0 to 1, 3 to 7, 30+), or between two calendar dates.
- Last seen: active in the last *N* days, or inactive for *N* days.

**Behaviour (from existing tables)**
- Created *N or more* / zero videos; reached a given project state (script approved, video delivered).
- Has / hasn't bought credits; credit balance above/below a value; ran out of credits.
- Made / hasn't made a distribution request; has referred someone.
- Has / hasn't completed brand kit setup.

**Profile**: industry, country/region, plan.

The editor shows a live **count and a sample of 10 people** before saving (this is the safety net that matters most), and the same preview is shown again before any send or activation.

Implementation: a registry of named fields in `services/marketing_segments.py`, each mapping to a SQL expression. The rule JSON is validated against the registry and compiled to one SQLAlchemy query. No raw SQL from the UI.

## 5. Copies

- Subject, preheader, body (plain text with blank-line paragraphs, same convention as `email_templates.render`), optional button.
- Merge tags with fallbacks: `{{first_name|there}}`. Unknown tags fail validation at save, not at send.
- Live preview as it will look in the branded shell, **send test to myself**, and a plain-text twin generated automatically.
- Every email gets an unsubscribe footer and `List-Unsubscribe` + `List-Unsubscribe-Post` headers added automatically; the operator cannot remove them.
- Later: "draft this with AI" using the existing LLM provider (operator edits before use).

## 6. Workflows

**Triggers**
- *Enters a segment* (checked every few minutes), e.g. "joined 1 day ago and has made 0 videos".
- *Joined*: fires when an account is created.
- *Manual / backfill*: add everyone currently in a segment.

**Steps (v1)**: Send email, Wait (days/hours, with an optional "send at 10:00 local" time), Condition (segment membership or "has done X" -> yes/no branch), Stop.

**Exit rules**: a workflow can define a **goal** (e.g. "made first video"). When a user reaches the goal they leave the workflow immediately, so nobody gets "make your first video" after making one. Also exits on unsubscribe, account deletion or suspension.

**Existing users**: when a workflow is activated the operator chooses *new people only* or *include everyone who matches now*. The second path shows the count first, then **drips them in** at a capped rate (e.g. 200 an hour) instead of blasting, which protects the sender reputation. This covers "email current users who have done few actions right away".

**Engine**: one Celery beat task, `marketing.tick`, every minute:
1. Enrol new matches for active workflows.
2. Advance enrolments whose `next_run_at` has passed (evaluate conditions, schedule the next step).
3. Deliver queued sends under the guards below.

Every step is idempotent (the unique key above), so a crashed or retried worker never double-sends.

## 7. Sending guards (these are what keep this from becoming a spam problem)

- **Consent and unsubscribe first**: one-click unsubscribe page (`/unsubscribe/<token>`, no login), honoured instantly, per-user. Transactional mail (sign-in codes, receipts, low-credit alerts) is a separate path and is never blocked or counted.
- **Frequency cap** across all workflows (default: at most 1 marketing email per user per 2 days) and a **daily account cap**.
- **Send window / quiet hours** (default 09:00 to 18:00 in the user's country timezone).
- **Pacing** per hour, as outreach does.
- **Suppression**: hard bounce and complaint events from the Resend webhook add the address to the suppression list.
- **Kill switch**: a global "pause all marketing" setting, and per-workflow pause that stops sends within one tick.
- **Separate sending identity**: marketing from its own subdomain/From (e.g. `news@mail.coverfounder.com`) so a marketing problem never affects sign-in-code delivery.
- Off by default behind `MARKETING_EMAIL=on` and a staging dry-run mode that sends only to operator addresses.

## 8. Admin UI (`/marketing`, with Segments / Copies / Workflows / Campaigns / Activity tabs)

- **Segments**: rule builder (add condition, pick field, operator, value), live count + sample.
- **Copies**: list, editor with side-by-side preview, versions, send test.
- **Workflows**: vertical step builder; each step is a card (Send / Wait / Condition / Stop); a header showing trigger, segment, goal; a funnel view per workflow (entered, emailed, converted, exited). Activate button shows the audience count and confirms.
- **Campaigns**: pick segment + copy + time, preview audience, schedule or send now.
- **Activity**: per-user log of what was sent and why something was skipped (so support can answer "why did I get this?").

New code lives in `backend/app/{models,routes,services}/marketing*.py` and `frontend/src/admin/pages/Marketing*.tsx`; the OpenAPI client is regenerated per the README steps.

## 9. Phases (each is shippable on its own)

1. **Foundations**: migration, consent/unsubscribe page and headers, suppression list, permissions, global pause, audit entries.
2. **Segments**: field registry, rule compiler, builder UI, live count/sample.
3. **Copies**: library, merge tags, preview, test send.
4. **Campaigns**: segment + copy + schedule, paced delivery, activity log. *This alone answers "email our current users who've done little, right now".*
5. **Workflows**: engine tick, enrolments, wait/condition/goal exit, step builder UI, existing-user backfill.
6. **Measurement and polish**: opens/clicks (tracked link redirect), goal-conversion per workflow, A/B subject lines, AI-assisted drafting, optional event table for behaviour that existing tables don't capture.

## 10. Tests

Per phase, in the existing pytest style: rule compiler (each field, AND/OR, date windows), unsubscribe and suppression honoured, frequency cap, send-at-most-once under retry, goal exit stops later steps, backfill pacing, merge-tag validation, and a rendered-email snapshot. Frontend: builder unit tests and the admin build/lint gate.

## 11. Decisions needed before building

1. **Consent for existing users.** Do the Terms/Privacy accepted at sign-up cover product marketing email? If not, existing users get a one-time notice or only "product tips" category mail until they opt in. (Legal call; I'd treat it as required before phase 4 goes live.)
2. **Sending identity.** New subdomain on Resend (recommended) or the existing `EMAIL_FROM`?
3. **Timezone.** Per-user country timezone for send windows (recommended), or one fixed operator timezone?
4. **Segment time basis.** Is "joined" the user's `created_at` or the workspace's? (Today these are effectively 1:1.)
5. **Who gets access.** New `marketing.*` permissions for specific roles, or operators only to start?
6. **Which first workflow.** Suggested starter: *Day 1 welcome -> day 3 "make your first video" (exit on first video) -> day 7 credits nudge*, built entirely as the first real test of phase 5.
