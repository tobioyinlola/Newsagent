# Referral rewards

Each verified new user receives a unique, random 24-character referral code. Existing users receive a persistent code on their first visit to **Referrals** (`/referrals`). The share URL uses the configured public app origin: `/signup?ref=<code>`. Codes are public sharing identifiers, not login credentials.

Open business signup accepts an optional `referral_code`. The server resolves it to an active referrer and saves it alongside the emailed signup code. Browser tab storage retains the referral during navigation/resends; the verified email code determines attribution. The verification request cannot replace the inviter. Invalid, unknown, deleted or suspended referrers do not prevent ordinary signup and earn nothing. Workspace invitation signups earn no referral reward.

After email verification creates a new business workspace and user, the same transaction records a `referral_rewards` row and grants exactly **1 credit** to the referrer's workspace through the existing append-only ledger. There is no purchase requirement, expiry or separate referral balance: rewards are ordinary spendable wallet credits. The referred business retains its existing signup credit policy unchanged.

The emailed code is claimed atomically. A unique reward per referred workspace, an idempotent ledger reference (`referral:<referred-workspace-id>`), and a serialized referrer-wallet update protect against repeated verification and simultaneous referrals. Signup failures roll back the reward. Existing-account signups and same-user/same-workspace referrals cannot earn credits. Email verification establishes control of an address; it does not independently prove that two different verified addresses represent unrelated businesses.

The authenticated referrals endpoint exposes only the current user's referral link, lifetime completed count/credits and latest 100 credited businesses. It never exposes the referred person's email. The UI supports copy/share, mobile layouts and live refresh of referral totals and wallet balance. Referral awards also create `referral.rewarded` audit records identifying the referring user and referred workspace.

Migration **0029** adds `referral_links`, `referral_rewards` and nullable `auth_codes.referral_code`; existing signup codes and accounts remain valid. Workspace exports include their referral reward direction and amounts. Deletion removes that workspace's users' public links and anonymizes user pointers on retained reward records; financial ledger entries remain under the existing retention policy. Deleted businesses appear as “Deleted business” to prior referrers.

Validation covers referral sharing through actual signup/verification, no credit before verification, stable and isolated links, new-user link allocation, invalid/expired codes, resends, attribution tampering, existing accounts, invitation exclusion, duplicate verification, parallel signups and privacy deletion/export. Provider payment credentials are not used by this feature.

## Distribution bonus

On top of the 1 credit for a verified signup, the referrer earns **4 more credits, once per referred business**, the first
time that business **pays for a distribution** (a distribution request that costs credits; a no-charge request does not count).

- It is granted in the same transaction as the paid distribution, as an ordinary wallet credit (ledger kind `grant`, reference
  `referral-bonus:<referred-workspace-id>`), so a retry, a double click or a second paid distribution can never pay it twice.
- It is only given to an active referrer. A deleted or suspended referrer earns nothing.
- The referrer gets an email ("You earned 4 bonus credits") and the Referral page shows which referred businesses have paid.
- Both amounts are settings: `REFERRAL_SIGNUP_CREDITS` (default 1) and `REFERRAL_DISTRIBUTION_BONUS_CREDITS` (default 4; set 0 to turn the bonus off).
- No database migration was needed: the bonus is recorded in the ledger.
- "Referral" now sits in the main sidebar (`/referrals`) in place of Brand kit; the Brand kit page itself is still reachable from Settings and by its address.
