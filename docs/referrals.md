# Referral rewards

Each verified new user receives a unique, random 24-character referral code. Existing users receive a persistent code on their first visit to **Referrals** (`/referrals`). The share URL uses the configured public app origin: `/signup?ref=<code>`. Codes are public sharing identifiers, not login credentials.

Open business signup accepts an optional `referral_code`. The server resolves it to an active referrer and saves it alongside the emailed signup code. Browser tab storage retains the referral during navigation/resends; the verified email code determines attribution. The verification request cannot replace the inviter. Invalid, unknown, deleted or suspended referrers do not prevent ordinary signup and earn nothing. Workspace invitation signups earn no referral reward.

After email verification creates a new business workspace and user, the same transaction records a `referral_rewards` row and grants exactly **1 credit** to the referrer's workspace through the existing append-only ledger. There is no purchase requirement, expiry or separate referral balance: rewards are ordinary spendable wallet credits. The referred business retains its existing signup credit policy unchanged.

The emailed code is claimed atomically. A unique reward per referred workspace, an idempotent ledger reference (`referral:<referred-workspace-id>`), and a serialized referrer-wallet update protect against repeated verification and simultaneous referrals. Signup failures roll back the reward. Existing-account signups and same-user/same-workspace referrals cannot earn credits. Email verification establishes control of an address; it does not independently prove that two different verified addresses represent unrelated businesses.

The authenticated referrals endpoint exposes only the current user's referral link, lifetime completed count/credits and latest 100 credited businesses. It never exposes the referred person's email. The UI supports copy/share, mobile layouts and live refresh of referral totals and wallet balance. Referral awards also create `referral.rewarded` audit records identifying the referring user and referred workspace.

Migration **0029** adds `referral_links`, `referral_rewards` and nullable `auth_codes.referral_code`; existing signup codes and accounts remain valid. Workspace exports include their referral reward direction and amounts. Deletion removes that workspace's users' public links and anonymizes user pointers on retained reward records; financial ledger entries remain under the existing retention policy. Deleted businesses appear as “Deleted business” to prior referrers.

Validation covers referral sharing through actual signup/verification, no credit before verification, stable and isolated links, new-user link allocation, invalid/expired codes, resends, attribution tampering, existing accounts, invitation exclusion, duplicate verification, parallel signups and privacy deletion/export. Provider payment credentials are not used by this feature.

## What a referrer earns (from 4 November 2026)

**Every time a business that signed up through a referral link buys credits, the business that referred it is credited 5% of those credits,
on every purchase, for as long as the referred business keeps buying.** This replaced the earlier 1-credit signup reward and the 4-credit
first-distribution bonus: signing up pays nothing by itself.

- It is a plain wallet credit (ledger kind `grant`, reference `referral-purchase:<checkout id>`), granted in the same transaction that adds the
  buyer's credits, so a repeated payment event can never pay it twice. The buyer receives everything they paid for; the reward is on top.
- Example: a $50 purchase buys 18.52 credits, so the referrer earns 0.93 credits (5%, rounded to the nearest 0.01; a purchase too small to
  round to 0.01 pays nothing).
- It applies to every way of buying credits that goes through payment confirmation: card (Stripe and Nuvion) and approved bank transfers.
  Credits an operator adds by hand in the back office, and credits earned or given away, never earn a share.
- Only an active referrer earns it: a deleted or suspended referrer earns nothing.
- The referrer is emailed ("You earned 0.93 credits") and the Referral page shows credits earned in total and from each business.
- The rate is the `REFERRAL_PURCHASE_PERCENT` setting (default 5; 0 turns it off). `REFERRAL_SIGNUP_CREDITS` (default 0) can still give a fixed
  credit at signup if ever wanted. Who referred whom is recorded at signup either way (`referral_rewards`).
- A business's running total from its referrals is kept on its `referral_rewards` row (`credits`).
