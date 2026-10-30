import { useState } from "react";

type Point = { date: string; value: number | null };
export function AudienceChart({ points, label, cumulative = false }: { points: Point[]; label: string; cumulative?: boolean }) {
  const [table, setTable] = useState(false);
  const known = points.filter((p): p is Point & { value: number } => p.value !== null);
  const max = Math.max(1, ...known.map(p => p.value));
  const from = points.length ? Date.parse(points[0].date) : 0;
  const to = points.length ? Date.parse(points[points.length - 1].date) : 0;
  const x = (date: string) => from === to ? 360 : 50 + (Date.parse(date) - from) / (to - from) * 640;
  const y = (value: number) => 205 - value / max * 175;
  return <div className="min-w-0">
    {!known.length ? <p className="rounded-lg bg-paper p-6 text-sm text-muted">No reported measurements for this period. Missing data is not treated as zero.</p> : <svg viewBox="0 0 720 250" className="mt-3 h-auto min-h-44 w-full" role="img" aria-label={`${label} over time${cumulative ? ", cumulative reported figures" : ""}`}>
      {[0, .5, 1].map(f => <g key={f}><line x1="50" x2="690" y1={y(max * f)} y2={y(max * f)} stroke="#d7d7cf" strokeDasharray="4 4" /><text x="44" y={y(max * f) + 4} textAnchor="end" className="text-[20px] sm:text-[12px]" fill="#595959">{(max * f).toLocaleString(undefined, { notation: "compact", maximumFractionDigits: 1 })}</text></g>)}
      <polyline fill="none" stroke="#634EA0" strokeWidth="3" strokeLinejoin="round" points={known.map(p => `${x(p.date)},${y(p.value)}`).join(" ")} />
      {known.map(p => <circle key={p.date} cx={x(p.date)} cy={y(p.value)} r={known.length > 90 ? 2 : 4} fill="#634EA0" tabIndex={0} aria-label={`${p.date}: ${p.value.toLocaleString()} ${label}`}><title>{p.date}: {p.value.toLocaleString()} {label}</title></circle>)}
      <text x="50" y="235" className="text-[20px] sm:text-[12px]" fill="#595959">{points[0]?.date}</text><text x="690" y="235" textAnchor="end" className="text-[20px] sm:text-[12px]" fill="#595959">{points[points.length - 1]?.date}</text>
    </svg>}
    <p className="mt-2 text-xs text-muted">{cumulative ? "Points show cumulative figures on the dates reported by the publisher. Gaps have no new measurement." : "Daily recorded activity. Hover or focus a point for its count. Dates use UTC."}</p>
    <button className="mt-2 min-h-11 text-sm font-semibold underline" onClick={() => setTable(!table)}>{table ? "Hide" : "Show"} chart data</button>
    {table && <div className="max-h-72 overflow-auto"><table className="w-full text-sm"><caption className="sr-only">{label} chart data</caption><thead><tr><th className="p-2 text-left">Date (UTC)</th><th className="p-2 text-right">{label}</th></tr></thead><tbody>{points.map(p => <tr className="border-t border-line" key={p.date}><td className="p-2">{p.date}</td><td className="p-2 text-right tabular-nums">{p.value === null ? "Not reported" : p.value.toLocaleString()}</td></tr>)}</tbody></table></div>}
  </div>;
}
