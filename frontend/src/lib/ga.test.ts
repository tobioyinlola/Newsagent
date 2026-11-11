import { afterEach, beforeEach, describe, expect, it, vi } from "vitest";

const ID = "G-L3JSNEQF7K";
type Mod = { ga: typeof import("./ga"); consent: typeof import("./consent") };

async function load(id: string | undefined = ID): Promise<Mod> {
  vi.resetModules();
  vi.stubEnv("VITE_GA_MEASUREMENT_ID", id ?? "");
  return { ga: await import("./ga"), consent: await import("./consent") };
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

describe("nothing happens without a yes", () => {
  it("is off entirely when no measurement id is set", async () => {
    const { ga, consent } = await load("");
    expect(ga.gaConfigured).toBe(false);
    consent.setConsent("granted");
    ga.startAnalytics();
    ga.trackPageView("/", "");
    expect(document.querySelector("script[src*=googletagmanager]")).toBeNull();
    expect(window.dataLayer).toBeUndefined();
  });
  it("sends and loads nothing before the visitor accepts", async () => {
    const { ga } = await load();
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
  it("asks again rather than assuming yes when browser storage is blocked", async () => {
    const { consent } = await load();
    vi.spyOn(Storage.prototype, "getItem").mockImplementation(() => { throw new Error("blocked"); });
    expect(consent.getConsent()).toBeNull();
    vi.restoreAllMocks();
  });
});

describe("after a yes", () => {
  it("loads Google's script and configures it with advertising features off", async () => {
    const { ga, consent } = await load();
    consent.setConsent("granted");
    ga.startAnalytics();
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
    const [e] = events("page_view");
    expect(e).toEqual({ page_location: `${location.origin}/ai-newsroom/:id?utm_campaign=welcome`, page_path: "/ai-newsroom/:id", page_title: "/ai-newsroom/:id" });
    ga.trackPageView("/i/abc123", "");
    ga.trackPageView("/admin/marketing", "");
    expect(events("page_view")).toHaveLength(1);
  });
  it("reports the five moments with numbers and labels only", async () => {
    const { ga, consent } = await load();
    consent.setConsent("granted");
    ga.startAnalytics();
    ga.track.signUp();
    ga.track.videoStarted("guided");
    ga.track.videoReady();
    ga.track.purchase({ id: "chk_1", value: 20, currency: "USD", credits: 10 });
    ga.track.purchase({ id: "chk_1", value: 20, currency: "USD", credits: 10 }); // coming back to the receipt
    expect(events("sign_up")).toEqual([{ method: "email" }]);
    expect(events("video_started")).toEqual([{ flow: "guided" }]);
    expect(events("video_ready")).toEqual([{}]);
    expect(events("purchase")).toEqual([{ transaction_id: "chk_1", value: 20, currency: "USD", items: [{ item_id: "credits", item_name: "Credits", quantity: 10, price: 2 }] }]);
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
