import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { api, unwrap } from "../api/client";
import { Bars, HBars, Stat } from "../components/Charts";
import { Card, ErrorBox, Notice } from "../components/ui";
import { ago, num, shortDay, usd } from "../lib/format";

const RANGES = [30, 60, 90] as const;

// The business at a glance: who signed up, who is paying, how videos are doing, what needs a person.
export function Overview() {
  const [days, setDays] = useState<(typeof RANGES)[number]>(30);
  const q = useQuery({ queryKey: ["overview", days], queryFn: () => unwrap(api.GET("/v1/admin/overview", { params: { query: { days } } })), refetchInterval: 30000 });
  if (q.isLoading) return <p aria-busy="true">Loading…</p>;
  if (q.error || !q.data) return <ErrorBox error={q.error ?? new Error("No data")} />;
  const { kpis: k, funnel, attention: a, signups_by_day, revenue_by_day, videos_by_state, recent_signups, top_customers } = q.data;
  const margin = Number(k.revenue_usd_30d) - Number(k.vendor_cost_usd_30d);
  const attention = [
    a.paused && <Notice key="p" tone="warn"><strong>Paid steps are paused.</strong> No videos are being made. <Link className="underline" to="/operations">Open Operations</Link> to resume.</Notice>,
    a.pending_reviews > 0 && <Notice key="r" tone="warn"><strong>{a.pending_reviews} item{a.pending_reviews === 1 ? "" : "s"} waiting for review.</strong> Customers are waiting on these. <Link className="underline" to="/review">Review now</Link></Notice>,
    a.failed_videos > 0 && <Notice key="f" tone="warn"><strong>{a.failed_videos} video{a.failed_videos === 1 ? "" : "s"} failed or stopped at a limit.</strong> <Link className="underline" to="/jobs">See jobs</Link></Notice>,
    a.suspended_workspaces > 0 && <Notice key="s" tone="info">{a.suspended_workspaces} suspended workspace{a.suspended_workspaces === 1 ? "" : "s"}. <Link className="underline" to="/customers">Customers</Link></Notice>,
  ].filter(Boolean);
  return (
    <>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-bold">Overview</h1>
        <div role="group" aria-label="Chart range" className="flex gap-1">
          {RANGES.map((r) => <button key={r} type="button" aria-pressed={days === r} onClick={() => setDays(r)} className={`rounded-sm border-2 border-ink px-3 py-1 text-sm font-bold ${days === r ? "bg-ink text-white" : "bg-white"}`}>{r} days</button>)}
        </div>
      </div>
      {attention.length > 0 && <div className="space-y-2" aria-label="Needs attention">{attention}</div>}

      <dl className="grid grid-cols-2 gap-3 md:grid-cols-4" aria-label="Key figures">
        <Stat label="Customers" value={k.customers} sub={`${k.active_30d} active in the last 30 days`} />
        <Stat label="New sign-ups" value={k.signups_7d} sub={`this week · ${k.signups_30d} in 30 days`} />
        <Stat label="Paying companies" value={k.paying_companies} sub={k.customers ? `${Math.round((k.paying_companies / k.customers) * 100)}% of customers` : "no customers yet"} />
        <Stat label="Revenue, 30 days" value={usd(k.revenue_usd_30d)} sub={`${usd(k.revenue_usd_total)} all time`} />
        <Stat label="Videos, 30 days" value={k.videos_30d} sub={`${k.videos_ready} finished · ${k.videos_total} all time`} />
        <Stat label="Vendor cost, 30 days" value={usd(k.vendor_cost_usd_30d)} sub="what vendors charged us" />
        <Stat label="Margin, 30 days" value={usd(margin)} sub="revenue less vendor cost (estimate)" tone={margin < 0 ? "warn" : undefined} />
        <Stat label="Credits outstanding" value={num(k.credits_outstanding)} sub="held by customers, not yet used" />
      </dl>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card><Bars title="New sign-ups per day" points={signups_by_day.map((d) => ({ label: shortDay(d.date), value: d.count }))} /></Card>
        <Card><Bars title="Revenue per day" color="bg-brand-green" format={usd} points={revenue_by_day.map((d) => ({ label: shortDay(d.date), value: Number(d.usd) }))} /></Card>
      </div>

      <div className="grid gap-4 lg:grid-cols-2">
        <Card><HBars title="Invites" rows={[{ label: "sent", value: funnel.invites_sent }, { label: "signed up", value: funnel.accepted }, { label: "waiting", value: funnel.pending }, { label: "expired", value: funnel.expired }]} /></Card>
        <Card><HBars title="Videos by stage" color="bg-brand-green" rows={Object.entries(videos_by_state).sort((x, y) => y[1] - x[1]).map(([label, value]) => ({ label, value }))} /></Card>
      </div>

      <Card title="Latest sign-ups" actions={<Link className="text-sm font-bold underline" to="/customers">All customers</Link>}>
        {recent_signups.length === 0 ? <p className="text-sm text-muted">No one has signed up yet. Create an invite under Setup.</p> : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm"><caption className="sr-only">Latest sign-ups</caption>
              <thead><tr className="text-left text-muted"><th className="py-1">Company</th><th>Owner</th><th>Signed up</th><th>Last seen</th><th className="text-right">Videos</th><th className="text-right">Credits</th><th>Paying</th></tr></thead>
              <tbody>{recent_signups.map((s) => (
                <tr key={s.workspace_id} className="border-t border-line">
                  <td className="py-1.5 font-bold"><Link className="underline" to={`/customers/${s.workspace_id}`}>{s.company}</Link></td>
                  <td>{s.email}</td><td>{ago(s.signed_up_at)}</td><td>{ago(s.last_login_at)}</td>
                  <td className="text-right tabular-nums">{s.videos}</td><td className="text-right tabular-nums">{num(s.credits)}</td>
                  <td>{s.paid ? <span className="rounded-sm bg-brand-green px-1.5 py-0.5 text-xs font-bold">Paying</span> : <span className="text-muted">Not yet</span>}</td>
                </tr>))}</tbody>
            </table>
          </div>
        )}
      </Card>

      {top_customers.length > 0 && (
        <Card title="Top customers" actions={<Link className="text-sm font-bold underline" to="/revenue">Revenue</Link>}>
          <table className="w-full text-sm"><caption className="sr-only">Top customers</caption>
            <thead><tr className="text-left text-muted"><th className="py-1">Company</th><th className="text-right">Paid</th><th className="text-right">Videos</th><th>Last video</th></tr></thead>
            <tbody>{top_customers.map((c) => <tr key={c.workspace_id} className="border-t border-line"><td className="py-1.5 font-bold"><Link className="underline" to={`/customers/${c.workspace_id}`}>{c.company}</Link></td><td className="text-right tabular-nums">{usd(c.revenue_usd)}</td><td className="text-right tabular-nums">{c.videos}</td><td>{ago(c.last_video_at)}</td></tr>)}</tbody>
          </table>
        </Card>
      )}
    </>
  );
}
