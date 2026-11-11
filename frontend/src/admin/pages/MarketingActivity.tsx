import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api, unwrap } from "../api/client";
import { Button, Card, ErrorBox, inputCls } from "../components/ui";
import { ago, num } from "../lib/format";

type Row = { id: string; at: string; email: string; kind: "campaign" | "workflow" | "test"; source: string; subject: string; status: "sent" | "skipped" | "failed" | "dry_run" | "test"; reason: string; opened: boolean; clicked: boolean };
const PAGE = 50;
const STATUS: Record<Row["status"], string> = { sent: "Sent", skipped: "Not sent", failed: "Failed", dry_run: "Dry run", test: "Test" };
const TONE: Record<Row["status"], string> = { sent: "bg-lime-tint", skipped: "bg-peach-tint", failed: "bg-brand-red", dry_run: "bg-lilac", test: "bg-paper" };
const WHY: Record<string, string> = {
  opted_out: "They unsubscribed",
  suppressed: "Their address is blocked (bounced or complained)",
  too_soon: "They had another marketing email too recently",
  account_inactive: "Their account is closed or suspended",
  already_sent: "Already sent",
};

// Every marketing email we sent or chose not to send, so support can answer "why did I get this?" and "why didn't I?".
export function ActivityTab() {
  const [q, setQ] = useState("");
  const [term, setTerm] = useState("");
  const [status, setStatus] = useState("");
  const [kind, setKind] = useState("");
  const [page, setPage] = useState(0);
  const list = useQuery({
    queryKey: ["marketing-activity", term, status, kind, page],
    queryFn: () => unwrap(api.GET("/v1/admin/marketing/activity", { params: { query: { q: term, status, kind, limit: PAGE, offset: page * PAGE } } })) as unknown as Promise<{ total: number; items: Row[] }>,
  });
  const d = list.data;
  const pages = Math.max(1, Math.ceil((d?.total ?? 0) / PAGE));
  return (
    <>
      <form className="flex flex-wrap items-end gap-2" role="search" onSubmit={(e) => { e.preventDefault(); setPage(0); setTerm(q.trim()); }}>
        <label className="block min-w-60 flex-1 text-sm font-semibold">Find a person<input aria-label="Search by email" className={inputCls} placeholder="Part of an email address" value={q} onChange={(e) => setQ(e.target.value)} /></label>
        <label className="block text-sm font-semibold">Outcome<select className={inputCls} value={status} onChange={(e) => { setStatus(e.target.value); setPage(0); }}><option value="">All</option><option value="sent">Sent</option><option value="skipped">Not sent</option><option value="failed">Failed</option><option value="dry_run">Dry run</option><option value="test">Test</option></select></label>
        <label className="block text-sm font-semibold">From<select className={inputCls} value={kind} onChange={(e) => { setKind(e.target.value); setPage(0); }}><option value="">Everything</option><option value="campaign">Campaigns</option><option value="workflow">Workflows</option><option value="test">Tests</option></select></label>
        <Button type="submit">Search</Button>
      </form>
      <ErrorBox error={list.error} />
      <Card title="Marketing activity">
        {list.isLoading ? <p aria-busy="true">Loading…</p> : d && d.items.length === 0 ? <p className="text-sm text-muted">Nothing here yet{term || status || kind ? " for that search" : ""}.</p> : (
          <>
            <ul className="divide-y divide-line text-sm">
              {d?.items.map((r) => (
                <li key={r.id} className="flex flex-wrap items-start justify-between gap-x-4 gap-y-1 py-2.5">
                  <div className="min-w-0 space-y-0.5">
                    <p><span className="break-all font-semibold">{r.email}</span> <span className={`ml-1 rounded-sm px-1.5 py-0.5 text-xs font-bold ${TONE[r.status]}`}>{STATUS[r.status]}</span></p>
                    <p className="text-muted">{r.subject || "(no subject)"}{r.source && ` · ${r.source}`}</p>
                    {r.status === "skipped" && <p className="text-xs">{WHY[r.reason] ?? r.reason}</p>}
                    {r.status === "sent" && (r.opened || r.clicked) && <p className="text-xs text-muted">{r.clicked ? "Clicked the button" : "Opened"}</p>}
                  </div>
                  <span className="shrink-0 text-xs text-muted" title={new Date(r.at).toLocaleString()}>{ago(r.at)}</span>
                </li>
              ))}
            </ul>
            <div className="mt-3 flex items-center justify-between text-sm">
              <span className="text-muted">{num(d?.total ?? 0)} in all</span>
              <div className="flex items-center gap-2"><Button variant="secondary" disabled={page === 0} onClick={() => setPage(page - 1)}>Newer</Button><span>Page {page + 1} of {pages}</span><Button variant="secondary" disabled={page + 1 >= pages} onClick={() => setPage(page + 1)}>Older</Button></div>
            </div>
          </>
        )}
      </Card>
    </>
  );
}
