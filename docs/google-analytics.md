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

## 1b. Google Tag Manager (optional)

Container: `GTM-MX2M47JB`. Add in Vercel (Production only), then redeploy:

| Name | Value |
|---|---|
| `VITE_GTM_ID` | `GTM-MX2M47JB` |
| `VITE_GA_VIA_GTM` | leave empty (see the warning below) |

**Do not paste the snippet Google gives you into `index.html`.** It is an inline `<script>`, which the site's security policy refuses, and
it would load for everyone straight away: before they choose about cookies, for browsers that send Do Not Track, on private links, and
on the back office. Our code loads the same container from Google's address, after the consent rules, and never on those pages.

What the container receives, from our code:
- the consent state, set **before** the container loads (`analytics_storage` denied until Accept; advertising always denied);
- `page_view` data-layer events with a cleaned address (`page_location`, `page_path`, `page_title`) each time the screen changes;
- `sign_up`, `video_started`, `video_ready` and `purchase` events. Use **Custom Event** triggers with those names.

**Avoid counting everything twice.** Analytics is already sent to directly (`G-L3JSNEQF7K`). So, in the container, do **not** add a GA4 tag for
the same measurement id, unless you also set `VITE_GA_VIA_GTM=true` (then we stop sending directly and the container is the only
sender). If you do use the container for GA4:
- set the GA4 configuration tag to **not** send a page view when it loads (our `page_view` event does that, with the cleaned address);
- don't use GTM's built-in *Page View* or *History Change* triggers for GA4: they report the raw address, which can contain private codes;
- in each tag's *Consent settings*, require `analytics_storage` (and `ad_storage` etc. for anything advertising-related).

**Security policy.** Custom HTML tags and extra pixels (Meta, LinkedIn, Google Ads) load more scripts, and the site's security policy only
allows Google's measurement addresses. Each new vendor needs its addresses added deliberately in `frontend/security-headers.mjs` (and
`vercel.json` regenerated); anything else is blocked, which is the point. GTM **preview/debug mode** is also blocked by default for the
same reason.

The `<noscript>` iframe Google suggests for visitors without JavaScript isn't used: this is a JavaScript app, and the policy blocks frames.

## 2. Settings to change in Google Analytics (one time)

In analytics.google.com, for the property that owns `G-L3JSNEQF7K`:

1. **Admin > Data streams > (the web stream) > Enhanced measurement.** Open the gear and turn **off**:
   - *Page views > Page changes based on browser history events* (we send each page view ourselves, with private codes removed; leaving
     this on double-counts and sends the raw address);
   - *Site search* and *Form interactions*.
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
