# Google Analytics

Google Analytics 4 measures how people use the **public website and the customer app**: which pages, where they come from, and how far
they get (sign up, first video, video ready, credits bought). It is separate from the in-app audience reports (`docs/analytics.md`),
which count views of stories and shared videos from our own database.

It uses Google's **advanced Consent Mode**, so it counts everyone, with cookies only for people who accept:

| Visitor | Google Analytics |
|---|---|
| Hasn't chosen yet (or ignores the banner) | Counts the visit **without cookies** (page, IP address and browser details; no cookie, no returning-visitor recognition) |
| Clicked **Accept** | Counts with cookies (`_ga`, 13 months), so returning visitors are recognised |
| Clicked **Decline** | Switched off, no data sent |
| Browser sends Do Not Track / Global Privacy Control | Switched off, no data sent |

It never runs on the back office (`/admin`), the founder interview links (`/i/...`) or private share links (`/s/...`).

**Expect Google's numbers to be incomplete for people who haven't accepted.** Without cookies, Google cannot tell that two visits are
the same person, so those visits are not counted as users on their own. Google estimates them with statistical modelling, and only
once the property has enough data (roughly 1,000 events a day from people who declined and 1,000 daily users who accepted, for 7
days). Until then GA4 shows mostly the people who accepted. **The exact count of everyone is the first-party counter below.**

## Our own cookie-free counter (exact, everyone)

Every visit to the public site and customer app is also counted by us, on our own server, with **no cookie and nothing stored on the
visitor's device**, whatever they chose about cookies. See it in the back office: **Reports & analytics > Website visitors**
(`/admin/analytics`): visitors and page views per day, where visitors came from (search, social, other websites, and our own
marketing emails by campaign), and the most visited pages.

- A visitor is a one-way code made from the day, a server secret, their IP address and browser. The IP address is **never stored**, and
  the code changes every day, so a person is counted **once a day** and can't be followed from one day to the next (someone who comes on
  two days counts twice). Only daily totals are kept; the codes are deleted after two days.
- Not counted: robots, browsers sending Do Not Track or Global Privacy Control, the back office, private links.
- Pages come from a fixed list, so made-up addresses can't fill the tables.
- It counts people on your own team too. Internal visits can't be removed from it the way a Google Analytics filter can.
- Needs `TRUST_PROXY_HEADERS=true` on the backend (already required for rate limits), so the visitor's address is read from
  `X-Forwarded-For` and not the proxy's.

## 1. Switch it on (one setting)

In Vercel: **Project > Settings > Environment Variables**, add

| Name | Value | Environments |
|---|---|---|
| `VITE_GA_MEASUREMENT_ID` | `G-L3JSNEQF7K` | **Production only** |

Then redeploy (the value is baked in at build time). Leave it **empty or unset on staging and previews** so test traffic stays out of your
real numbers. With no value, there is no banner and nothing loads.

To stop all tracking, clear the value and redeploy.

## 1b. Your Tag Manager container (`GTM-MX2M47JB`)

Add these in Vercel (Production only), next to the Analytics id, then redeploy. **Set both.**

| Name | Value |
|---|---|
| `VITE_GA_MEASUREMENT_ID` | `G-L3JSNEQF7K` |
| `VITE_GTM_ID` | `GTM-MX2M47JB` |

**What that container is.** We downloaded Google's real file for `GTM-MX2M47JB` and read it: it is not a separate container with its own tags.
It holds exactly the same configuration as the Analytics stream `G-L3JSNEQF7K` (17 tags, all for that one stream): it is the "Google tag"
Analytics creates for the stream. So the two are the same thing, and **when `VITE_GTM_ID` is set, the container is the only Google script
we load** (never `gtag.js` as well, which would run the same tag twice). Leave `VITE_GTM_ID` empty to load `gtag.js` directly instead; the
result is identical. If you later add your own tags to a container, they load too, and each needs its consent settings checked.

**Do not paste Google's snippet into `index.html`.** It is an inline `<script>`, which the site's security policy refuses (we tested it),
and it would load for everyone straight away: before they choose about cookies, for Do Not Track, on private links and on the back office.

**Security policy.** Extra vendors (Meta, LinkedIn, Google Ads, custom scripts) load more addresses, and the policy only allows Google's
measurement addresses. Each new vendor must be added deliberately in `frontend/security-headers.mjs` (then regenerate `vercel.json`).
Tag Manager's preview/debug mode is blocked by default for the same reason. The `<noscript>` frame isn't used (this is a JavaScript app).

## 1c. How we know it works (and how to check again)

`pnpm check:ga` (in `frontend/`; needs internet and Chromium) downloads Google's **real** `gtag.js` and `gtm.js` for your ids, runs them in a real
browser against the real build, and records every measurement the browser would send. The measurements are answered locally, so **nothing is
sent to Google and nothing is counted in your account**. 34 checks, run once for the direct tag and once for the container:

- every screen is counted exactly once, in order, with a **cleaned address and title** (never the page's own title or the real address);
- **no private code, payment session id, search term or email address** is sent, even when someone types an email into a form;
- Google's own automatic events (scroll, outbound click, form, download, site search) are **never** sent;
- analytics cookies are denied until Accept (`gcs=G100`), granted after (`gcs=G101`), and the `_ga` cookies appear only then;
- one visit is one session, and every hit is for `G-L3JSNEQF7K`;
- sign_up, video_started, video_ready and purchase arrive with the cleaned address; a repeated purchase is sent once;
- a declined visitor, a Do Not Track browser and a private link send **nothing** and don't even load Google's script.

Run it after changing anything about analytics, or after changing the data stream's settings in your Google account.

### What the real script showed about your stream (and why the code keeps Google shut)

Your stream has *every* enhanced-measurement feature on: automatic page views including **page changes on browser history events**, scrolls,
outbound clicks, file downloads, form interactions, video, site search, and **automatic collection of user-provided data** (emails, phones,
addresses). Left alone, Google's tag then sends its own page view on load and on every in-app page change **using the real address and
the page's real title** (with any `?code=` or payment session id), counting every page twice next to ours.

Nothing we can pass to the tag (`send_page_view: false`, a cleaned `page_location`, `set`) stops that. So the code keeps Google's tag **shut**
(`ga-disable-G-L3JSNEQF7K`) and opens it only for the instant we hand it one of our own cleaned events. The check above proves it. This
means **the settings below are no longer required for correct numbers**; they are still worth switching off, as a second line of defence.

## 2. Settings to change in Google Analytics (one time)

In analytics.google.com, for the property that owns `G-L3JSNEQF7K`:

1. **Admin > Data streams > (the web stream) > Enhanced measurement.** Open the gear and turn **off** everything you don't use, in
   particular *Page changes based on browser history events*, *Site search* and *Form interactions* (the code already stops these
   from reaching Google; switching them off is a second line of defence). Also look at **Data collection > User-provided data collection**
   (it is on for your stream) and turn it off: we never send emails, but there is no reason to leave it on.
2. **Admin > Data collection and modification > Data retention:** set event data retention to **14 months**.
3. **Data collection:** leave *Google signals* **off**. (The site also tells Google not to use advertising features.)
4. **Admin > Events:** mark `sign_up`, `video_started`, `video_ready` and `purchase` as **key events**.
5. **Admin > Data streams > Configure tag settings > List unwanted referrals:** add your payment provider's domain (for example
   `checkout.stripe.com`), so a purchase isn't credited to it instead of where the visitor really came from.
6. **Admin > Data collection > Internal traffic:** define your team's IP addresses, then turn the *Internal traffic* data filter on.
7. **Admin > Data sharing settings:** switch off anything you don't want Google to use for its own products.

## 3. What is sent

| Moment | Event | Details sent |
|---|---|---|
| Every page | `page_view` | The cleaned address only, such as `/ai-newsroom/:id`. Only `utm_` campaign tags are kept from the address bar |
| Sign-up form visited | `page_view` of `/signup` | (a normal page view) |
| Account created | `sign_up` | `method: email` |
| First video started | `video_started` | `flow: guided` or `classic` |
| Video becomes ready | `video_ready` | nothing (fires only when it finishes while the person is watching, not when an old video is opened) |
| Credits bought | `purchase` | payment number, amount, currency, credits (once per payment; bank transfers count when approved, not when submitted) |

Never sent: names, emails, company names, page titles, project or checkout numbers, link codes, reset codes, referral codes.

## 4. Marketing emails in Analytics

The button in every marketing email goes through our own site first. When it leads to a page on our site, we add
`utm_source=cover_founder&utm_medium=email&utm_campaign=<campaign or workflow name>` (and `utm_content=step-N` for workflows). In
Analytics, open **Reports > Acquisition > Traffic acquisition** and look at *Session campaign* to see which campaign brought sign-ups
and purchases. Links to other websites are left alone.

## 5. Checking it works

1. Open the live site in a private window and look at **Reports > Realtime** in Analytics: you should appear within a minute even before you answer the banner. Then click **Accept** and confirm the `_ga` cookie appears.
   In the back office, **Reports & analytics > Website visitors** should show the visit right away.
2. Click around (sign up page, etc.): each screen shows as its own page.
3. Click **Cookie settings** in the footer and **Decline**: nothing further goes to Google and the `_ga` cookies are removed (our own cookie-free count continues).
4. Open a `/s/...` private link: no banner, nothing sent or counted.

## 6. Security policy

`vercel.json` (generated by `scripts/gen-vercel-root.mjs` and `frontend/scripts/gen-vercel-json.mjs`) lets the **public site** load
`googletagmanager.com` and report to `google-analytics.com` / `analytics.google.com`. The back office (`/admin`) keeps the strict policy with
no third-party script. Regenerate both files after changing `frontend/security-headers.mjs`.

## 7. Wording

The Privacy Policy describes both measurements (Google Analytics: cookie-free until you choose, cookies only after Accept, off after
Decline; and our own cookie-free counter) under *Cookies and similar storage*, the data table, the providers table, the purposes table and
the retention table, and notes the change under *Changes to this policy*.

**Be aware:** counting visitors with Google Analytics before they choose sends their IP address and browser details to Google without
consent. That is how Google's advanced Consent Mode works and is widely used, but regulators in the UK, EU and Nigeria have not all
accepted it, and the legal basis we state is "legitimate interests". If you would rather not take that risk, set the visitors-before-choosing
behaviour to wait for consent (ask a developer; it is a one-line change in `frontend/src/components/Analytics.tsx`). The first-party counter
stays exact either way. `TERMS_VERSION` was **not** changed: the change is a disclosure with its own consent, not a new term people must
re-accept. Have your lawyer read the wording if you want it checked.
