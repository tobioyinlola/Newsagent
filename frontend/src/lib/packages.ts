// Ready-made media packages: the shapes the server sends, and how their prices are written.
export type MediaPackage = {
  id: string; slug: string; kind: "regional" | "organisation" | "campaign"; region: string; campaign: "" | "black_friday" | "cyber_monday";
  name: string; usd_price: string | null; usd_estimate?: string | null; standard_usd: string | null; percent_off: number | null; credits: string | null;
  local_prices: Record<string, string>; outlets: string[]; includes: string[]; ideal_for: string; note: string;
  slots_total: number | null; slots_left: number | null; ends_at: string | null;
  state: "open" | "quote" | "not_started" | "ended" | "sold_out" | "off";
};

export const PACKAGE_TABS: { key: string; label: string }[] = [
  { key: "campaign", label: "Black Friday & Cyber Monday" },
  { key: "nigeria", label: "Nigeria & West Africa" },
  { key: "africa", label: "Africa-wide" },
  { key: "us", label: "United States" },
  { key: "canada", label: "Canada" },
  { key: "uk_europe", label: "UK & Europe" },
  { key: "middle_east", label: "Middle East" },
  { key: "organisation", label: "Organisations" },
];

const tab = (p: MediaPackage) => (p.kind === "campaign" ? "campaign" : p.kind === "organisation" ? "organisation" : p.region);
/** The tabs that have something to show, in the usual order. A closed campaign leaves its tab. */
export function tabsFor(packages: MediaPackage[]) {
  const live = new Set(packages.filter((p) => p.kind !== "campaign" || !["ended", "off"].includes(p.state)).map(tab));
  return PACKAGE_TABS.filter((t) => live.has(t.key));
}
export const inTab = (packages: MediaPackage[], key: string) => packages.filter((p) => tab(p) === key && (p.kind !== "campaign" || !["ended", "off"].includes(p.state)));

const SYMBOL: Record<string, string> = { NGN: "₦", GBP: "£", EUR: "€", USD: "US$", CAD: "C$", GHS: "GH₵", KES: "KSh ", UGX: "USh ", CHF: "CHF ", AED: "AED ", QAR: "QAR " };
export function money(code: string, amount: string | number): string {
  const n = Number(amount);
  const hasCents = Math.abs(n - Math.round(n)) > 0.004;
  return `${SYMBOL[code] ?? `${code} `}${n.toLocaleString("en-US", { minimumFractionDigits: hasCents ? 2 : 0, maximumFractionDigits: 2 })}`;
}
export const usd = (amount: string | number) => money("USD", amount);

export const quoteMail = (p: MediaPackage) => `mailto:coverfounder@gmail.com?subject=${encodeURIComponent(`Quote request: ${p.name}`)}&body=${encodeURIComponent(`Hello Cover Founder team,\n\nPlease send me a quote for "${p.name}".\n\nMy name:\nMy company:\n`)}`;

export function endsText(iso: string | null): string {
  if (!iso) return "";
  return `Ends ${new Date(iso).toLocaleDateString("en-GB", { day: "numeric", month: "long", timeZone: "Africa/Lagos" })}`;
}

// ---------- prices in other currencies ----------
// Display only: a customer is always charged in US dollars (as credits). A price the document states in a currency is shown exactly;
// every other currency is converted from the dollar price at the rates the operator sets, and marked "≈".
export type Currency = { code: string; name: string; per_usd: string };
export type PackageList = { packages: MediaPackage[]; currencies: Currency[] };
export type Shown = { text: string; approx: boolean };

const rateOf = (cs: Currency[], code: string) => Number(cs.find((c) => c.code === code)?.per_usd ?? 0);
/** A converted amount, rounded the way people read it: whole units once it is big, cents while it is small. */
function rounded(n: number): number { return n >= 100 ? Math.round(n) : Math.round(n * 100) / 100; }

/** What a package costs in a currency. Null when there is no price to show (a quote with nothing to convert from). */
export function priceIn(p: MediaPackage, code: string, cs: Currency[]): Shown | null {
  const stated = p.local_prices[code];
  if (stated) return { text: money(code, stated), approx: false };
  if (code === "USD" && p.usd_price) return { text: usd(p.usd_price), approx: false };
  const dollars = p.usd_price ?? p.usd_estimate;
  const rate = rateOf(cs, code);
  if (!dollars || !rate) return null;
  return { text: money(code, rounded(Number(dollars) * rate)), approx: true };
}

/** The usual price (the strike-through) in the same currency, converted. */
export function standardIn(p: MediaPackage, code: string, cs: Currency[]): string | null {
  if (!p.standard_usd) return null;
  if (code === "USD") return usd(p.standard_usd);
  const rate = rateOf(cs, code);
  return rate ? money(code, rounded(Number(p.standard_usd) * rate)) : null;
}

// Where a visitor probably is, so the first thing they see is a price they recognise. They can change it, and it is remembered.
const ZONES: Record<string, string> = {
  "Africa/Lagos": "NGN", "Africa/Accra": "GHS", "Africa/Nairobi": "KES", "Africa/Kampala": "UGX", "Europe/London": "GBP",
  "America/Toronto": "CAD", "America/Vancouver": "CAD", "America/Edmonton": "CAD", "America/Winnipeg": "CAD", "America/Halifax": "CAD",
  "Asia/Dubai": "AED", "Asia/Qatar": "QAR", "Europe/Zurich": "CHF",
};
const KEY = "cf-package-currency";
export function startingCurrency(cs: Currency[]): string {
  const ok = (c: string | null | undefined): c is string => !!c && cs.some((x) => x.code === c);
  try { const saved = localStorage.getItem(KEY); if (ok(saved)) return saved; } catch { /* private window */ }
  try {
    const zone = Intl.DateTimeFormat().resolvedOptions().timeZone;
    const guess = ZONES[zone] ?? (zone?.startsWith("Europe/") ? "EUR" : "USD");
    if (ok(guess)) return guess;
  } catch { /* old browser */ }
  return "USD";
}
export function rememberCurrency(code: string) { try { localStorage.setItem(KEY, code); } catch { /* private window */ } }
