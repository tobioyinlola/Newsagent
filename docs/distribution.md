# Distribution requests

A completed video's page links to `/distribution/request?project=<id>`. The customer sidebar also lists Distribution. Starting a request immediately creates a server-side draft. The four steps are outlets, video/announcement, primary contact/images, and review/payment. Fields autosave after a short delay; Continue and Save draft explicitly persist changes. Existing drafts and submissions remain accessible from the request list.

## Available outlets and pricing

`backend/app/routes/distribution.py` contains the initial 47 distinct Africa catalogue entries. Premium Times appears once. All outlets currently cost **0 credits**. United States, Canada, and United Kingdom are marked coming soon and cannot be selected. Catalogue IDs are persistent: append new entries rather than reordering existing ones. Submitted requests snapshot outlet names and prices. These are requests for manual fulfilment, not API integrations with publishers or guarantees of placement.

Pricing and total calculation are authoritative on the backend. Before introducing nonzero prices, review the catalogue, set the per-outlet prices, and validate the intended commercial offer. A changed quote requires review before submission. There is no new payment-provider integration: paid requests use the existing credit wallet and ledger. The existing Billing screen remains responsible for top-ups; a return link restores the saved distribution request. Nuvion integration is still paused.

## Submission and wallet safety

Draft ownership is checked on every customer endpoint. Only a completed video from the same workspace and clean, checked uploads from that workspace can be used. Logo and all four contact details are required; additional pictures are optional (up to ten). Images reuse the existing signed upload, file-type verification, size limits and malware checking.

Pay and submit atomically claims the draft, locks the wallet, checks the server-calculated total, deducts through the existing append-only ledger, and marks it paid/submitted. Repeated or concurrent submissions do not debit twice. Zero-credit submissions are marked paid without adding a zero-value ledger transaction. Insufficient credit leaves the request as an unpaid review-stage draft and returns 402. Submitted content is immutable to customers.

## Notifications and operations

The requester and primary contact receive the confirmation email, including the promise that the Cover Founder team will reach out within 24 hours. Failed email delivery does not undo submission/payment. The persisted `email_sent_at` field records successful delivery through the configured provider, and pending messages are retried by the existing `run_sweep` scheduled job. Email delivery is at least once: a crash after delivery but before recording it may cause a repeat email. Operators can also retry pending confirmations in the back office. Real delivery depends on the existing email provider configuration; local validation uses the mock mailbox.

`/admin/distribution` shows unpaid drafts and paid submissions, their current stage, last activity, creator, contact details, release text, selected outlets and prices. Operators with `operations.view` can inspect requests and load short-lived download links for video/logo/images. `operations.manage` is required to retry emails or update fulfilment to submitted, in progress, or completed. Drafts cannot be marked completed without payment. Submission and status updates are audited. Workspace export includes distribution data; account deletion removes its distribution/contact records.

## Deployment and verification

Apply migration `0022` using the existing pre-deploy command `uv run alembic upgrade head`. No new environment variables or external publisher credentials are required. Scheduled notification retries require the existing scheduler/worker workflow; the manual admin retry remains available independently. No production deployment was performed as part of implementation.

Checks:

- Backend: `uv run pytest -q tests/test_distribution.py` covers free/paid requests, concurrent debit protection, insufficient funds and retry, saved drafts, tenant isolation, checked assets, required fields, price changes, status access and email retries.
- Browser: `CHROMIUM_PATH=/usr/bin/chromium pnpm e2e distribution.spec.ts` runs a completed video through outlet selection, selection summary, draft recovery, custom announcement, logo/images, submission, confirmation email and back-office status/downloads.
- Migration: apply to a disposable database, run `alembic check`, downgrade to `0021`, and upgrade again.
