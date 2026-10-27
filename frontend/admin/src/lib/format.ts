export const usd = (v: string | number) => new Intl.NumberFormat("en-US", { style: "currency", currency: "USD", maximumFractionDigits: Number(v) % 1 === 0 ? 0 : 2 }).format(Number(v));
export const num = (v: string | number) => new Intl.NumberFormat("en-US", { maximumFractionDigits: 1 }).format(Number(v));
export const date = (v: string | null | undefined) => (v ? new Date(v).toLocaleDateString(undefined, { day: "numeric", month: "short", year: "numeric" }) : "never");
export const ago = (v: string | null | undefined) => {
  if (!v) return "never";
  const s = (Date.now() - new Date(v).getTime()) / 1000;
  if (s < 90) return "just now";
  if (s < 3600) return `${Math.round(s / 60)} min ago`;
  if (s < 86400) return `${Math.round(s / 3600)} h ago`;
  if (s < 86400 * 30) return `${Math.round(s / 86400)} d ago`;
  return date(v);
};
export const shortDay = (iso: string) => new Date(iso + "T00:00:00").toLocaleDateString(undefined, { day: "numeric", month: "short" });
