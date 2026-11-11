# Marketing email: how to switch it on safely

Marketing email (Back office > Marketing) sends through the same sender as every other email, so a problem with it can affect
sign-in codes. Go in this order.

## 1. Before anything is sent
- **Migrations:** run `alembic upgrade head` on staging first (marketing adds `0040` to `0047`), then production.
- **Worker:** the Celery worker and beat must be running. Marketing runs as the `marketing.deliver` task, once a minute.
- **Permissions:** `marketing.view` and `marketing.manage` (admins have both). Give them to other roles under Team.

## 2. Report bounces and spam complaints (do this before `on`)
Without it, bad addresses keep getting emailed and hurt delivery for everyone.
1. In Resend, open Webhooks and add an endpoint: `https://<your app domain>/v1/webhooks/resend-events`.
2. Tick the events `email.bounced` and `email.complained`.
3. Copy the signing secret (starts with `whsec_`) into `RESEND_EVENTS_SECRET` on `backend` and redeploy.
4. The Marketing screen stops showing the "bounces aren't being reported" warning.
- A **permanent** bounce blocks the address for marketing. Temporary or unclear bounces are ignored.
- A **spam complaint** blocks the address and counts as an unsubscribe.
- Blocked addresses are listed under Marketing > Opt-outs; a block can be lifted there. Unsubscribes can't be undone by us: the
  person turns it back on from the unsubscribe page or Settings > Profile > Emails from us.

## 3. Turn it on in stages
1. `MARKETING_EMAIL=dry_run`: everything runs and is logged (Marketing > Activity) but nothing is emailed.
2. Make a campaign to a small segment and check the counts and the email preview. Use "Send a test to me" on the copy.
3. `MARKETING_EMAIL=on`, and send first to a segment of your own accounts.
4. Start with small campaigns and watch how many land in spam before sending bigger ones.

## 4. Things to know
- Limits (Marketing > Sending): at most one marketing email per person every 2 days, 500 a day, 20 a minute. Account emails are
  never counted or held back.
- **Pause all marketing** stops every send within a minute. Workflows freeze where they are; campaigns wait.
- Workflows send 9:00 to 18:00 in the person's country (`MARKETING_DEFAULT_TIMEZONE`, default Africa/Lagos, for countries we don't know).
  Campaigns send at the time you pick.
- Opens are approximate (some mail apps load images for everyone). Clicks are the reliable number. Tracking can be switched off.
- Before emailing existing users, confirm that the Terms and Privacy Policy they accepted allow product marketing email.
