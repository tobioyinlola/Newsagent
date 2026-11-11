import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api, unwrap } from "../api/client";
import { Card, ErrorBox, inputCls } from "./ui";
import { Bars, Stat } from "./Charts";
import { num } from "../lib/format";

type Report = { start: string; end: string; totals: { visitors: number; pageviews: number }; series: { date: string; visitors: number; pageviews: number }[]; pages: { path: string; views: number }[]; sources: { source: string; detail: string; visitors: number }[]; definitions: Record<string, string> };
const SOURCE: Record<string, string> = { direct: "Direct (typed the address, or a bookmark)", search: "Search", social: "Social media", email: "Our emails", referral: "Another website", other: "Other" };
// A ranked list with the full label always readable, and a bar to compare sizes.
function Ranked({ title, rows }: { title: string; rows: { label: string; value: number }[] }) {
  const max = Math.max(1, ...rows.map((r) => r.value));
  return (
    <ol aria-label={title} className="space-y-2.5">
      {rows.map((r) => (
        <li key={r.label} className="text-sm">
          <div className="flex items-baseline justify-between gap-3"><span className="min-w-0 break-words">{r.label}</span><span className="shrink-0 font-semibold tabular-nums">{num(r.value)}</span></div>
          <div className="mt-1 h-2 overflow-hidden rounded-full bg-line" aria-hidden="true"><div className="h-full bg-brand-green" style={{ width: `${Math.max(2, (r.value / max) * 100)}%` }} /></div>
        </li>
      ))}
    </ol>
  );
}

const iso = (offsetDays: number) => { const d = new Date(); d.setUTCDate(d.getUTCDate() + offsetDays); return d.toISOString().slice(0, 10); };

// How many people visit the public website and customer app, counted by us without cookies. Includes visitors who never answered
// (or who declined) the cookie notice; excludes robots, privacy-signal browsers, the back office and private links.
export function SiteVisits() {
  const [days, setDays] = useState(30);
  const q = useQuery({
    queryKey: ["site-visits", days],
    queryFn: () => unwrap(api.GET("/v1/admin/site-visits", { params: { query: { start: iso(-(days - 1)), end: iso(0) } } })) as unknown as Promise<Report>,
  });
  const r = q.data;
  return (
    <Card title="Website visitors" actions={<label className="flex items-center gap-2 text-sm font-semibold">Show<select aria-label="Period" className={`${inputCls} !w-auto`} value={days} onChange={(e) => setDays(Number(e.target.value))}><option value={7}>the last 7 days</option><option value={30}>the last 30 days</option><option value={90}>the last 90 days</option></select></label>}>
      <ErrorBox error={q.error} />
      {q.isLoading ? <p aria-busy="true">Loading…</p> : r && (
        <div className="space-y-6">
          <p className="max-w-3xl text-sm text-muted">Everyone who visits the website, counted by us without cookies, whether or not they accepted the cookie notice. {r.definitions.excluded}</p>
          <dl className="grid grid-cols-2 gap-3 md:grid-cols-3">
            <Stat label="Visitors" value={num(r.totals.visitors)} sub="each counted once a day" />
            <Stat label="Page views" value={num(r.totals.pageviews)} sub="screens opened" />
            <Stat label="Pages per visit" value={r.totals.visitors ? (r.totals.pageviews / r.totals.visitors).toFixed(1) : "–"} />
          </dl>
          <Bars title="Visitors each day" points={r.series.map((s) => ({ label: s.date, value: s.visitors }))} format={num} />
          <div className="grid gap-6 md:grid-cols-2">
            <div>
              <h3 className="mb-2 font-mono text-sm font-bold">Where visitors came from</h3>
              {r.sources.length ? <Ranked title="Sources" rows={r.sources.map((s) => ({ label: `${SOURCE[s.source] ?? s.source}${s.detail ? ` · ${s.detail}` : ""}`, value: s.visitors }))} /> : <p className="text-sm text-muted">No visits yet in this period.</p>}
            </div>
            <div>
              <h3 className="mb-2 font-mono text-sm font-bold">Most visited pages</h3>
              {r.pages.length ? <Ranked title="Pages" rows={r.pages.slice(0, 10).map((p) => ({ label: p.path, value: p.views }))} /> : <p className="text-sm text-muted">No visits yet in this period.</p>}
            </div>
          </div>
          <p className="text-xs text-muted">{r.definitions.visitors}</p>
        </div>
      )}
    </Card>
  );
}
