import { browserOptOut } from "./consent";
import { cleanPath, isMeasurable } from "./ga";

// Our own cookie-free visit counter. Nothing is stored on the visitor's device and no cookie is set: the server turns the visitor's
// address and browser into a one-way code that changes every day. It counts everyone, whatever they chose about cookies, except
// browsers that send "Do Not Track" or "Global Privacy Control", and it never counts the back office or private links.
let firstOfLoad = true;

// Only the other website's name, and only when they arrived from elsewhere. Moving around inside our own site isn't "arriving".
function externalReferrerHost(): string {
  try {
    const host = new URL(document.referrer).hostname;
    return host && host !== location.hostname ? host : "";
  } catch {
    return "";
  }
}

export function recordVisit(pathname: string, search: string): void {
  if (browserOptOut() || !isMeasurable(pathname)) return;
  const q = new URLSearchParams(search);
  const body = {
    path: cleanPath(pathname),
    referrer_host: firstOfLoad ? externalReferrerHost() : "",
    utm_source: firstOfLoad ? (q.get("utm_source") ?? "") : "",
    utm_medium: firstOfLoad ? (q.get("utm_medium") ?? "") : "",
    utm_campaign: firstOfLoad ? (q.get("utm_campaign") ?? "") : "",
  };
  firstOfLoad = false;
  try {
    void fetch(`${import.meta.env.VITE_API_URL ?? ""}/v1/public/visit`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(body), keepalive: true, credentials: "omit" }).catch(() => { /* counting must never get in anyone's way */ });
  } catch { /* same */ }
}
