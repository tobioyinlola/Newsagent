import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const ID = "G-L3JSNEQF7K";
type Mod = { ga: typeof import("./ga"); consent: typeof import("./consent") };

async function load(id: string | undefined = ID, gtm = ""): Promise<Mod> {
  vi.resetModules();
  vi.stubEnv("VITE_GA_MEASUREMENT_ID", id ?? "");
  vi.stubEnv("VITE_GTM_ID", gtm);
  return { ga: await import("./ga"), consent: await import("./consent") };
}
// Google's script reports "loaded"; we then wait a moment for it to finish with what was queued before anything is handed to it.
async function loaded() {
  document.querySelectorAll<HTMLScriptElement>("script[src*=googletagmanager]").forEach((el) => el.onload?.(new Event("load")));
  await new Promise((r) => setTimeout(r, 250));
}
const sent = () => (window.dataLayer ?? []).map((e) => Array.from(e as ArrayLike<unknown>));
const events = (name: string) => sent().filter((e) => e[0] === "event" && e[1] === name).map((e) => e[2] as Record<string, unknown>);

beforeEach(() => { localStorage.clear(); sessionStorage.clear(); document.head.innerHTML = ""; window.dataLayer = undefined; window.gtag = undefined; Object.defineProperty(navigator, "doNotTrack", { value: "0", configurable: true }); });
afterEach(() => { vi.unstubAllEnvs(); });

describe("addresses are cleaned before Google sees them", () => {
  it("replaces project, checkout and token codes, and keeps readable pages", async () => {
    const { ga } = await load();
    expect(ga.cleanPath("/ai-newsroom/0123456789abcdef0123456789abcdef")).toBe("/ai-newsroom/:id");
    expect(ga.cleanPath("/billing/stripe/9f86d081884c7d659a2feaa0c55ad015")).toBe("/billing/stripe/:id");
    expect(ga.cleanPath("/billing/pay/Xq3-Jf8_Lm2PzR7vT1wKc9YbNa4HsDe6")).toBe("/billing/pay/:id");
    expect(ga.cleanPath("/ai-newsroom/new")).toBe("/ai-newsroom/new");
    expect(ga.cleanPath("/latest-stories/acme-launches-its-new-payments-product")).toBe("/latest-stories/acme-launches-its-new-payments-product");
    expect(ga.cleanPath("/pricing/")).toBe("/pricing");
    expect(ga.cleanPath("/")).toBe("/");
  });
  it("keeps only the campaign tags from the address bar", async () => {
    const { ga } = await load();
    expect(ga.cleanQuery("?token=secret&ref=ABC123&utm_source=cover_founder&utm_medium=email&utm_campaign=welcome")).toBe("?utm_source=cover_founder&utm_medium=email&utm_campaign=welcome");
    expect(ga.cleanQuery("?code=123456&email=a@b.com")).toBe("");
    expect(ga.cleanQuery("")).toBe("");
  });
  it("never measures private links or the back office", async () => {
    const { ga } = await load();
    for (const p of ["/admin", "/admin/marketing/campaigns", "/i/abc", "/s/abc"]) expect(ga.isMeasurable(p)).toBe(false);
    for (const p of ["/", "/signup", "/billing", "/ai-newsroom/new", "/latest-stories/x"]) expect(ga.isMeasurable(p)).toBe(true);
  });
});

describe("until they choose: counted without cookies. After Decline or a privacy signal: nothing", () => {
  it("is off entirely when no measurement id is set", async () => {
    const { ga, consent } = await load("");
    expect(ga.gaConfigured).toBe(false);
    consent.setConsent("granted");
    ga.startAnalytics();
    ga.trackPageView("/", "");
    expect(document.querySelector("script[src*=googletagmanager]")).toBeNull();
    expect(window.dataLayer).toBeUndefined();
  });
  it("counts a visitor who hasn't chosen yet, with analytics cookies denied and no cookie set", async () => {
    const { ga } = await load();
    ga.startAnalytics();
    expect(document.querySelector("script[src*=googletagmanager]")).not.toBeNull();
    expect(sent().find((e) => e[0] === "consent" && e[1] === "default")?.[2]).toMatchObject({ analytics_storage: "denied", ad_storage: "denied", ad_user_data: "denied", ad_personalization: "denied" });
    ga.trackPageView("/signup", "");
    await loaded();
    expect(events("page_view")).toHaveLength(1);
    expect(document.cookie).not.toContain("_ga");
  });
  it("lets Google use cookies only after an explicit Accept", async () => {
    const { ga, consent } = await load();
    ga.startAnalytics();
    consent.setConsent("granted");
    ga.startAnalytics();
    const updates = sent().filter((e) => e[0] === "consent" && e[1] === "update");
    expect(updates.at(-1)?.[2]).toEqual({ analytics_storage: "granted" });
    expect(document.querySelectorAll("script[src*=googletagmanager]")).toHaveLength(1); // not loaded a second time
  });
  it("sends nothing and loads nothing after a Decline", async () => {
    const { ga, consent } = await load();
    consent.setConsent("denied");
    ga.startAnalytics();
    ga.trackPageView("/", "");
    ga.track.signUp();
    expect(document.querySelector("script[src*=googletagmanager]")).toBeNull();
    expect(sent()).toEqual([]);
  });
  it("treats Do Not Track and Global Privacy Control as a standing no, even after a click on Accept", async () => {
    const { ga, consent } = await load();
    consent.setConsent("granted");
    Object.defineProperty(navigator, "doNotTrack", { value: "1", configurable: true });
    expect(consent.getConsent()).toBe("denied");
    ga.startAnalytics();
    expect(document.querySelector("script[src*=googletagmanager]")).toBeNull();
    Object.defineProperty(navigator, "doNotTrack", { value: "0", configurable: true });
    Object.defineProperty(navigator, "globalPrivacyControl", { value: true, configurable: true });
    expect(consent.getConsent()).toBe("denied");
    Object.defineProperty(navigator, "globalPrivacyControl", { value: undefined, configurable: true });
  });
  it("asks again rather than assuming yes when browser storage is blocked, and still counts without cookies", async () => {
    const { ga, consent } = await load();
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => { throw new Error("blocked"); });
    expect(consent.getConsent()).toBeNull();
    ga.startAnalytics();
    expect(sent().find((e) => e[0] === "consent" && e[1] === "default")?.[2]).toMatchObject({ analytics_storage: "denied" });
    vi.restoreAllMocks();
  });
});

describe("after Accept", () => {
  it("loads Google's script and configures it with advertising features off, and analytics cookies on", async () => {
    const { ga, consent } = await load();
    consent.setConsent("granted");
    ga.startAnalytics();
    expect(sent().find((e) => e[0] === "consent" && e[1] === "default")?.[2]).toMatchObject({ analytics_storage: "granted", ad_storage: "denied" });
    const script = document.querySelector<HTMLScriptElement>("script[src*=googletagmanager]");
    expect(script?.src).toBe(`https://www.googletagmanager.com/gtag/js?id=${ID}`);
    const config = sent().find((e) => e[0] === "config");
    expect(config?.[1]).toBe(ID);
    expect(config?.[2]).toMatchObject({ send_page_view: false, allow_google_signals: false, allow_ad_personalization_signals: false });
    expect(sent().find((e) => e[0] === "consent" && e[1] === "default")?.[2]).toMatchObject({ ad_storage: "denied", ad_user_data: "denied", ad_personalization: "denied" });
    ga.startAnalytics(); // asking twice does not load it twice
    expect(document.querySelectorAll("script[src*=googletagmanager]")).toHaveLength(1);
  });
  it("sends each page with a cleaned address and no title", async () => {
    const { ga, consent } = await load();
    consent.setConsent("granted");
    ga.startAnalytics();
    ga.trackPageView("/ai-newsroom/0123456789abcdef0123456789abcdef", "?token=secret&utm_campaign=welcome");
    await loaded();
    const [e] = events("page_view");
    expect(e).toEqual({ page_location: `${location.origin}/ai-newsroom/:id?utm_campaign=welcome`, page_path: "/ai-newsroom/:id", page_title: "/ai-newsroom/:id" });
    ga.trackPageView("/i/abc123", "");
    ga.trackPageView("/admin/marketing", "");
    expect(events("page_view")).toHaveLength(1);
    ga.trackPageView("/signup", "");
    expect(events("page_view")[1]).toMatchObject({ page_path: "/signup", page_referrer: `${location.origin}/ai-newsroom/:id?utm_campaign=welcome` }); // the page before, inside the app
  });
  it("reports the five moments with numbers and labels only", async () => {
    const { ga, consent } = await load();
    consent.setConsent("granted");
    ga.startAnalytics();
    history.replaceState({}, "", "/billing/stripe/9f86d081884c7d659a2feaa0c55ad015?session_id=cs_secret_1");
    ga.track.signUp();
    ga.track.videoStarted("guided");
    ga.track.videoReady();
    ga.track.purchase({ id: "chk_1", value: 20, currency: "USD", credits: 10 });
    ga.track.purchase({ id: "chk_1", value: 20, currency: "USD", credits: 10 }); // coming back to the receipt
    await loaded();
    // every one carries the cleaned address and title: left out, Google would fill in the real address, which holds the payment session id
    const page = { page_location: `${location.origin}/billing/stripe/:id`, page_path: "/billing/stripe/:id", page_title: "/billing/stripe/:id" };
    expect(events("sign_up")).toEqual([{ ...page, method: "email" }]);
    expect(events("video_started")).toEqual([{ ...page, flow: "guided" }]);
    expect(events("video_ready")).toEqual([page]);
    expect(events("purchase")).toEqual([{ ...page, transaction_id: "chk_1", value: 20, currency: "USD", items: [{ item_id: "credits", item_name: "Credits", quantity: 10, price: 2 }] }]);
    expect(JSON.stringify(sent())).not.toContain("session_id");
    history.replaceState({}, "", "/");
  });
  it("stops sending, and removes Google's cookies, when they change their mind", async () => {
    const { ga, consent } = await load();
    consent.setConsent("granted");
    ga.startAnalytics();
    document.cookie = "_ga=GA1.1.123; path=/";
    document.cookie = `_ga_${ID.slice(2)}=GS1.1.456; path=/`;
    consent.setConsent("denied");
    ga.stopAnalytics();
    expect(window[`ga-disable-${ID}`]).toBe(true);
    expect(document.cookie).not.toContain("_ga");
    ga.trackPageView("/", "");
    expect(events("page_view")).toHaveLength(0);
  });
});

const GTM = "GTM-MX2M47JB";
const scripts = () => Array.from(document.querySelectorAll<HTMLScriptElement>("script[src*=googletagmanager]")).map((e) => e.src);
const objectEvents = (name: string) => (window.dataLayer ?? []).filter((e) => !(Object.prototype.toString.call(e) === "[object Arguments]") && (e as { event?: string }).event === name) as Record<string, unknown>[];

describe("Google Tag Manager", () => {
  it("is not loaded at all unless a container id is set", async () => {
    const { ga } = await load(ID, "");
    ga.startAnalytics();
    expect(ga.gtmConfigured).toBe(false);
    expect(scripts().some((s) => s.includes("gtm.js"))).toBe(false);
  });
  it("loads from Google's own address (never inline), after the consent defaults are in place", async () => {
    const { ga } = await load("", GTM);
    ga.startAnalytics();
    expect(scripts()).toEqual([`https://www.googletagmanager.com/gtm.js?id=${GTM}`]);
    expect(document.querySelectorAll("script:not([src])")).toHaveLength(0); // nothing inline: the site's security policy would refuse it
    const order = (window.dataLayer ?? []).map((e) => (Object.prototype.toString.call(e) === "[object Arguments]" ? `${Array.from(e as ArrayLike<unknown>)[0]}` : (e as { event?: string }).event));
    expect(order.indexOf("consent")).toBeGreaterThanOrEqual(0);
    expect(order.indexOf("consent")).toBeLessThan(order.indexOf("gtm.js"));
    expect(sent().find((e) => e[0] === "consent" && e[1] === "default")?.[2]).toMatchObject({ analytics_storage: "denied", ad_storage: "denied", ad_user_data: "denied", ad_personalization: "denied" });
    expect(document.cookie).not.toContain("_ga");
  });
  it("is never loaded for someone who declined, or whose browser sends a privacy signal", async () => {
    const { ga, consent } = await load("", GTM);
    consent.setConsent("denied");
    ga.startAnalytics();
    expect(scripts()).toEqual([]);
    consent.setConsent(null);
    Object.defineProperty(navigator, "doNotTrack", { value: "1", configurable: true });
    ga.startAnalytics();
    expect(scripts()).toEqual([]);
  });
  it("gives the container a clean data layer: page views with the cleaned address, and the key moments, as events a trigger can use", async () => {
    const { ga } = await load("", GTM);
    ga.startAnalytics();
    ga.trackPageView("/ai-newsroom/0123456789abcdef0123456789abcdef", "?token=secret&utm_campaign=welcome");
    ga.trackPageView("/i/abc", "");
    ga.track.signUp();
    await loaded();
    expect(objectEvents("page_view")).toEqual([{ event: "page_view", page_location: `${location.origin}/ai-newsroom/:id?utm_campaign=welcome`, page_path: "/ai-newsroom/:id", page_title: "/ai-newsroom/:id" }]);
    expect(objectEvents("sign_up")).toHaveLength(1);
    expect(events("sign_up")).toHaveLength(1); // and as a gtag command, which the Google tag inside the container processes
  });
  it("when both ids are set, the container is the ONLY thing loaded: it carries the Analytics tag, so also loading gtag.js would run it twice", async () => {
    const { ga } = await load(ID, GTM);
    ga.startAnalytics();
    expect(scripts()).toEqual([`https://www.googletagmanager.com/gtm.js?id=${GTM}`]);
    ga.trackPageView("/signup", "");
    await loaded();
    expect(events("page_view")).toHaveLength(1);
    expect(sent().filter((e) => e[0] === "config")).toHaveLength(1); // the stream is configured once
  });
  it("Decline removes Google's cookies whatever measurement id set them, and stops Analytics", async () => {
    const { ga, consent } = await load(ID, GTM);
    consent.setConsent("granted");
    ga.startAnalytics();
    document.cookie = "_ga=GA1.1.123; path=/";
    document.cookie = "_ga_ABC123XYZ9=GS1.1.456; path=/";
    document.cookie = "keep_me=1; path=/";
    consent.setConsent("denied");
    ga.stopAnalytics();
    expect(document.cookie).toBe("keep_me=1");
    ga.trackPageView("/", "");
    await loaded();
    expect(objectEvents("page_view")).toHaveLength(0);
  });
});

describe("Google is kept shut except while we hand it one of our own events", () => {
  it("opens only for the moment of each send (Google's own automatic events would otherwise carry the raw address)", async () => {
    const { ga } = await load();
    ga.startAnalytics();
    const flag = () => window[`ga-disable-${ID}`];
    expect(flag()).toBe(true); // shut from the very start, so Google's own first automatic page view is dropped
    await loaded();
    expect(flag()).toBe(true); // and still shut once it has loaded
    const seen: (boolean | undefined)[] = [];
    const real = window.gtag!;
    window.gtag = (...a: unknown[]) => { if (a[0] === "event") seen.push(flag()); real(...a); };
    ga.trackPageView("/signup", "");
    expect(seen).toEqual([false]); // open while the event was handed over
    expect(flag()).toBe(true); // shut again straight after
  });
  it("keeps what was queued before Google loaded, in order, and loses none of it", async () => {
    const { ga } = await load();
    ga.startAnalytics();
    ga.trackPageView("/", "");
    ga.trackPageView("/signup", "");
    ga.track.signUp();
    expect(events("page_view")).toHaveLength(0); // nothing is handed over while Google is still loading
    await loaded();
    expect(events("page_view").map((e) => e.page_path)).toEqual(["/", "/signup"]);
    expect(events("sign_up")).toHaveLength(1);
  });
  it("hands over nothing that was queued if they decline before Google has loaded", async () => {
    const { ga, consent } = await load();
    ga.startAnalytics();
    ga.trackPageView("/", "");
    consent.setConsent("denied");
    ga.stopAnalytics();
    await loaded();
    expect(events("page_view")).toHaveLength(0);
  });
});
