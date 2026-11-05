import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { api, unwrap } from "../api/client";
import { Stat } from "../components/Charts";
import { Button, Card, ErrorBox, inputCls } from "../components/ui";
import { ago, num } from "../lib/format";
import { downloadAuthed } from "../lib/download";

const PAGE = 50;
type Sort = "balance_low" | "balance_high" | "used_high" | "recent" | "company";
const SORTS: [Sort, string][] = [["balance_high", "Most credits left"], ["balance_low", "Fewest credits left"], ["used_high", "Most used"], ["recent", "Most recent activity"], ["company", "Company name"]];

// Every customer's wallet: what is left, what they bought, what they were given, and what they have used. Click one for its full history.
export function Wallets() {
  const [q, setQ] = useState("");
  const [term, setTerm] = useState("");
  const [sort, setSort] = useState<Sort>("balance_high");
  const [page, setPage] = useState(0);
  const [err, setErr] = useState<string | null>(null);
  const list = useQuery({ queryKey: ["wallets", term, sort, page], queryFn: () => unwrap(api.GET("/v1/admin/wallets", { params: { query: { q: term, sort, limit: PAGE, offset: page * PAGE } } })) });
  const d = list.data;
  const pages = Math.max(1, Math.ceil((d?.total ?? 0) / PAGE));
  const csv = () => downloadAuthed(`/v1/admin/wallets.csv?${new URLSearchParams({ q: term, sort })}`, "wallets.csv").catch((e) => setErr(e.message));
  return (
    <>
      <h1 className="text-2xl font-bold">Wallets</h1>
      <dl className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat label="Wallets" value={d ? num(d.totals.wallets) : "…"} sub={d ? `${num(d.totals.empty)} with no credit left` : undefined} />
        <Stat label="Credits left (all wallets)" value={d ? num(d.totals.balance) : "…"} />
        <Stat label="Credits bought" value={d ? num(d.totals.bought) : "…"} />
        <Stat label="Credits used" value={d ? num(d.totals.used) : "…"} />
      </dl>
      <form className="flex flex-wrap items-end gap-2" role="search" onSubmit={(e) => { e.preventDefault(); setPage(0); setTerm(q.trim()); }}>
        <label className="block min-w-60 flex-1 text-sm font-semibold">Search<input aria-label="Search wallets" placeholder="Company or email" className={inputCls} value={q} onChange={(e) => setQ(e.target.value)} /></label>
        <label className="block text-sm font-semibold">Order by<select className={inputCls} value={sort} onChange={(e) => { setSort(e.target.value as Sort); setPage(0); }}>{SORTS.map(([k, label]) => <option key={k} value={k}>{label}</option>)}</select></label>
        <Button type="submit">Search</Button>
        <Button type="button" variant="secondary" onClick={() => void csv()}>Download CSV</Button>
      </form>
      <ErrorBox error={list.error ?? (err ? new Error(err) : null)} />
      <Card>
        {list.isLoading ? <p aria-busy="true">Loading…</p> : d && d.items.length === 0 ? <p className="text-sm text-muted">{term ? "No wallets match that search." : "No wallets yet."}</p> : (
          <>
          <ul className="space-y-3 sm:hidden" aria-label="Customer wallets">
            {d?.items.map((w) => (
              <li key={w.workspace_id} className="rounded-lg border border-line p-3 text-sm">
                <div className="flex items-start justify-between gap-2"><Link className="font-bold underline" to={`/customers/${w.workspace_id}#wallet`}>{w.company}</Link><span className={`shrink-0 rounded-sm px-1.5 py-0.5 text-xs font-bold ${w.status === "suspended" ? "bg-brand-red" : "bg-lime-tint"}`}>{w.status}</span></div>
                <p className="break-all text-xs text-muted">{w.owner_email}</p>
                <dl className="mt-2 grid grid-cols-2 gap-x-4 gap-y-1">
                  <div><dt className="text-xs text-muted">Credits left</dt><dd className={`font-semibold tabular-nums ${Number(w.balance) <= 0 ? "text-red-700" : ""}`}>{num(w.balance)}</dd></div>
                  <div><dt className="text-xs text-muted">Used</dt><dd className="tabular-nums">{num(w.used)}</dd></div>
                  <div><dt className="text-xs text-muted">Bought</dt><dd className="tabular-nums">{num(w.bought)}</dd></div>
                  <div><dt className="text-xs text-muted">Given free</dt><dd className="tabular-nums">{num(w.free)}</dd></div>
                </dl>
                <p className="mt-2 text-xs text-muted">Last activity: {ago(w.last_activity_at)}</p>
              </li>
            ))}
          </ul>
          <div className="hidden overflow-x-auto sm:block">
            <table className="w-full text-sm"><caption className="sr-only">Customer wallets</caption>
              <thead><tr className="text-left text-muted"><th className="py-1">Company</th><th>Owner</th><th>Status</th><th className="text-right">Credits left</th><th className="text-right">Bought</th><th className="text-right">Given free</th><th className="text-right">Used</th><th>Last activity</th></tr></thead>
              <tbody>{d?.items.map((w) => (
                <tr key={w.workspace_id} className="border-t border-line">
                  <td className="py-1.5 font-bold"><Link className="underline" to={`/customers/${w.workspace_id}#wallet`}>{w.company}</Link></td>
                  <td>{w.owner_email}</td>
                  <td><span className={`rounded-sm px-1.5 py-0.5 text-xs font-bold ${w.status === "suspended" ? "bg-brand-red" : "bg-lime-tint"}`}>{w.status}</span></td>
                  <td className={`text-right font-semibold tabular-nums ${Number(w.balance) <= 0 ? "text-red-700" : ""}`}>{num(w.balance)}</td>
                  <td className="text-right tabular-nums">{num(w.bought)}</td><td className="text-right tabular-nums">{num(w.free)}</td><td className="text-right tabular-nums">{num(w.used)}</td>
                  <td>{ago(w.last_activity_at)}</td>
                </tr>))}</tbody>
            </table>
          </div>
          </>
        )}
        {d && d.total > PAGE && (
          <div className="mt-3 flex items-center justify-between text-sm">
            <span className="text-muted">{d.total} wallets · page {page + 1} of {pages}</span>
            <span className="flex gap-2"><Button variant="secondary" disabled={page === 0} onClick={() => setPage(page - 1)}>Previous</Button><Button variant="secondary" disabled={page + 1 >= pages} onClick={() => setPage(page + 1)}>Next</Button></span>
          </div>
        )}
      </Card>
    </>
  );
}
