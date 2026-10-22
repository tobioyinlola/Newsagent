import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api, unwrap } from "../../api/client";
import { Button, Card, ErrorBox } from "../ui";
import { downloadAuthed } from "../../lib/download";

const usd = (v: string | number) => `$${Number(v).toFixed(4)}`;

export function Costs() {
  const r = useQuery({ queryKey: ["admin-costs"], queryFn: () => unwrap(api.GET("/v1/admin/cost-report", { params: { query: { days: 90 } } })) });
  const [err, setErr] = useState<string | null>(null);
  const s = r.data?.summary;
  return (
    <>
      <Card title="Cost per finished video (last 90 days)" actions={<Button variant="secondary" onClick={() => downloadAuthed("/v1/admin/cost-report.csv?days=90", "cost-report.csv").catch((e) => setErr(e.message))}>Download CSV</Button>}>
        <ErrorBox error={r.error ?? (err ? new Error(err) : null)} />
        {s && (
          <dl className="grid gap-4 sm:grid-cols-4">
            {[["Finished videos", String(s.videos)], ["Avg vendor cost", usd(s.avg_vendor_cost)], ["Avg credits charged", Number(s.avg_credits_charged).toFixed(4)], ["Avg margin", usd(s.avg_margin)]].map(([k, v]) => (
              <div key={k}><dt className="text-sm text-muted">{k}</dt><dd className={`text-2xl font-bold tabular-nums ${k === "Avg margin" && Number(s.avg_margin) < 0 ? "bg-red-tint px-1 text-ink" : ""}`}>{v}</dd></div>
            ))}
          </dl>
        )}
        {s && <p className="mt-3 text-xs text-muted">Markup {Number(s.markup)}× and ${Number(s.usd_per_credit).toFixed(2)} per credit. Margin = credits charged × price per credit − what vendors charged us. Gate 3 needs real numbers for 10 pilot videos.</p>}
      </Card>
      <Card title="By video">
        <div className="overflow-x-auto"><table className="w-full text-sm"><caption className="sr-only">Cost by video</caption>
          <thead><tr className="text-left text-muted"><th className="py-1">Video</th><th>Workspace</th><th>State</th><th>Type</th><th className="text-right">Vendor cost</th><th className="text-right">Charged</th><th className="text-right">Margin</th><th>By vendor</th></tr></thead>
          <tbody>{r.data?.rows.map((x) => (
            <tr key={x.project_id} className="border-t border-line"><td className="py-1">{x.project_id.slice(0, 6)}</td><td>{x.workspace_name}</td><td>{x.state.replace("_", " ")}</td><td>{x.interview ? "interview" : "anchor"}</td>
              <td className="text-right tabular-nums">{usd(x.vendor_cost)}</td><td className="text-right tabular-nums">{Number(x.credits_charged).toFixed(4)}</td><td className={`text-right tabular-nums ${Number(x.margin) < 0 ? "bg-red-tint px-1 font-bold text-ink" : ""}`}>{usd(x.margin)}</td>
              <td className="text-xs">{Object.entries(x.by_vendor).map(([k, v]) => `${k} ${usd(v)}`).join(" · ")}</td></tr>))}</tbody></table></div>
      </Card>
    </>
  );
}
