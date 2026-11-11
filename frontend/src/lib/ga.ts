import { getConsent } from "./consent";

// Google Analytics 4, used with care, in Google's "advanced Consent Mode":
//  - it is off unless VITE_GA_MEASUREMENT_ID is set for the build;
//  - until a visitor chooses it counts their visit WITHOUT cookies; if they accept, it also uses cookies; if they decline, it is switched off;
//  - the private pages (founder interview links, private share links, the back office) are never measured;
//  - addresses are cleaned before they are sent, so no private link code, checkout number or project number ever reaches Google;
//  - no names, emails or company names are sent: only what a page is, and what step someone reached.
export const GA_ID: string = String(import.meta.env.VITE_GA_MEASUREMENT_ID ?? "").trim();
export const gaConfigured = /^G-[A-Z0-9]{6,}$/.test(GA_ID);

// Google Tag Manager (optional): if VITE_GTM_ID is set, that container is the ONE thing we load (it carries the Analytics tag, as the
// "Google tag" container Analytics creates for a data stream does). Loading both gtm.js and gtag.js for the same stream would run the
// Google tag twice. Keep VITE_GA_MEASUREMENT_ID set as well: it names the stream we keep closed to Google's own automatic events.
export const GTM_ID: string = String(import.meta.env.VITE_GTM_ID ?? "").trim();
export const gtmConfigured = /^GTM-[A-Z0-9]{4,}$/.test(GTM_ID);
export const trackingConfigured = gaConfigured || gtmConfigured;

type Params = Record<string, string | number | boolean | undefined | Record<string, unknown>[]>;
declare global {
  interface Window {
    dataLayer?: unknown[];
    gtag?: (...args: unknown[]) => void;
    [key: `ga-disable-${string}`]: boolean | undefined;
  }
}

// Pages that are never measured: the operator back office, and the private links (the person opening one did not sign up to anything).
const NEVER = [/^\/admin(\/|$)/, /^\/i\//, /^\/s\//];
export const isMeasurable = (pathname: string) => !NEVER.some((r) => r.test(pathname));

// A long unguessable code: a project or checkout number (hex), or a random token (long, mixed upper and lower case).
// A readable story address like "acme-launches-new-product" is all lower case and stays as it is.
const isIdLike = (seg: string) => /^[0-9a-f]{20,}$/i.test(seg) || (seg.length >= 22 && /^[A-Za-z0-9_-]+$/.test(seg) && /[A-Z]/.test(seg) && /[a-z]/.test(seg));
const UTM = ["utm_source", "utm_medium", "utm_campaign", "utm_term", "utm_content"];

// "/ai-newsroom/8f3c…" becomes "/ai-newsroom/:id": the shape of the page, never the thing it was about.
export function cleanPath(pathname: string): string {
  const path = pathname.replace(/\/{2,}/g, "/").split("/").map((seg) => (isIdLike(seg) ? ":id" : seg)).join("/") || "/";
  return path.length > 1 ? path.replace(/\/$/, "") : path;
}

// Only the campaign tags survive from the address bar. Everything else (reset codes, referral codes, anything) is dropped.
export function cleanQuery(search: string): string {
  const keep = new URLSearchParams();
  const from = new URLSearchParams(search);
  for (const k of UTM) { const v = from.get(k); if (v) keep.set(k, v.slice(0, 100)); }
  const q = keep.toString();
  return q ? `?${q}` : "";
}

const FLUSH_DELAY_MS = 150;
let started = false;
let ready = false; // Google's script has loaded and processed what we queued
const queued: (() => void)[] = [];
let lastLocation = ""; // where the visitor was before, for the "previous page" report (the browser's own referrer never changes in a one-page app)

// Sending is allowed unless they declined (or their browser sent a privacy signal, which getConsent() reports as "denied").
const active = () => trackingConfigured && started && getConsent() !== "denied" && typeof window.gtag === "function";

// Google's script reads an `arguments` object from the data layer, not an array, so this has to be a plain function.
// eslint-disable-next-line @typescript-eslint/no-unused-vars
function gtag(..._args: unknown[]) {
  window.dataLayer = window.dataLayer ?? [];
  // eslint-disable-next-line prefer-rest-params
  window.dataLayer.push(arguments);
}

// THE GATE. Left to itself, Google's tag sends its own automatic events (a page view on load and on every in-app page change, scrolls,
// outbound clicks, form use, file downloads, searches) using the RAW address and title, which can hold private codes, and which would
// count every page twice next to ours. Nothing in the tag's settings from our side stops that. So Google is kept switched off, and
// opened only for the instant we hand it one of our own cleaned events. (Checked against Google's real script.)
const gate = (open: boolean) => { if (gaConfigured) window[`ga-disable-${GA_ID}`] = !open; };
function toGoogle(send: () => void) {
  if (!ready) { queued.push(() => toGoogle(send)); return; }
  gate(true);
  try { send(); } finally { gate(false); }
}

// Called on the first measurable page, and again when their choice changes. Cookies are used only after an explicit Accept; until then
// Google gets cookie-free page views, and after Decline or a privacy signal it gets nothing at all (and the script is never loaded).
export function startAnalytics(): void {
  const consent = getConsent();
  if (!trackingConfigured || consent === "denied") return;
  const storage = consent === "granted" ? "granted" : "denied";
  if (started) { window.gtag?.("consent", "update", { analytics_storage: storage }); return; }
  started = true;
  gate(false);
  window.dataLayer = window.dataLayer ?? [];
  window.gtag = gtag;
  // Advertising features stay off for everyone, and analytics cookies are off until they accept. Set BEFORE Google's code loads.
  gtag("consent", "default", { ad_storage: "denied", ad_user_data: "denied", ad_personalization: "denied", analytics_storage: storage });
  gtag("set", "ads_data_redaction", true);
  if (gtmConfigured) {
    window.dataLayer.push({ "gtm.start": Date.now(), event: "gtm.js" });
  } else {
    gtag("js", new Date());
  }
  if (gaConfigured) {
    gtag("config", GA_ID, {
      send_page_view: false, // the app is one page: we send each page view ourselves, with a cleaned address
      allow_google_signals: false,
      allow_ad_personalization_signals: false,
      cookie_expires: 34128000, // 13 months, the longest regulators accept
      cookie_flags: "SameSite=Lax;Secure",
    });
  }
  // Google's code goes in as a script element from its own address, never inline: the site's security policy only allows that address.
  const el = document.createElement("script");
  el.async = true;
  el.src = gtmConfigured ? `https://www.googletagmanager.com/gtm.js?id=${encodeURIComponent(GTM_ID)}` : `https://www.googletagmanager.com/gtag/js?id=${encodeURIComponent(GA_ID)}`;
  // Google finishes working through what was queued shortly AFTER its script reports "loaded"; sending any sooner would be lost behind the gate.
  el.onload = () => { setTimeout(() => { ready = true; queued.splice(0).forEach((f) => f()); }, FLUSH_DELAY_MS); };
  document.head.appendChild(el);
}

// They said no, or changed their mind: stop sending, and remove what Google set (whichever measurement id set it).
export function stopAnalytics(): void {
  if (!trackingConfigured) return;
  gate(false);
  queued.length = 0;
  window.gtag?.("consent", "update", { analytics_storage: "denied" });
  const host = location.hostname;
  const parent = host.split(".").length > 2 ? host.split(".").slice(-2).join(".") : host;
  const names = document.cookie.split(";").map((c) => c.split("=")[0].trim()).filter((n) => /^_(ga|gid|gat)(_|$)/.test(n));
  for (const n of names) {
    for (const d of [host, `.${host}`, `.${parent}`]) document.cookie = `${n}=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/; domain=${d}`;
    document.cookie = `${n}=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/`;
  }
}

// One event, to wherever it is wanted: Google's tag (a gtag command, which also reaches the tag inside a Tag Manager container) and,
// for a container with its own triggers, a data-layer event.
function emit(name: string, params: Record<string, unknown>) {
  // Every event carries the cleaned address and title. Without them Google fills in the real ones, and on a payment return page the real
  // address holds the payment session id.
  const full = name === "page_view" ? params : { ...pageParams(), ...params };
  toGoogle(() => {
    window.gtag!("event", name, full);
    if (gtmConfigured) window.dataLayer!.push({ event: name, ...full });
  });
}

function pageParams() {
  const path = cleanPath(location.pathname);
  return { page_location: `${location.origin}${path}${cleanQuery(location.search)}`, page_path: path, page_title: path };
}

export function trackPageView(pathname: string, search: string): void {
  if (!active() || !isMeasurable(pathname)) return;
  const path = cleanPath(pathname);
  const location_ = `${location.origin}${path}${cleanQuery(search)}`;
  emit("page_view", {
    page_location: location_,
    page_path: path,
    page_title: path, // the page's own title can carry a company or headline, so the cleaned address stands in for it
    ...(lastLocation ? { page_referrer: lastLocation } : {}), // moving inside the app: the page before this one (the first page uses the real referrer)
  });
  lastLocation = location_;
}

export function trackEvent(name: string, params: Params = {}): void {
  if (!active() || !isMeasurable(location.pathname)) return;
  emit(name, params);
}

// The moments that matter, named once. Each sends numbers and labels only.
export const track = {
  signUp: () => trackEvent("sign_up", { method: "email" }),
  videoStarted: (flow: "guided" | "classic") => trackEvent("video_started", { flow }),
  videoReady: () => trackEvent("video_ready"),
  // Once per payment: coming back to the receipt page later must not count the same purchase again.
  purchase: (p: { id: string; value: number; currency: string; credits: number }) => {
    const key = `newsagent.ga.purchase.${p.id}`;
    try { if (sessionStorage.getItem(key)) return; if (active()) sessionStorage.setItem(key, "1"); } catch { /* storage unavailable: the id still lets Google ignore a repeat */ }
    trackEvent("purchase", { transaction_id: p.id, value: p.value, currency: p.currency, items: [{ item_id: "credits", item_name: "Credits", quantity: p.credits, price: p.credits ? p.value / p.credits : p.value }] });
  },
};

// Lets the browser tests call the real functions above. Only present in a build made with `--mode e2e`; a normal build leaves it out.
if (import.meta.env.MODE === "e2e") (window as unknown as { __ga?: unknown }).__ga = { track, trackPageView };
