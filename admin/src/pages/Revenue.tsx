import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api, unwrap } from "../api/client";
import { Stat } from "../components/Charts";
import { Card, ErrorBox } from "../components/ui";
import { date, num, usd } from "../lib/format";

// Who is paying, how much, and every payment.
export function Revenue() {
  const q = useQuery({ queryKey: ["payments"], queryFn: () => unwrap(api.GET("/v1/admin/payments")) });
  if (q.isLoading) return <p aria-busy="true">Loading…</p>;
  if (q.error || !q.data) return <ErrorBox error={q.error ?? new Error("No data")} />;
  const p = q.data;
  return (
    <>
      <h1 className="text-2xl font-bold">Revenue</h1>
      <dl className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat label="Revenue, all time" value={usd(p.total_usd)} />
        <Stat label="Revenue, 30 days" value={usd(p.total_usd_30d)} />
        <Stat label="Paying companies" value={p.paying_companies.length} />
        <Stat label="Offline credits" value={num(p.offline_credits)} sub="bank transfers and invoices: only credits are recorded" />
      </dl>
      <Card title="Paying companies">
        {p.paying_companies.length === 0 ? <p className="text-sm text-muted">No payments yet.</p> : (
          <table className="w-full text-sm"><caption className="sr-only">Paying companies</caption>
            <thead><tr className="text-left text-muted"><th className="py-1">Company</th><th className="text-right">Payments</th><th className="text-right">Total paid</th><th>Last payment</th></tr></thead>
            <tbody>{p.paying_companies.map((c) => <tr key={c.workspace_id} className="border-t border-line"><td className="py-1.5 font-bold"><Link className="underline" to={`/customers/${c.workspace_id}`}>{c.company}</Link></td><td className="text-right tabular-nums">{c.payments}</td><td className="text-right tabular-nums">{usd(c.usd)}</td><td>{date(c.last_paid_at)}</td></tr>)}</tbody>
          </table>
        )}
      </Card>
      <Card title="Payments">
        {p.items.length === 0 ? <p className="text-sm text-muted">Nothing to show.</p> : (
          <div className="overflow-x-auto">
            <table className="w-full text-sm"><caption className="sr-only">Payments, newest first</caption>
              <thead><tr className="text-left text-muted"><th className="py-1">When</th><th>Company</th><th>Type</th><th className="text-right">Amount</th><th className="text-right">Credits</th></tr></thead>
              <tbody>{p.items.map((r, i) => <tr key={i} className="border-t border-line"><td className="py-1.5">{date(r.when)}</td><td><Link className="underline" to={`/customers/${r.workspace_id}`}>{r.company}</Link></td><td>{r.kind === "card" ? `Card${r.provider ? ` (${r.provider})` : ""}` : "Offline"}</td><td className="text-right tabular-nums">{r.usd == null ? "not recorded" : usd(r.usd)}</td><td className="text-right tabular-nums">{num(r.credits)}</td></tr>)}</tbody>
            </table>
          </div>
        )}
      </Card>
    </>
  );
}
