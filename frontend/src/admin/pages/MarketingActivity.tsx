import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api, unwrap } from "../api/client";
import { Button, Card, ErrorBox, inputCls } from "../components/ui";
import { EmptyState, PageIntro } from "../components/marketingUi";
import { ago, num } from "../lib/format";

type Row = { id: string; at: string; email: string; kind: "campaign" | "workflow" | "test"; source: string; subject: string; status: "sent" | "skipped" | "failed" | "dry_run" | "test"; reason: string; opened: boolean; clicked: boolean };
const PAGE = 50;
const STATUS: Record<Row["status"], string> = { sent: "Sent", skipped: "Not sent", failed: "Failed", dry_run: "Test mode", test: "Test" };
const TONE: Record<Row["status"], string> = { sent: "bg-lime-tint", skipped: "bg-peach-tint", failed: "bg-brand-red", dry_run: "bg-lilac", test: "bg-paper" };
const WHY: Record<string, string> = {
  opted_out: "They unsubscribed, so we don’t email them.",
  suppressed: "Their address is blocked (it bounced or they marked an email as spam).",
  too_soon: "They’d had another marketing email too recently. We space them out so nobody is flooded.",
  account_inactive: "Their account is closed or suspended.",
  already_sent: "This exact email had already been sent to them.",
  engine_off: "Marketing email was switched off at the time.",
};
const CHIPS: [string, string][] = [["", "Everything"], ["sent", "Sent"], ["skipped", "Not sent"], ["failed", "Failed"], ["dry_run", "Test mode"], ["test", "Tests to me"]];
const FROM: Record<Row["kind"], string> = { campaign: "campaign", workflow: "workflow", test: "a test" };

// Every marketing email we sent or chose not to send, so anyone can answer "did they get it?" and "why not?".
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
  const filtered = !!(term || status || kind);
  return (
    <div className="space-y-5">
      <PageIntro title="Activity">Every marketing email we sent, and every one we chose not to send, newest first. Use it to answer “did this person get our email?” and “why didn’t they?”.</PageIntro>
      <form className="flex flex-wrap items-end gap-2" role="search" onSubmit={(e) => { e.preventDefault(); setPage(0); setTerm(q.trim()); }}>
        <label className="block min-w-60 flex-1 text-sm font-semibold">Find a person<input aria-label="Search by email" className={inputCls} placeholder="Part of their email address" value={q} onChange={(e) => setQ(e.target.value)} /></label>
        <label className="block text-sm font-semibold">From<select className={inputCls} value={kind} onChange={(e) => { setKind(e.target.value); setPage(0); }}><option value="">Campaigns, workflows and tests</option><option value="campaign">Campaigns only</option><option value="workflow">Workflows only</option><option value="test">Tests only</option></select></label>
        <Button type="submit">Search</Button>
        {term && <Button type="button" variant="secondary" onClick={() => { setQ(""); setTerm(""); setPage(0); }}>Clear search</Button>}
      </form>
      <div role="group" aria-label="Filter by outcome" className="flex flex-wrap gap-2">
        {CHIPS.map(([k, label]) => <button key={k} type="button" aria-pressed={status === k} onClick={() => { setStatus(k); setPage(0); }} className={`rounded-full border px-3.5 py-1.5 text-sm font-semibold ${status === k ? "border-ink bg-brand-green" : "border-line bg-white hover:border-ink"}`}>{label}</button>)}
      </div>
      <ErrorBox error={list.error} />
      <Card>
        {list.isLoading ? <p aria-busy="true">Loading…</p> : d && d.items.length === 0 ? (
          <EmptyState title={filtered ? "Nothing matches that" : "No marketing email yet"}>{filtered ? "Try a different search, or clear the filters." : "Once a campaign or workflow sends (or is run in test mode), every email appears here."}</EmptyState>
        ) : (
          <>
            <ul className="divide-y divide-line text-sm">
              {d?.items.map((r) => (
                <li key={r.id} className="flex flex-wrap items-start justify-between gap-x-4 gap-y-1 py-3">
                  <div className="min-w-0 space-y-0.5">
                    <p><span className="break-all font-semibold">{r.email}</span> <span className={`ml-1 rounded-sm px-1.5 py-0.5 text-xs font-bold ${TONE[r.status]}`}>{STATUS[r.status]}</span></p>
                    <p className="text-muted">“{r.subject || "(no subject)"}”{r.source ? ` · from ${FROM[r.kind]} “${r.source}”` : ` · ${FROM[r.kind]}`}</p>
                    {r.status === "skipped" && <p className="text-xs">{WHY[r.reason] ?? r.reason}</p>}
                    {r.status === "failed" && <p className="text-xs">The mail service couldn’t send it.</p>}
                    {r.status === "sent" && (r.opened || r.clicked) && <p className="text-xs text-muted">{r.clicked ? "They clicked the button." : "They opened it."}</p>}
                  </div>
                  <span className="shrink-0 text-xs text-muted" title={new Date(r.at).toLocaleString()}>{ago(r.at)}</span>
                </li>
              ))}
            </ul>
            <div className="mt-3 flex flex-wrap items-center justify-between gap-2 text-sm">
              <span className="text-muted">{num(d?.total ?? 0)} in all</span>
              <div className="flex items-center gap-2"><Button variant="secondary" disabled={page === 0} onClick={() => setPage(page - 1)}>Newer</Button><span>Page {page + 1} of {pages}</span><Button variant="secondary" disabled={page + 1 >= pages} onClick={() => setPage(page + 1)}>Older</Button></div>
            </div>
          </>
        )}
      </Card>
    </div>
  );
}
