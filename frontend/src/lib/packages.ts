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
// A card shows ONE currency: the amount in it, and the credits. A price the document states in a currency is shown exactly as written;
// any other currency is converted from the dollar price at the rates the operator sets. Customers are always charged in US dollars (credits).
export type Currency = { code: string; name: string; per_usd: string };
export type PackageList = { packages: MediaPackage[]; currencies: Currency[] };

const rateOf = (cs: Currency[], code: string) => Number(cs.find((c) => c.code === code)?.per_usd ?? 0);
/** A converted amount, rounded the way people read it: whole units once it is big, cents while it is small. */
function rounded(n: number): number { return n >= 100 ? Math.round(n) : Math.round(n * 100) / 100; }

/** What a package costs in a currency, or null when there is nothing to show it from (a quote with no listed price). */
export function priceIn(p: MediaPackage, code: string, cs: Currency[]): string | null {
  const stated = p.local_prices[code];
  if (stated) return money(code, stated);
  if (code === "USD" && p.usd_price) return usd(p.usd_price);
  const dollars = p.usd_price ?? p.usd_estimate;
  const rate = rateOf(cs, code);
  return dollars && rate ? money(code, rounded(Number(dollars) * rate)) : null;
}

/** The usual price (the strike-through) in the same currency. */
export function standardIn(p: MediaPackage, code: string, cs: Currency[]): string | null {
  if (!p.standard_usd) return null;
  if (code === "USD") return usd(p.standard_usd);
  const rate = rateOf(cs, code);
  return rate ? money(code, rounded(Number(p.standard_usd) * rate)) : null;
}

/** The currency a card opens in: the one its region uses in the document (Canada in Canadian dollars, Nigeria in naira, the UK in pounds,
 *  the Gulf in dirhams). Africa-wide, the US, the organisations and the campaign deals are priced in dollars. */
export function defaultCurrency(p: MediaPackage): string {
  const local = Object.keys(p.local_prices);
  const regional = p.kind === "regional" && ["nigeria", "canada", "uk_europe", "middle_east"].includes(p.region);
  if (regional && local.length) return local[0];
  return p.usd_price ? "USD" : local[0] ?? "USD";
}

/** What a card's picker offers: the currencies the document states for it first, then the rest. A package priced on request is never offered in dollars. */
export function optionsFor(p: MediaPackage, cs: Currency[]): Currency[] {
  const stated = [...(p.usd_price ? ["USD"] : []), ...Object.keys(p.local_prices)];
  const rank = (c: Currency) => { const i = stated.indexOf(c.code); return i < 0 ? 99 : i; };
  return cs.filter((c) => p.usd_price || c.code !== "USD").sort((a, b) => rank(a) - rank(b));
}
