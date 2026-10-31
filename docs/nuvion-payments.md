# Nuvion USD credit purchases

## What is implemented

Set `BILLING_PROVIDER=nuvion` to use the Nuvion adapter. Credit options remain the existing fixed USD amounts and exchange rate to app credits. The server snapshots the price/credits and Nuvion receiving account, entity and API environment when creating a checkout. The customer is sent to `/billing/card/<checkout-id>`.

Card numbers, expiry, security codes and cardholder names are encrypted in the browser with RSA-OAEP/SHA-256 using the public key supplied by the authenticated checkout API. Plaintext card numbers and CVVs are never sent by the client to Cover Founder's API, stored, or placed in URLs. Payment bodies are excluded from request telemetry. No secret API key is exposed to the client. There is no saved-card feature or Apple Pay UI in this release.

Nuvion Payment Intent amounts are integer USD cents. A local checkout commits before remote intent creation. The checkout ID is the unique remote reference, and retries look up that reference instead of creating unrelated payment intents. Card confirmation is claimed atomically before the external request: a double click, timeout or process restart cannot immediately submit another card confirmation. A definitive rejection can reopen entry only after a fresh provider lookup proves the intent still requires action and has no intent actions. Ambiguous errors require at least two minutes plus the same provider checks. Unknown list responses and existing 3DS/processing actions keep confirmation locked. Recovery never resubmits a card automatically: the customer must enter their card again and explicitly click Pay.

Nuvion may redirect to `app.nuvion.dev` or `app.nuvion.co` for 3DS. Return URL query parameters are never payment evidence. The backend retrieves the current intent and matches its ID, reference, account, entity, USD currency and exact amount to the saved checkout. The nested confirmation action must also be completed, bound to that intent and account, match the USD charge and have no refund. Only then does the existing credit ledger grant the purchased credits. Settlement is serialized and idempotent across simultaneous browser requests, webhook retries and scheduled reconciliation.

Pending payments are accessible from Billing → Card payments. The return page polls processing payments; processor verification is throttled. The existing scheduled `jobs.sweep` also reconciles pending confirmations to recover missed webhooks. Failed/declined/cancelled payments add no credits. Refund execution, chargeback handling and automatic reversal of already-spent app credits are not implemented: operators must manage refunds with Nuvion and adjust the app ledger under the business's refund policy. Resolve that operational policy before live launch.

## Configuration (secure values, never chat or source code)

Nuvion documents separate environments:

- Sandbox dashboard: https://app.nuvion.dev/dashboard/settings
- Sandbox API: `https://api.nuvion.dev` (no real funds)
- Production dashboard: https://app.nuvion.co/dashboard/settings
- Production API: `https://api.nuvion.co`

A live key does not establish sandbox access. Use a separate sandbox key and its matching public encryption key for external testing. Account verification does not establish that card acquiring is enabled; confirm that with Nuvion.

Required settings in the backend's runtime environment:

| Setting | Purpose |
| --- | --- |
| `BILLING_PROVIDER=nuvion` | Enables new Nuvion purchases. Keep existing `manual` mode until configuration and provider checks are complete. |
| `NUVION_API_URL` | Exact official sandbox or production API URL. Production runtime rejects sandbox payments. |
| `NUVION_API_KEY` | Secret key permitted to create/read Payment Intents and Intent Actions and verify actions; a read-only Developer key cannot create payments. |
| `NUVION_PUBLIC_KEY` | Matching RSA public PEM key, at least 2048 bits. Use real newlines or literal `\n` line breaks. This key is public, not the API secret. |
| `NUVION_ACCOUNT_ID` | Approved receiving USD account belonging to the configured entity. |
| `NUVION_ENTITY_ID` | The merchant entity that owns that receiving account. |
| `NUVION_WEBHOOK_SECRET` | Raw webhook signing secret, at least 24 characters, available to local HMAC verification. Must not be only a proxy placeholder. |

Cloud environment draft requirements are separate from Railway production variables. Saving requirements does not supply secret values, publish the environment, configure Railway or enable live payments. Secret API bindings may use the HTTPS proxy to the official API hosts. The webhook secret must be set as a runtime value available to the application, since verification is local. Enter it securely in settings, never in chat. Rotate any API secret previously shared in chat, and use the public encryption key associated with the replacement API key.

Apply migration `0023` with the existing `alembic upgrade head` pre-deployment command before starting the new application. No new dependencies are needed. The adapter remains unused while `BILLING_PROVIDER=manual` or `mock`. Already-started Nuvion payments can still be verified after switching new purchases back to `manual`, provided Nuvion settings remain configured; don't remove verification credentials while payments are pending.

## Webhooks

Register `POST https://www.coverfounder.com/v1/webhooks/nuvion` (or the equivalent backend URL) for `payment_intent.completed`, `payment_intent.failed` and `payment_intent.cancelled`. The legacy `/v1/webhooks/billing` path delegates to the same online verification when Nuvion is selected. Use a separate endpoint/secret per environment.

Nuvion signs `{timestamp}.{raw-body}` using HMAC-SHA256. The app checks `x-nuvion-event-signature`, `x-nuvion-event-timestamp` and `x-nuvion-event-id`, allows the documented short retry window, then reads current provider state before granting credits. A signed event claiming completion while the remote intent is pending grants nothing. No webhook callback or browser response can choose the workspace, purchased credits or price.

Nuvion retries only twice (three deliveries total) and may blacklist failing endpoints. Keep the scheduler running and inspect webhook delivery status in Nuvion. On configuration or transient failures the endpoint returns a retryable error rather than acknowledging an unprocessed payment as settled.

## Validation and activation

Local API tests use `httpx.MockTransport` implementing the documented provider contract, never a live key. Browser tests verify RSA encryption by decrypting captured ciphertext with a disposable test key and verify that forged successful-return parameters cannot display confirmed payment without a server response. The full local suites should be run before deployment.

External activation still requires actual credentials, account/entity identifiers and a registered webhook. Confirm account ownership and USD currency with read-only provider requests; verify Nuvion accepts the chosen card-collection/PCI approach. Then use provider-approved sandbox test cards to check success, decline, 3DS, delayed completion, duplicate notifications, refund policy and recovery. A sandbox or live card purchase has not been verified merely because these local tests pass. Live charge testing needs an agreed test payer and amount; do not charge a real card without explicit authorization.

Official references: [Card payments](https://docs.nuvion.co/guides/accept-card-payment), [Payment Intents](https://docs.nuvion.co/api-reference/payment-intents), [Webhooks](https://docs.nuvion.co/webhooks/overview), [Authentication](https://docs.nuvion.co/authentication), [Encryption](https://docs.nuvion.co/core-concepts/encryption).


## Live setup verification

The replacement credential was verified against the live account API and passed the payment-write permission probe. A uniquely referenced USD 10 Payment Intent was created without any Intent Action, then immediately cancelled and retrieved to confirm `cancelled` with no card confirmation. No card was supplied and no money moved. This validates intent creation, account routing, lookup and cancellation; it does not validate card acquiring, 3DS or settlement.

The selected receiving account was confirmed by the owner as “Onyeka Akumah USD”. Exact account/entity identifiers belong in environment settings, not application code. The runtime payment key cannot manage webhooks (the API returns a permission denial), so registration must be completed from the Nuvion dashboard by an authorized user, or with a separately authorized setup credential.

The callback acknowledges `webhook.health` without payment credentials to permit endpoint registration before installing Nuvion's generated signing secret. This is reachability-only: financial events still require full configuration, a valid signature and online verification. Leave `BILLING_PROVIDER=manual` until Railway has the matching secret API key, public encryption key, verified account/entity IDs and the actual signing secret generated when the webhook is registered.

## NGN purchases (additional implementation)

The USD credit packages and credit calculation are unchanged. `NGN_PER_USD` defaults to `1400`; packages display ₦14,000 / ₦70,000 / ₦140,000 / ₦280,000 for $10 / $50 / $100 / $200. This is the platform's selling rate, not a provider-executed currency conversion. NGN collections stay in the selected NGN account. No FX transfer or payout is initiated.

Billing offers USD/NGN selection and separate NGN card/bank-transfer methods. `/v1/billing/payment-methods` exposes availability and the current rate. The browser sends the rate it displayed; the server rejects stale quotes and computes the payable amount itself. Each local checkout stores its currency, NGN amount, rate and receiving-account snapshot in `payment_context`; existing USD checkouts continue to use their original shape. No database migration is required. Changing the selling rate affects new checkouts only.

Required additional Railway settings are `NUVION_NGN_ACCOUNT_ID` (the owner selected “Onyeka Akumah NGN”), `NGN_PER_USD=1400`, and independent `NUVION_NGN_CARD_ENABLED` / `NUVION_NGN_BANK_ENABLED` switches. Both switches default to false. Keep USD enabled. A configured NGN account does not prove NGN card acquiring or acceptance of Nigerian-issued cards; get confirmation from Nuvion before enabling that switch. Card intents use NGN kobo, the NGN receiving account, and the same encrypted-card/3DS/online verification flow. The gateway's exact charged currency and amount must match the saved NGN quote before granting the saved USD package's credits.

Nuvion's [funding-session reference](https://docs.nuvion.co/api-reference/funding-session) explicitly says hosted Open Banking on an NGN account returns a dependency-unavailable error. Bank transfers therefore use Nuvion's documented [provisioned account details](https://docs.nuvion.co/guides/accept-with-account-details). The server retrieves active NGN bank coordinates with inflows enabled before creating the local order. It creates no accounts and initiates no debit, payout or transfer. Instructions show the exact amount and unique `CF<checkout-id>` narration with copy controls. The live API omits the beneficiary name on the selected receiving details, so the UI labels the account display name accurately and asks payers to confirm the beneficiary returned by their bank.

Add **`inflows.completed`** to the existing Nuvion webhook subscription at `https://www.coverfounder.com/v1/webhooks/nuvion`. The existing signing secret applies if editing the existing subscription. If creating a new webhook instead, configure its actual signing secret appropriately; one app setting cannot validate two independently generated secrets. The runtime key can read transfers but cannot manage webhooks, so edit the subscription in the Nuvion dashboard.

Signed bank callbacks are wake-up signals only. The server retrieves `/transfers/{id}` and requires a successful NGN bank-transfer inflow, exact merchant account/entity, exact amount in kobo, creation after the checkout, and exact order narration. A transfer can only settle the order named by that verified narration. It binds the provider transfer ID before using the existing atomic wallet settlement. Repeated callbacks or status checks cannot grant twice. Unexpected amounts, missing/altered narrations and payments without an order reference remain uncredited and require operator review; a receipt or a customer clicking “Check transfer status” is never sufficient evidence. A duplicate extra transfer to an already-paid order does not buy additional credits automatically. Operators must resolve that under the refund/support policy.

The authenticated bank status page and scheduled reconciliation scan settled bank inflows, using amount/date/account filters and pagination, to recover missed notifications. Scans are throttled to once per 15 seconds per checkout and capped at 10 pages. The webhook remains the primary path; the scan cap is a recovery limit, not proof that no payment exists. Do not promise reliable automatic matching if a bank cannot preserve the full narration; investigate dedicated customer/order account details with Nuvion if this is common.

Read-only live checks confirmed an active NGN account with active inflow-enabled bank details and permission to list transfers. No live NGN card charge or bank transfer was performed. The NGN implementation is not live until deployed and its switches are configured. Use a payer-authorized test to verify narration preservation, bank posting, NGN acquiring, fees and actual settlement before making broad acceptance claims.

An additional live configuration smoke test created a ₦14,000 NGN Payment Intent on the owner-approved NGN account without any Intent Action or card. Nuvion returned `201` and `requires_action`; it was immediately cancelled and retrieved to confirm `cancelled`. This establishes NGN intent creation and cancellation, not Nigerian-issued card acceptance, 3DS or successful collection. No money moved.


## Payment recovery and finance review (migration 0027)

Bank webhooks and reconciliation now persist verified successful NGN inflows in a unique receipt registry. An altered narration remains uncredited automatically; amount alone never identifies a payer. A customer can submit the exact transaction reference from their bank receipt through the bank checkout's **Already transferred but not credited?** form. The server retrieves the settled transfer, checks the receiving account/entity, currency, amount and checkout date, and queues a review without granting credit.

In **Admin → Revenue → Payment reconciliation**, an operator with `finance.manage` can:

1. Refresh recent receipts from Nuvion (up to 50 transfers from the last 30 days per refresh). Webhooks and pending-checkout scans also collect receipts. A missing result in this bounded list is not proof no transfer exists.
2. Verify the payer's receipt and ownership independently, choose the correct pending purchase, record a meaningful reason, and confirm ownership. A customer claim is a review hint, not proof of ownership.
3. Match the transfer. The server fetches current provider data again and applies the checkout's saved credits through the existing ledger. Receipt allocation and checkout settlement are locked, so simultaneous requests or repeated callbacks cannot apply one transfer to multiple purchases. The original matching actor/time and an audit record are retained.
4. Recheck pending card or bank purchases without submitting a new charge.

Staff with only `finance.view` can inspect the report but cannot match or recheck. The report displays safe provider error types, HTTP status and request IDs. Logs/audits never include raw processor responses, plaintext card data, encrypted card payloads or API keys. Financial receipt records follow existing checkout retention; workspace exports include only that workspace's allocated receipts.

For the previously reported ₦1,400 receipt, verify the matching customer's $1 checkout before assigning it. The saved package grants **0.37 credits** at ₦1,400 per USD. Deployment of this code alone does not credit that payment; an authenticated finance operator must review and match it. Do not ask the customer to transfer again.

After deployment, have the authorized cardholder test the $1 USD purchase once. Verify the provider's completed intent/action, a paid checkout, exactly one 0.37-credit ledger entry, and a confirmation email. Repeat status checks must leave the balance unchanged. If the provider rejects the attempt, capture the new error type/request ID from the admin report and ask Nuvion to resolve acquiring/encryption/account restrictions as indicated. Application tests and successful intent creation do not establish successful live card acquiring. NGN card payments remain controlled by the existing availability flag; do not enable them solely because NGN intent creation succeeds.


## Custom credit quantities and distribution top-up

Billing retains the existing preset packages (including the owner-requested $1 test package) and adds a custom **credit quantity** field. Video-count estimates are no longer shown in billing. `POST /v1/billing/custom-quote` accepts a positive quantity with up to two decimal places and returns an authoritative USD amount, NGN equivalent, quoted rate and price-version hash. Custom purchases require at least $10 USD; at $2.70 per credit and 0.01-credit increments, the minimum custom quantity is 3.71 credits ($10.02). The separate $10 preset continues to grant 3.70 credits.

Custom checkout submits `custom_credits`, `amount_usd` and `custom_quote_version`. The server recalculates the price, rejects changed/missing/altered quotes, snapshots the requested credit quantity and price in the existing Checkout, and uses the same verified settlement and idempotent ledger path as presets. NGN card/bank availability and exchange-rate checks still apply. No provider call charges a user merely for requesting a quote. Amount bounds protect the existing Numeric(12,4) financial storage. No new database migration or payment credential is required.

At the configured $2.70 unit price and ₦1,400/USD, **220 credits = $594.00 = ₦831,600.00**. The exchange rate displayed in a custom quote is the one submitted for NGN checkout. A changed quote/rate must be reviewed before paying. Local Nuvion contract tests cover USD card, NGN card and NGN transfer settlement of this custom purchase; they do not constitute a real live card charge.

Distribution saves the review draft before checking the current wallet balance. An insufficient balance opens an accessible modal showing required credits, balance and shortfall, with a billing link that preserves the draft and suggests a sufficient custom quantity (at least the custom minimum). The atomic server-side deduction remains authoritative and reports the same shortfall popup if another tab spends funds after preflight. Successful card/bank checkout offers a direct return link to that distribution draft. Buying credits never submits a distribution automatically; the user reviews and clicks Pay and submit again.
