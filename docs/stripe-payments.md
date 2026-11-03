# Stripe card payments

Customers can pay for credits by card. They pay on Stripe's own page, and the credits are added to their wallet
automatically once Stripe confirms the payment. No card number ever reaches our servers.

Stripe sits beside the existing methods: bank transfer (finance approves each one) and Nuvion naira options are unchanged.
Stripe is the USD card method and is on whenever `STRIPE_SECRET_KEY` is set.

## How a payment flows

1. The customer picks an amount on **Billing** and chooses **Card**, then **Buy**.
2. `POST /v1/billing/checkout` makes our `Checkout` row (provider `stripe`) and a Stripe Checkout Session for exactly that
   amount in USD, then sends the customer to Stripe.
3. Stripe calls `POST /v1/webhooks/stripe` (`checkout.session.completed`). We check the signature, ask Stripe for the session,
   confirm it is paid and that the amount, currency and checkout id match, then `handle_payment_event()` adds the credits
   once and writes the ledger row. The customer also gets the "Credits added" email.
4. The customer lands on `/billing/stripe/<id>`, which asks our server (which asks Stripe) until the payment is confirmed.
   If the webhook is late the page still settles the payment. A scheduled job (`reconcile_pending`) also settles any that were missed.
5. If the customer backs out, the session is closed and nothing is charged.

Credits are never granted from the browser's return URL, only from Stripe's own word (signed webhook or direct lookup).

## Amounts

- Lowest amount: **$10** (`MIN_FUND_USD`).
- The **$1** preset is the test amount. It is offered only in the sandbox (a Stripe test key, or local development) and
  disappears by itself when a live key (`sk_live_...`) is used. Nothing needs to be changed at launch.
- Presets come from `CREDIT_PURCHASE_USD`; custom amounts keep their $10 minimum.

## Set-up (sandbox first)

1. In Stripe, stay in **Test mode** (sandbox) and copy the secret key (`sk_test_...`).
2. Add a webhook endpoint for `https://<api-host>/v1/webhooks/stripe` with these events:
   `checkout.session.completed`, `checkout.session.async_payment_succeeded`, `checkout.session.async_payment_failed`,
   `checkout.session.expired`. Copy its signing secret (`whsec_...`).
3. Set these variables on the **staging** service (Railway). Never commit them or paste them into chat:

   | Variable | Value |
   |---|---|
   | `STRIPE_SECRET_KEY` | `sk_test_...` |
   | `STRIPE_WEBHOOK_SECRET` | `whsec_...` |

4. Redeploy. Billing now shows **Card** with a test-mode note.

## Testing in the sandbox

| Card | Result |
|---|---|
| `4242 4242 4242 4242` | Succeeds |
| `4000 0000 0000 0002` | Declined |
| `4000 0025 0000 3155` | Asks for 3D Secure |

Use any future expiry date and any 3-digit security code. Check that: the credits land and the balance goes up,
the "Credits added" email arrives, the ledger shows a "Purchase" row, the payment shows under **Payments**, a
declined card adds nothing, and backing out of Stripe's page adds nothing.

## Going live

1. Create the live webhook endpoint in Stripe (live mode) and copy its `whsec_...`.
2. On the **production** service, set `STRIPE_SECRET_KEY=sk_live_...` and the live `STRIPE_WEBHOOK_SECRET`.
3. The $1 amount disappears automatically. Make one real $10 payment and check the credits.

The service refuses to start in production with a test key, or with a key but no webhook secret.

## Local development

`STRIPE_API_URL` can point at a stand-in Stripe (local development only; it must be Stripe's own address everywhere else).
Without a key, Stripe is off and nothing changes.

## Not included

Refunds, receipts and invoices, saved cards, subscriptions, and Stripe for naira.
