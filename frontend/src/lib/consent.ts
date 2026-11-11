// The visitor's choice about analytics cookies. Nothing from Google loads until they say yes.
// A "Do Not Track" or "Global Privacy Control" signal from the browser is a standing no, whatever was clicked before.
const KEY = "newsagent.analytics-consent";

export type Consent = "granted" | "denied";
type Listener = (c: Consent | null) => void;
const listeners = new Set<Listener>();

export function browserOptOut(): boolean {
  if (typeof navigator === "undefined") return false;
  return navigator.doNotTrack === "1" || !!(navigator as Navigator & { globalPrivacyControl?: boolean }).globalPrivacyControl;
}

export function getConsent(): Consent | null {
  if (browserOptOut()) return "denied";
  try {
    const v = localStorage.getItem(KEY);
    return v === "granted" || v === "denied" ? v : null;
  } catch {
    return null; // storage blocked: ask again next time rather than assume yes
  }
}

export function setConsent(c: Consent | null): void {
  try {
    if (c === null) localStorage.removeItem(KEY);
    else localStorage.setItem(KEY, c);
  } catch { /* storage unavailable: the choice lasts until the page is closed */ }
  listeners.forEach((l) => l(browserOptOut() ? "denied" : c));
}

export function onConsentChange(l: Listener): () => void {
  listeners.add(l);
  return () => { listeners.delete(l); };
}

// "Cookie settings" in the footer asks the banner to open again.
const REOPEN = "newsagent:cookie-settings";
export const openCookieSettings = () => window.dispatchEvent(new Event(REOPEN));
export const onOpenCookieSettings = (fn: () => void) => { window.addEventListener(REOPEN, fn); return () => window.removeEventListener(REOPEN, fn); };
