import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useNavigate, useParams, useSearchParams } from "react-router-dom";
import { api, unwrap } from "../api/client";
import { Button, Card, ErrorBox, Notice } from "../components/ui";
import { downloadAuthed } from "../lib/download";

const money = (v: string | number) => Number(v).toLocaleString(undefined, { style: "currency", currency: "USD" });
const KIND: Record<string, string> = { grant: "Credits added", purchase: "Purchase", adjustment: "Adjustment", usage: "Used", usage_adjust: "Usage correction", usage_release: "Refunded (step didn't run)" };

export function Billing() {
  const qc = useQueryClient();
  const [params] = useSearchParams();
  const [month, setMonth] = useState(new Date().toISOString().slice(0, 7));
  const summary = useQuery({ queryKey: ["billing-summary"], queryFn: () => unwrap(api.GET("/v1/billing/summary")) });
  const packs = useQuery({ queryKey: ["packs"], queryFn: () => unwrap(api.GET("/v1/billing/packs")) });
  const usage = useQuery({ queryKey: ["usage", month], queryFn: () => unwrap(api.GET("/v1/billing/usage", { params: { query: { month } } })) });
  const ledger = useQuery({ queryKey: ["ledger"], queryFn: () => unwrap(api.GET("/v1/billing/ledger", { params: { query: { limit_: 50 } } })) });
  const buy = useMutation({
    mutationFn: (pack_id: string) => unwrap(api.POST("/v1/billing/checkout", { body: { pack_id } })),
    onSuccess: (d) => { qc.invalidateQueries({ queryKey: ["me"] }); window.location.assign(d.url); },
  });
  const [csvErr, setCsvErr] = useState<string | null>(null);
  const s = summary.data;
  const low = s && Number(s.credit_balance) < Number(s.low_balance_threshold);

  return (
    <>
      <h1 className="text-2xl font-bold">Credits and billing</h1>
      {params.get("paid") && <Notice tone="ok">Payment received. Your credits have been added.</Notice>}
      <Card title="Your balance">
        <p className="text-4xl font-extrabold tabular-nums" aria-label="Credit balance">{s ? Number(s.credit_balance).toFixed(2) : "…"} <span className="text-lg font-medium text-muted">credits</span></p>
        {low && <div className="mt-3"><Notice tone="warn">You're running low. Add credits so your next video isn't paused.</Notice></div>}
        {s && <p className="mt-2 text-sm text-muted">Up to {s.max_videos_per_day} videos a day. A typical video uses a few credits; every video shows its cost on the project page.</p>}
      </Card>
      <Card title="Add credits">
        {packs.data?.length ? (
          <ul className="grid gap-3 sm:grid-cols-3">
            {packs.data.map((p) => (
              <li key={p.id} className="rounded-md border border-line p-4">
                <p className="font-semibold">{p.name}</p>
                <p className="text-2xl font-bold">{Number(p.credits).toFixed(0)} credits</p>
                <p className="mb-3 text-muted">{money(p.price_usd)}</p>
                <Button onClick={() => buy.mutate(p.id)} disabled={buy.isPending} aria-label={`Buy ${p.name}`}>Buy</Button>
              </li>
            ))}
          </ul>
        ) : <p className="text-muted">Credit packs aren't available yet. Contact us to add credits.</p>}
        <ErrorBox error={buy.error} />
      </Card>
      <Card title="Usage" actions={
        <span className="flex items-center gap-2">
          <label className="text-sm" htmlFor="month">Month</label>
          <input id="month" type="month" className="rounded border border-ink px-2 py-1 text-sm" value={month} onChange={(e) => setMonth(e.target.value)} />
          <Button variant="secondary" onClick={() => downloadAuthed(`/v1/billing/usage.csv?month=${month}`, `usage-${month}.csv`).catch((e) => setCsvErr(e.message))}>Download CSV</Button>
        </span>}>
        {csvErr && <ErrorBox error={new Error(csvErr)} />}
        {usage.data && usage.data.lines.length ? (
          <table className="w-full text-sm"><caption className="sr-only">Usage by video and step</caption>
            <thead><tr className="text-left text-muted"><th className="py-1">Video</th><th>Step</th><th className="text-right">Credits</th></tr></thead>
            <tbody>{usage.data.lines.map((l, i) => <tr key={i} className="border-t border-line"><td className="py-1">{l.project_id ? <Link className="underline" to={`/projects/${l.project_id}`}>{l.project_id.slice(0, 6)}</Link> : "-"}</td><td>{l.stage ?? "-"}</td><td className="text-right tabular-nums">{Number(l.credits).toFixed(4)}</td></tr>)}
              <tr className="border-t border-ink font-semibold"><td className="py-1" colSpan={2}>Total for {usage.data.month}</td><td className="text-right tabular-nums">{Number(usage.data.total_credits).toFixed(4)}</td></tr></tbody></table>
        ) : <p className="text-muted">No usage in {month}.</p>}
      </Card>
      <Card title="History">
        <table className="w-full text-sm"><caption className="sr-only">Credit history</caption>
          <thead><tr className="text-left text-muted"><th className="py-1">When</th><th>What</th><th className="text-right">Credits</th><th className="text-right">Balance</th></tr></thead>
          <tbody>{ledger.data?.map((e) => <tr key={e.id} className="border-t border-line"><td className="py-1">{new Date(e.created_at).toLocaleString()}</td><td>{KIND[e.kind] ?? e.kind}{e.stage ? ` · ${e.stage}` : ""}</td><td className={`text-right tabular-nums ${Number(e.amount) < 0 ? "" : "text-ink"}`}>{Number(e.amount) > 0 ? "+" : ""}{Number(e.amount).toFixed(4)}</td><td className="text-right tabular-nums">{Number(e.balance_after).toFixed(2)}</td></tr>)}</tbody></table>
      </Card>
    </>
  );
}

// Local development only: stands in for the payment provider's hosted checkout page.
export function MockPay() {
  const { checkoutId = "" } = useParams();
  const nav = useNavigate();
  const pay = useMutation({
    mutationFn: () => unwrap(api.POST("/v1/billing/dev/pay/{checkout_id}", { params: { path: { checkout_id: checkoutId } } })),
    onSuccess: () => nav("/billing?paid=1"),
  });
  return (
    <div className="mx-auto max-w-md space-y-4 p-6">
      <Card title="Test payment">
        <Notice tone="warn">This is a test checkout for development. A real payment provider's page appears here in production.</Notice>
        <div className="mt-4 flex gap-2"><Button onClick={() => pay.mutate()} disabled={pay.isPending}>Pay now (test)</Button><Link className="px-3 py-2 text-sm underline" to="/billing">Cancel</Link></div>
        <ErrorBox error={pay.error} />
      </Card>
    </div>
  );
}
