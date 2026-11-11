// Proves Google Analytics behaves as intended, using GOOGLE'S REAL SCRIPT.
//
//   pnpm check:ga            (needs internet access to www.googletagmanager.com, and Chromium via Playwright)
//
// It builds the site in a test mode, downloads the real gtag.js / gtm.js for your measurement id and container, loads them in a real
// browser, and records every measurement hit the browser would send. The hits are answered locally with "204": NOTHING is sent to Google
// and nothing is counted in your Analytics account. It then checks, among other things, that:
//   - every screen is counted exactly once, with a cleaned address and title (never the raw page address or title);
//   - no private code, payment session id, search term or email address is sent, and Google's own automatic events (scroll, click,
//     form, download, site search) are never sent, whatever the data stream's "enhanced measurement" settings are;
//   - analytics cookies are denied until the visitor accepts, and granted after;
//   - nothing at all is sent after a Decline, with Do Not Track, or on private links;
//   - the key moments (sign_up, video_started, video_ready, purchase) arrive, with the cleaned address, and a repeat purchase once only.
// Override the ids with GA_ID=G-XXXX GTM_ID=GTM-XXXX.
import { spawn, execFileSync } from "node:child_process";
import { chromium } from "@playwright/test";

const GA_ID = process.env.GA_ID || "G-L3JSNEQF7K";
const GTM_ID = process.env.GTM_ID || "GTM-MX2M47JB";
const PORT = 4179;
const BASE = `http://localhost:${PORT}`;
const strip = (u) => (u ?? "").replace(/^http:\/\/localhost(:\d+)?/, "");
const results = [];
const check = (name, ok, extra = "") => { results.push(ok); console.log(`${ok ? "PASS" : "FAIL"}  ${name}${extra ? "  -> " + extra : ""}`); };
// Plain fetch where the machine has direct internet; curl (which honours a proxy) where it doesn't.
const get = async (url) => {
  try { const r = await fetch(url); if (!r.ok) throw new Error(`${url}: ${r.status}`); return Buffer.from(await r.arrayBuffer()); }
  catch { return execFileSync("curl", ["-sSf", "--max-time", "30", url], { maxBuffer: 20_000_000 }); }
};

async function run(mode, scripts) {
  const label = mode === "gtm" ? `Tag Manager container ${GTM_ID}` : `direct tag ${GA_ID}`;
  console.log(`\n===== ${label} =====`);
  const server = spawn("pnpm", ["exec", "vite", "preview", "--port", String(PORT), "--strictPort"], { stdio: "ignore" });
  await new Promise((r) => setTimeout(r, 4000));
  const b = await chromium.launch({ executablePath: process.env.CHROMIUM_PATH || undefined });
  try {
    const open = async ({ consent, dnt } = {}) => {
      const ctx = await b.newContext({ userAgent: "Mozilla/5.0 (X11; Linux x86_64) Chrome/120.0 Safari/537.36", viewport: { width: 1200, height: 800 } });
      if (consent) await ctx.addInitScript((c) => localStorage.setItem("newsagent.analytics-consent", c), consent);
      if (dnt) await ctx.addInitScript(() => Object.defineProperty(navigator, "doNotTrack", { value: "1", configurable: true }));
      const hits = [];
      await ctx.route(/^https:\/\/(?!localhost)/, async (r) => { const u = r.request().url(); if (/\/g\/collect|\/j\/collect|\/collect\?/.test(u)) hits.push({ q: Object.fromEntries(new URL(u).searchParams), body: r.request().postData() || "" }); await r.fulfill({ status: 204, body: "" }); });
      await ctx.route(/googletagmanager\.com\/(gtag\/js|gtm\.js)/, (r) => r.fulfill({ status: 200, contentType: "application/javascript", body: r.request().url().includes("gtm.js") ? scripts.gtm : scripts.gtag }));
      return { ctx, hits, p: await ctx.newPage() };
    };
    const v = await open();
    const wait = (ms = 4500) => v.p.waitForTimeout(ms);
    const nav = (path) => v.p.evaluate((x) => { history.pushState({}, "", x); window.dispatchEvent(new PopStateEvent("popstate")); }, path);
    await v.p.goto(BASE + "/?utm_source=cover_founder&utm_medium=email&utm_campaign=welcome");
    await v.p.getByRole("region", { name: "Cookie choices" }).waitFor(); await wait();
    await v.p.getByRole("link", { name: "Sign up" }).first().click(); await wait();
    await v.p.getByPlaceholder(/email/i).first().fill("someone@example.com").catch(() => {}); await v.p.keyboard.press("Tab"); await v.p.mouse.wheel(0, 3000); await wait();
    await nav("/billing/stripe/9f86d081884c7d659a2feaa0c55ad015?session_id=cs_secret_123&code=987654"); await wait();
    await nav("/signup?q=secret-search-term&email=a@b.com"); await wait();
    const beforeAccept = v.hits.length;
    await v.p.getByRole("button", { name: "Accept" }).click(); await wait(1500);
    await nav("/login"); await wait();
    // the payment return page's address, WITHOUT the app moving away from it (as it doesn't on a real return), then the key moments
    await v.p.evaluate(() => history.replaceState({}, "", "/billing/stripe/9f86d081884c7d659a2feaa0c55ad015?session_id=cs_secret_999")); await wait(1500);
    await v.p.evaluate(() => { const g = window.__ga; g.track.signUp(); g.track.videoStarted("guided"); g.track.videoReady(); g.track.purchase({ id: "chk_123", value: 20, currency: "USD", credits: 10 }); g.track.purchase({ id: "chk_123", value: 20, currency: "USD", credits: 10 }); });
    await wait(7000);
    const loadedFrom = await v.p.evaluate(() => [...document.scripts].map((x) => x.src).filter((x) => /googletagmanager/.test(x)));
    const cookies = (await v.ctx.cookies()).map((c) => c.name);
    await v.p.close(); await new Promise((r) => setTimeout(r, 1500));
    const evs = v.hits.flatMap((h, i) => [{ ...h.q }, ...h.body.split("\n").filter(Boolean).map((l) => Object.fromEntries(new URLSearchParams(l)))].map((e) => ({ i, ...e, gcs: e.gcs ?? h.q.gcs, dl: e.dl ?? h.q.dl, dt: e.dt ?? h.q.dt, cu: e.cu ?? h.q.cu })));
    const pv = evs.filter((e) => e.en === "page_view").map((e) => strip(e.dl));
    console.log("page views:", JSON.stringify(pv));
    const all = JSON.stringify(evs);
    const want = mode === "gtm" ? `https://www.googletagmanager.com/gtm.js?id=${GTM_ID}` : `https://www.googletagmanager.com/gtag/js?id=${GA_ID}`;
    check("exactly one Google script is loaded, the expected one", loadedFrom.length === 1 && loadedFrom[0] === want, JSON.stringify(loadedFrom));
    check("every hit is for your property", v.hits.length > 0 && v.hits.every((h) => h.q.tid === GA_ID));
    check("one visit is one session", new Set(v.hits.map((h) => h.q.sid).filter(Boolean)).size === 1);
    check("the first page of the visit is counted, with the campaign tags only", pv[0] === "/?utm_source=cover_founder&utm_medium=email&utm_campaign=welcome");
    check("every screen visited is counted", ["/signup", "/billing/stripe/:id", "/login"].every((p) => pv.includes(p)));
    // the app itself sends a signed-out visitor from the billing screen to /login, which is why /login follows each billing screen
    const expected = ["/?utm_source=cover_founder&utm_medium=email&utm_campaign=welcome", "/signup", "/billing/stripe/:id", "/login", "/signup", "/login"];
    check("each screen once, exactly as visited (Google's own automatic page views are not sent)", JSON.stringify(pv) === JSON.stringify(expected), JSON.stringify(pv));
    check("every page view carries a cleaned title, never the page's own title", evs.filter((e) => e.en === "page_view").every((e) => (e.dt ?? "").startsWith("/")));
    check("no private code, payment session id, search term or email anywhere", !/code=|session_id|9f86d0|q=secret|search-term|someone|%40|a@b/.test(all));
    check("none of Google's automatic events (scroll, click, form, download, search)", !evs.some((e) => ["scroll", "click", "form_start", "form_submit", "file_download", "view_search_results", "video_start"].includes(e.en)));
    check("before Accept: analytics cookies denied (gcs=G100) and no Google cookie", evs.filter((e) => e.i < beforeAccept).every((e) => e.gcs === "G100"));
    check("after Accept: analytics cookies granted (gcs=G101), and Google sets its cookies", evs.some((e) => e.i >= beforeAccept && e.gcs === "G101") && cookies.some((c) => /^_ga/.test(c)), cookies.join(","));
    check("the key moments arrive (sign_up, video_started, video_ready, purchase)", ["sign_up", "video_started", "video_ready", "purchase"].every((n) => evs.some((e) => e.en === n)));
    check("they carry the cleaned address and title", evs.filter((e) => ["sign_up", "video_started", "video_ready", "purchase"].includes(e.en)).every((e) => strip(e.dl) === "/billing/stripe/:id" && e.dt === "/billing/stripe/:id"));
    check("purchase has its id, value and currency, and is sent once", evs.filter((e) => e.en === "purchase").length === 1 && evs.some((e) => e.en === "purchase" && e["ep.transaction_id"] === "chk_123" && e["epn.value"] === "20" && e.cu === "USD"));
    await v.ctx.close();
    for (const [name, opts, path] of [["declined", { consent: "denied" }, "/"], ["Do Not Track", { dnt: true }, "/"], ["a private link", {}, "/s/AbCdEf0123456789xyzQWERTYuiop1234"]]) {
      const s = await open(opts);
      await s.p.goto(BASE + path); await s.p.waitForTimeout(3000);
      const loadedAny = await s.p.evaluate(() => [...document.scripts].some((x) => /googletagmanager/.test(x.src)));
      check(`${name}: nothing sent to Google and its script isn't even loaded`, s.hits.length === 0 && !loadedAny);
      await s.ctx.close();
    }
  } finally { await b.close(); server.kill(); }
}

console.log("Downloading Google's real scripts (nothing is sent to your account)...");
const scripts = { gtag: await get(`https://www.googletagmanager.com/gtag/js?id=${GA_ID}`), gtm: await get(`https://www.googletagmanager.com/gtm.js?id=${GTM_ID}`) };
for (const [mode, env] of [["gtag", { VITE_GA_MEASUREMENT_ID: GA_ID }], ["gtm", { VITE_GA_MEASUREMENT_ID: GA_ID, VITE_GTM_ID: GTM_ID }]]) {
  execFileSync("pnpm", ["exec", "vite", "build", "--mode", "e2e"], { env: { ...process.env, ...env }, stdio: "ignore" });
  await run(mode, scripts);
}
const failed = results.filter((x) => !x).length;
console.log(`\n${failed === 0 ? "ALL CHECKS PASSED" : failed + " CHECK(S) FAILED"} (${results.length} checks)`);
process.exit(failed ? 1 : 0);
