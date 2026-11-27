// Ready-made media packages: the shapes the server sends, and how their prices are written.
export type MediaPackage = {
  id: string; slug: string; kind: "regional" | "organisation" | "campaign"; region: string; campaign: "" | "black_friday" | "cyber_monday";
  name: string; usd_price: string | null; standard_usd: string | null; percent_off: number | null; credits: string | null;
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
