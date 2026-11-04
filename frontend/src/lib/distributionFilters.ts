// Browsing outlets by topic and place, and remembering what a visitor chose until they have signed up.

export type OutletFilters = { topics: string[]; locations: { region: string; countries: string[] }[] };
export type Facets = { topic: string; region: string; country: string }; // "" means all
export const ALL: Facets = { topic: "", region: "", country: "" };
type Tagged = { topic?: string; region?: string; country?: string | null };

export function matches(o: Tagged, f: Facets): boolean {
  return (!f.topic || o.topic === f.topic) && (!f.region || o.region === f.region) && (!f.country || o.country === f.country);
}

/** How many outlets each choice would show, given the other choices (so a chip never promises something that is not there). */
export function counts<T extends Tagged>(outlets: T[], f: Facets, filters: OutletFilters) {
  const topic = Object.fromEntries(filters.topics.map((t) => [t, outlets.filter((o) => matches(o, { ...f, topic: t })).length]));
  const region = Object.fromEntries(filters.locations.map((l) => [l.region, outlets.filter((o) => matches(o, { ...f, region: l.region, country: "" })).length]));
  const country = Object.fromEntries(filters.locations.flatMap((l) => l.countries).map((c) => [c, outlets.filter((o) => matches(o, { ...f, country: c, region: "" })).length]));
  return { all: outlets.filter((o) => matches(o, f)).length, topic, region, country };
}

/** Say why a choice shows nothing: a place we have no outlets in yet, or just a combination with no match. */
export function emptyReason(outlets: Tagged[], f: Facets): string | null {
  if (outlets.some((o) => matches(o, f))) return null;
  const place = f.country || f.region;
  if (place && !outlets.some((o) => matches(o, { ...ALL, region: f.region, country: f.country }))) return `We have no outlets in ${place} yet. They are coming soon.`;
  return "No outlets match these choices. Try another topic or place.";
}

// ---------- the saved choice ----------
const PICK = "newsagent.distribution.pick";
const AFTER = "newsagent.afterAuth";
const WEEK = 7 * 24 * 3600 * 1000;
const ALLOWED_AFTER = "/distribution/request";

function read(key: string): string | null { try { return localStorage.getItem(key); } catch { return null; } }
function write(key: string, value: string | null) { try { if (value === null) localStorage.removeItem(key); else localStorage.setItem(key, value); } catch { /* storage may be unavailable; the page still works */ } }

export function savePick(ids: string[]) { write(PICK, JSON.stringify({ ids, at: Date.now() })); }
export function readPick(now = Date.now()): string[] {
  try {
    const v = JSON.parse(read(PICK) ?? "null") as { ids?: unknown; at?: number } | null;
    if (!v || !Array.isArray(v.ids) || typeof v.at !== "number" || now - v.at > WEEK) { if (v) write(PICK, null); return []; }
    return v.ids.filter((x): x is string => typeof x === "string");
  } catch { return []; }
}
export function clearPick() { write(PICK, null); }

/** Where to go once signed in. Only the distribution request page is allowed, so this can never become an open redirect. */
export function setAfterAuth(path: string) { if (isAllowedAfter(path)) write(AFTER, path); }
export function takeAfterAuth(): string | null {
  const p = read(AFTER);
  write(AFTER, null);
  return p && isAllowedAfter(p) ? p : null;
}
export function peekAfterAuth(): string | null { const p = read(AFTER); return p && isAllowedAfter(p) ? p : null; }
export function isAllowedAfter(path: string): boolean {
  return path === ALLOWED_AFTER || path.startsWith(`${ALLOWED_AFTER}?`);
}
