# Distribution requests and fulfilment

Customers start from a finished video or Distribution. Requests save drafts across outlet selection, video/announcement, contact/images, and review/payment. Submission uses the existing credit wallet; USD/NGN wallet funding remains in Billing.

## Operator setup

Open **Admin → Distribution → Notification and outlet settings**. `operations.view` permits inspection; `operations.manage` permits configuration, outreach, retries and fulfilment edits.

- Set multiple team notification addresses (one per line or comma-separated). The default list is empty; addresses are never guessed. Changes apply to future submissions.
- Select each outlet and set its placement credits, logo acceptance/fee and additional-picture acceptance/fee per picture. Initial placement prices remain zero. Unconfigured image policies are shown as awaiting confirmation and do not authorize image charges or forward images to publishers. Save the actual publisher terms before enabling outreach.
- Set the publisher contact name/email. Enable automatic outreach only for direct-access outlets. A valid email is required.
- Edit and save each outlet's plain-text email subject/body. Supported placeholders are listed in the UI. Templates reject unsupported field access, format directives, blank content and multi-line subjects. The default subject is a publication enquiry; the opening paragraph describes the sponsorship request and asks for publication confirmation, timeline, fee and bank/payment details. It distinguishes payment to Cover Founder from publisher payment.

Configuration is stored in the existing `SystemSetting` row `distribution_fulfillment`, not an environment variable. Publisher replies continue to use the existing email provider's `EMAIL_REPLY_TO`/sender mailbox; ensure that mailbox is monitored. Replies, negotiation, bank details and actual publisher payments are handled outside this app. No inbound email reader or bank payout is implemented.

## Authoritative pricing and safe payment

The 47 existing Africa catalogue IDs are stable; six additional Nigerian news outlets use IDs 48–53; other listed regions remain coming soon. Server quotes include base placement credits plus an accepted/selected logo fee and a fee per additional picture accepted/selected by each outlet. Company logo upload is optional. Customers can continue and submit without a logo; no logo fee applies when none is uploaded. The customer can opt out of sending a logo or pictures separately for each outlet. Unsupported/unconfirmed images are excluded from that outlet's publisher materials and add no fee.

Prices and selected media are shown before payment. The browser submits its displayed total and catalogue version. Stale amounts or changed image policies require review, even if a draft autosave has already refreshed the stored total. The server derives charges itself, rejects totals outside the database's monetary range, locks the workspace wallet and atomically claims/debits/submits the request. Insufficient funds leave a draft and queue no sale/publisher emails. Duplicate/concurrent submissions cannot debit twice. Zero-credit orders are accurately identified as no-charge confirmations.

Submission stores immutable outlet/fee/media snapshots, creates one placement per outlet, and queues notifications in the same transaction as payment. Later configuration changes cannot change paid totals or rewrite queued/sent messages.

## Customer confirmation and receipt

The requester and primary contact receive separate, deduplicated confirmation messages with outlet-by-outlet placement/logo/picture charges, total credits, a permanent `CF-DIST-<request-id>` confirmation number and payment reference. They retain the 24-hour contact promise at submission.

The authenticated request page provides a downloadable, printable HTML receipt/credit invoice with the same breakdown and reference. This records payment from a credit wallet; it is not a second USD/NGN card charge or a tax/VAT invoice. Receipt downloads require workspace ownership. The dashboard lists published press links and the distribution detail page tracks every selected outlet. Customer views never include publisher contact addresses, email logs, internal notes or publisher-payment flags.

## Team and publisher messages

Configured team recipients receive the paid/no-charge indication, complete customer contact information, selected outlets and costs, full announcement, video project, image counts, signed video/logo/picture download links and a secure back-office link for reviewing submitted materials.

Direct-access outlets automatically receive their saved, rendered publisher email after successful submission. Publisher material links include the selected video and only that outlet's accepted/selected logo/pictures. Signed material links expire after seven days. Admins can edit the rendered recipient, subject and body per placement, save them and explicitly send an additional email/follow-up. Refresh expired materials manually before sending old drafts. Each send has an idempotency key; retrying the same action does not queue a second message.

The admin request detail contains message subjects/bodies, recipients, pending/sending/sent/failed state, attempts, sent time, errors and a request activity timeline. Editing a draft email does not rewrite sent history. Sent means the configured provider accepted the message, not proof of inbox delivery or a publisher reply.

## Per-outlet status and publication

Customer-visible statuses are **Pending**, **In progress** and **Published**. Admin-only progress includes **Not started**, **Follow-up done** and **Publisher payment made**, plus private notes. Publisher payment is a staff-entered record only; it does not move money or change a customer's payment status.

Saving a new valid HTTP(S) publication URL marks that outlet Published and queues emails to the requester/contact with the outlet name and link. URLs cannot contain credentials or unsafe schemes. Multiple outlets are tracked independently, with separate publication notifications; repeating the same URL update does not send duplicates. The overall request completes only after its placements are published. Concurrent outlet updates are serialized at the request level so the roll-up remains correct. Customer progress refreshes automatically; links also appear on their dashboard.

## Delivery reliability and privacy

A durable per-recipient outbox commits before sending. Post-response delivery keeps email outages off the payment path; the existing `jobs.sweep` retries pending/failed messages and recovers sending leases older than ten minutes. Workers claim each message before calling the provider and hold no database transaction across the network call. Automatic attempts stop at eight; an authorized admin can retry a specific failed message without resetting its attempt history. A bounded processing window leaves remaining work queued for the next sweep. Exhausted messages cannot starve newer requests. Messages already marked sent are not resent during ordinary retries.

Delivery is at least once: a process crash after provider acceptance but before saving success can still produce a repeat email. The configured provider interface has no delivery idempotency receipt. Wallet debits remain independently idempotent. Payment is retained when an email fails. Logs show the failure and permit recovery.

Workspace export includes public outlet progress/links. Workspace erasure removes its distribution placements, outbox messages and activity records along with the original request data. Private publisher/admin fields are excluded from customer responses.

## Migration and rollout

Apply migration **0024** using the existing `alembic upgrade head` pre-deploy command. It creates placements, outbox and activity tables and backfills paid legacy requests without queuing historical emails or retroactive publisher outreach. Legacy completed orders retain their published status but may lack a recorded URL/contact/draft; staff can add these. Successful old confirmations are not automatically reissued. Downgrade removes new fulfilment tables while preserving original requests and payment records.

This implementation has not been deployed as part of this task. Configure real team recipients, publisher contacts, actual fees/image policies and a monitored reply mailbox before relying on production outreach. Local tests use the mock email provider; no messages were sent to real team members or publishers.

Validation covers paid/free/insufficient-funds paths; stale quote and fractional media charges; duplicate/concurrent submission and outreach; per-recipient failure/retry and stale leases; template validation and permissions; private internal status; safe publication links and multi-outlet roll-up; receipt download/privacy; workspace export/erasure; and complete browser journeys from payment to publisher email, follow-up, publication, customer email and dashboard links. Migration upgrade, legacy backfill, schema check, downgrade and re-upgrade were tested on a disposable SQLite database.


## Owner-supplied placement prices

The Credit on CF column supplied on 30 October 2026 sets the base placement credits for outlets 1–17: `42, 83, 124, 69, 97, 61, 138, 28, 42, 42, 28, 28, 42, 42, 42, 42, 42`. These are the first 12 media outlets and five crypto channels. The other outlets retain their existing defaults until prices are provided. These values are credit units, with the existing configured logo/image add-ons applied separately when selected.

Migration `0026` updates only the placement-credit field in existing overrides for these 17 outlets, preserving contacts, email templates and media policies. It does not create media-policy confirmations for previously unconfigured outlets or rewrite paid requests. Old override credits are recorded for rollback; rollback preserves later admin pricing edits. Current UI totals, saved quotes, invoices and wallet deductions use the authoritative catalog, with stale-quote protection still in place.

The Nigerian news spreadsheet rollout (migration 0028) uses the final **CF Credit + Margins** column as the placement credit price. Its five-credit margin is already included and is not added a second time. Decimal prices are preserved. Existing publisher contacts, media fees and policies remain intact; paid distribution requests keep their original price snapshots. Earlier tech/crypto pricing is unchanged.

Distribution step navigation appears at both the top and bottom, with separators, completed-step styling and an accessible active step. Advancing still validates the preceding required fields. The review payment action saves the draft, checks a fresh wallet balance and opens a shortfall modal when more credits are required; the existing atomic server check remains the final authority. Billing and successful payment screens link back to the saved draft.
