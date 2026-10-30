# Audience reporting

Customer navigation: **Analytics** (`/analytics`). The dashboard has a 30-day summary and completed videos link to their own report. Admin navigation: **Reports & analytics** (`/admin/analytics`), under Operations. Admin reports include every workspace; customers only see their own workspace. Filter by story, use 7/30/90 days or a custom UTC range up to 366 days, inspect trend points/the accessible data table, or download CSV.

## Cover Founder measurements

- Story impression: at least 50% of a story thumbnail visible for one second on a visible page.
- Story visit: a public story page successfully loaded and visible.
- Shared-video visit: a private share page successfully loaded and visible.
- Engaged video view: at least 10 seconds of distinct content watched, or completion of a shorter clip. Seeking forward and replaying the same portion do not accumulate extra watch time.
- Completion: playback ends with at least 90% of distinct content watched.

Each metric counts once per project, browser-tab session and UTC day, including across public/private video surfaces. These counts represent recorded sessions, **not verified unique people**. A random session UUID lives in sessionStorage; only its SHA-256 digest is stored server-side. No raw IP address or user agent is stored in these analytics tables. Recognised bot user agents, authenticated project owners/admin previews, Do Not Track and Global Privacy Control opt-outs are excluded. Client failures/blockers may reduce counts. Intake is rate limited; it is not a fraud-proof measurement service.

Collection starts when this feature is deployed. Historical activity is not reconstructed. Existing shared-link server opens remain explicitly separate as a lifetime legacy counter, not added to the new visits. Daily aggregates persist; daily maintenance prunes deduplication markers older than two days. Project deletion removes its platform measurements; workspace export includes aggregates, never session markers. Workspace erasure removes publisher figures too.

## Publisher measurements

In admin reports, select a published outlet under **Publisher reports**. First save its published URL and contact in Distribution. **Request figures from publisher** queues a professional email asking for dated views/impressions and metric definitions. Replies remain in the team's email inbox; there is no inbox sync or automatic scraping. The existing distribution outbox logs delivery, handles failure/retry, and uses the configured email provider and reply-to address.

Enter cumulative figures **as of a reporting date**, with a customer-visible source note. Leave unavailable metrics blank; zero means the publisher explicitly reported zero. A snapshot is unique per placement/date; saving again corrects it. Previous dates remain available for history, editing and removal. Admin write access requires `operations.manage`; read access requires `operations.view`. Edits and removals are audited. Staff email identities are excluded from the customer report.

Latest known views and impressions are selected independently per placement as of the report's end date, with each measurement date displayed. Repeated cumulative snapshots are **never added together**. Publisher history uses snapshots inside the selected date range; current totals can come from an earlier snapshot. CSV includes daily platform counts and in-range cumulative publisher snapshots, labelled by source and basis. Channel totals are separate from platform totals; audience overlap between publishers is unknown. Different publishers may define impressions/views differently.

## Rollout and validation

Migration `0025` adds three tables (`audience_events`, `audience_daily`, `publisher_snapshots`) and no backfill. Run `alembic upgrade head` through the existing predeploy command before serving the updated application. No new credentials or environment variables are needed; publisher email requests use existing email configuration.

Local tests use mock email/vendor providers and disposable databases. They do not send real publisher emails or run live payment transactions. Backend integration tests cover concurrency, duplicates, scoped access, opt-outs, bot/owner exclusions, hidden stories, private-link revocation, snapshots/corrections, multiple outlets, date boundaries, CSV injection handling and data erasure. Frontend tests cover watch ranges, privacy, duplicate requests and visibility thresholds. The browser scenario covers public measurements, admin entry/request email, customer/mobile display and CSV download.
