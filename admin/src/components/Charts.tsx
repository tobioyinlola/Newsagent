import type { ReactNode } from "react";

type Point = { label: string; value: number };

// A small bar chart in the brand's colours. The data is also available as a table for screen readers.
export function Bars({ title, points, format = (n) => String(n), color = "bg-brand-purple" }: { title: string; points: Point[]; format?: (n: number) => string; color?: string }) {
  const max = Math.max(1, ...points.map((p) => p.value));
  const total = points.reduce((n, p) => n + p.value, 0);
  return (
    <figure className="space-y-2">
      <figcaption className="flex items-baseline justify-between gap-2">
        <span className="font-mono text-sm font-bold">{title}</span>
        <span className="text-sm text-muted">{format(total)} in total</span>
      </figcaption>
      <div className="flex h-36 items-end gap-[3px] border-b-2 border-ink" role="img" aria-label={`${title}: ${format(total)} over ${points.length} days`}>
        {points.map((p) => (
          <div key={p.label} className="group relative flex h-full flex-1 items-end" title={`${p.label}: ${format(p.value)}`}>
            <div className={`w-full ${p.value ? color : "bg-line"}`} style={{ height: `${p.value ? Math.max(4, (p.value / max) * 100) : 2}%` }} />
          </div>
        ))}
      </div>
      <div className="flex justify-between text-xs text-muted"><span>{points[0]?.label}</span><span>{points[points.length - 1]?.label}</span></div>
      <table className="sr-only"><caption>{title}</caption><thead><tr><th>Day</th><th>Value</th></tr></thead><tbody>{points.map((p) => <tr key={p.label}><td>{p.label}</td><td>{format(p.value)}</td></tr>)}</tbody></table>
    </figure>
  );
}

// Horizontal bars for a handful of labelled counts (a funnel, videos by state).
export function HBars({ title, rows, color = "bg-brand-purple" }: { title: string; rows: { label: string; value: number }[]; color?: string }) {
  const max = Math.max(1, ...rows.map((r) => r.value));
  return (
    <figure className="space-y-2">
      <figcaption className="font-mono text-sm font-bold">{title}</figcaption>
      {rows.length === 0 ? <p className="text-sm text-muted">Nothing yet.</p> : (
        <ul className="space-y-1.5">
          {rows.map((r) => (
            <li key={r.label} className="grid grid-cols-[8.5rem_1fr_2.5rem] items-center gap-2 text-sm">
              <span className="truncate capitalize">{r.label.replace(/_/g, " ")}</span>
              <span className="h-4 bg-paper"><span className={`block h-full ${color}`} style={{ width: `${(r.value / max) * 100}%` }} /></span>
              <span className="text-right font-bold tabular-nums">{r.value}</span>
            </li>
          ))}
        </ul>
      )}
    </figure>
  );
}

export function Stat({ label, value, sub, tone }: { label: string; value: ReactNode; sub?: ReactNode; tone?: "good" | "warn" }) {
  return (
    <div className={`rounded-md border-2 border-ink p-4 ${tone === "warn" ? "bg-peach-tint" : "bg-white"}`}>
      <dt className="text-sm text-muted">{label}</dt>
      <dd className="mt-1 font-mono text-3xl font-bold tabular-nums">{value}</dd>
      {sub && <p className="mt-1 text-xs text-muted">{sub}</p>}
    </div>
  );
}
