# Bank transfer credit purchases

New purchases use USD or NGN bank transfers when `BANK_TRANSFER_REVIEW_ENABLED=true` (the default). Card checkout is marked **Coming soon** and new card confirmations are rejected server-side. Existing card payments and legacy NGN transfers retain their verified settlement and reconciliation paths; switching modes does not discard an already completed payment.

## Customer flow

1. Choose a fixed package or a custom credit quantity. Custom purchases start at the equivalent of USD 10. Prices and the NGN conversion rate are validated by the server and saved with the purchase.
2. Transfer the exact displayed amount using the unique CF narration. Receiving instructions are snapshotted at checkout.
3. Click **I have paid**, upload a PNG, JPEG or PDF receipt (maximum 5 MB), then submit it for approval. An optional payer bank reference helps the reviewer match it.
4. The payment remains **Awaiting approval**, with no wallet credit. The page says credits will be added in a few minutes **once the team confirms the transfer**. Review timing depends on a team member being available.
5. Approval credits the wallet once, updates payment and credit history, and emails the customer. Rejected receipts show the reason and allow a corrected receipt for the same purchase; customers should contact the team before paying again.

## Back office

In **Revenue → Bank transfer approvals**, staff with `finance.view` can inspect purchases and private receipts. Staff need `finance.manage` to approve or reject. Before approving they must check the receiving bank statement, enter the actual bank transaction reference, record a verification note, and explicitly confirm funds arrived. A receipt alone is never payment verification.

Configured operator/owner addresses and every active staff member with `finance.manage` receive action-required emails upon submission. Suspended/revoked staff are excluded. Email delivery status and attempts appear with the purchase. Approval and rejection are audited with the actor and time.

Staff with `settings.manage` can edit USD and NGN receiving instructions in the same section. Initially the system reads the approved Nuvion receiving accounts already configured for the application. It verifies the account currency, entity, active details and inflow status. Unknown beneficiary names are not invented; an account label is displayed separately. Saved overrides apply to future purchases only. Disable an account to stop new purchases in that currency.

## Integrity and operations

Migration `0031_transfer_review` creates private payment-proof records, review decisions and a durable notification outbox. Apply migrations before deploying the application.

Uploaded bytes are checked for size, declared format, active PDF content and malware. The server copies accepted evidence to an immutable verified object; customer upload URLs cannot overwrite reviewed evidence. Receipt links are short-lived and access to their generation is workspace/permission checked. Workspace privacy exports include receipts; deletion removes proof files and identifying review/email data while retaining required financial records.

Approval locks the purchase, checks the expected receipt revision and uses the existing atomic wallet ledger settlement. Unique bank references per receiving account and unique approved receipt hashes prevent reuse. References already matched by legacy transfer reconciliation are rejected. Repeated approvals do not grant more credits. New manual-review purchases have provider `manual_bank`, separate from automated Nuvion purchases.

Submission/decision emails are committed in the same transaction as their state change and attempted after commit. The periodic sweep retries pending/stale deliveries, up to ten attempts. Admin screens expose failed delivery status. Mail failures do not undo or duplicate a wallet credit. As with other email delivery systems, a provider accepting a message immediately before a process crash can cause a duplicate retry; wallet settlement remains idempotent.

Local backend tests explicitly enable the production review mode in `test_transfer_review.py`. Existing legacy payment tests keep their old mode to test compatibility. Run the new browser journey with:

```bash
BANK_TRANSFER_REVIEW_ENABLED=true pnpm e2e transfer-review.spec.ts
```

The browser test uses a disposable local database, mock storage and mock email, and makes no real transfers or card charges.

The payment instructions include a recipient display ending in `/ Sydney Money Technology Inc` unless that name is already present. This supplements the existing account identity; the verified beneficiary, account number, routing and stored receiving-account snapshot are not modified.
