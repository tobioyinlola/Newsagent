import { getConsent } from "./consent";

// Google Analytics 4, used with care, in Google's "advanced Consent Mode":
//  - it is off unless VITE_GA_MEASUREMENT_ID is set for the build;
//  - until a visitor chooses it counts their visit WITHOUT cookies; if they accept, it also uses cookies; if they decline, it is switched off;
//  - the private pages (founder interview links, private share links, the back office) are never measured;
//  - addresses are cleaned before they are sent, so no private link code, checkout number or project number ever reaches Google;
//  - no names, emails or company names are sent: only what a page is, and what step someone reached.
export const GA_ID: string = String(import.meta.env.VITE_GA_MEASUREMENT_ID ?? "").trim();
export const gaConfigured = /^G-[A-Z0-9]{6,}$/.test(GA_ID);

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

let started = false;
// Sending is allowed unless they declined (or their browser sent a privacy signal, which getConsent() reports as "denied").
const active = () => gaConfigured && started && getConsent() !== "denied" && typeof window.gtag === "function";

// Google's script reads an `arguments` object from the data layer, not an array, so this has to be a plain function.
// eslint-disable-next-line @typescript-eslint/no-unused-vars
function gtag(..._args: unknown[]) {
  window.dataLayer = window.dataLayer ?? [];
  // eslint-disable-next-line prefer-rest-params
  window.dataLayer.push(arguments);
}

// Called on the first measurable page, and again when their choice changes. Cookies are used only after an explicit Accept; until then Google
// gets cookie-free page views, and after Decline or a privacy signal it gets nothing at all.
export function startAnalytics(): void {
  const consent = getConsent();
  if (!gaConfigured || consent === "denied") return;
  window[`ga-disable-${GA_ID}`] = false;
  const storage = consent === "granted" ? "granted" : "denied";
  if (started) { window.gtag?.("consent", "update", { analytics_storage: storage }); return; }
  started = true;
  window.dataLayer = window.dataLayer ?? [];
  window.gtag = gtag;
  // Advertising features stay off for everyone. Analytics cookies are off until they accept.
  gtag("consent", "default", { ad_storage: "denied", ad_user_data: "denied", ad_personalization: "denied", analytics_storage: storage });
  gtag("set", "ads_data_redaction", true);
  gtag("js", new Date());
  gtag("config", GA_ID, {
    send_page_view: false, // the app is one page: we send each page view ourselves, with a cleaned address
    allow_google_signals: false,
    allow_ad_personalization_signals: false,
    cookie_expires: 34128000, // 13 months, the longest regulators accept
    cookie_flags: "SameSite=Lax;Secure",
  });
  const s = document.createElement("script");
  s.async = true;
  s.src = `https://www.googletagmanager.com/gtag/js?id=${encodeURIComponent(GA_ID)}`;
  document.head.appendChild(s);
}

// They said no, or changed their mind: stop sending, and remove what Google set.
export function stopAnalytics(): void {
  if (!gaConfigured) return;
  window[`ga-disable-${GA_ID}`] = true;
  window.gtag?.("consent", "update", { analytics_storage: "denied" });
  const names = ["_ga", `_ga_${GA_ID.replace(/^G-/, "")}`, "_gid", "_gat"];
  const host = location.hostname;
  const parent = host.split(".").length > 2 ? host.split(".").slice(-2).join(".") : host;
  for (const n of names) for (const d of [host, `.${host}`, `.${parent}`]) document.cookie = `${n}=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/; domain=${d}`;
  for (const n of names) document.cookie = `${n}=; expires=Thu, 01 Jan 1970 00:00:00 GMT; path=/`;
}

export function trackPageView(pathname: string, search: string): void {
  if (!active() || !isMeasurable(pathname)) return;
  const path = cleanPath(pathname);
  window.gtag!("event", "page_view", {
    page_location: `${location.origin}${path}${cleanQuery(search)}`,
    page_path: path,
    page_title: path, // the page's own title can carry a company or headline, so the cleaned address stands in for it
  });
}

export function trackEvent(name: string, params: Params = {}): void {
  if (!active() || !isMeasurable(location.pathname)) return;
  window.gtag!("event", name, params);
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
