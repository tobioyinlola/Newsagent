import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, unwrap } from "../api/client";
import { Button, Card, ConfirmDialog, ErrorBox, inputCls } from "../components/ui";
import { EmptyState, PageIntro, useToast } from "../components/marketingUi";
import { ago, num } from "../lib/format";
import { useCan } from "../lib/can";

type Row = { email: string; reason: string; at: string };
const PAGE = 50;
const REASON: Record<string, string> = { "hard bounce": "The address bounced for good", "spam complaint": "They marked our email as spam", link: "They used the unsubscribe link", one_click: "They used their mail app’s unsubscribe", account: "They switched it off in their settings", complaint: "They marked our email as spam", operator: "Removed by us" };

// Everyone we won't email: addresses that bounced or complained (blocked), and people who chose to stop (unsubscribed).
export function OptoutsTab() {
  const qc = useQueryClient();
  const toast = useToast();
  const manage = useCan()("marketing.manage");
  const [kind, setKind] = useState<"blocked" | "unsubscribed">("unsubscribed");
  const [q, setQ] = useState("");
  const [term, setTerm] = useState("");
  const [page, setPage] = useState(0);
  const [lifting, setLifting] = useState<string | null>(null);
  const list = useQuery({
    queryKey: ["marketing-optouts", kind, term, page],
    queryFn: () => unwrap(api.GET("/v1/admin/marketing/optouts", { params: { query: { kind, q: term, limit: PAGE, offset: page * PAGE } } })) as unknown as Promise<{ total: number; items: Row[] }>,
  });
  const lift = useMutation({
    mutationFn: (email: string) => unwrap(api.DELETE("/v1/admin/marketing/optouts/blocked/{email}", { params: { path: { email } } })),
    onSuccess: async () => { setLifting(null); await qc.invalidateQueries({ queryKey: ["marketing-optouts"] }); await qc.invalidateQueries({ queryKey: ["marketing-status"] }); toast("Block lifted."); },
  });
  const d = list.data;
  const pages = Math.max(1, Math.ceil((d?.total ?? 0) / PAGE));
  return (
    <div className="space-y-5">
      <PageIntro title="Unsubscribed and blocked">The people we never send marketing email to, and why. This keeps you on the right side of people’s wishes and protects your sender reputation. Account emails like sign-in codes and receipts are never affected.</PageIntro>
      <div role="group" aria-label="Which list" className="flex flex-wrap gap-2">
        {([["unsubscribed", "Unsubscribed", "People who chose to stop"], ["blocked", "Blocked addresses", "Bounced or reported as spam"]] as const).map(([k, label, hint]) => (
          <button key={k} type="button" aria-pressed={kind === k} onClick={() => { setKind(k); setPage(0); }} className={`rounded-xl border px-4 py-2 text-left text-sm ${kind === k ? "border-ink bg-brand-green" : "border-line bg-white hover:border-ink"}`}><b className="block">{label}</b><span className="text-xs">{hint}</span></button>
        ))}
      </div>
      <form className="flex flex-wrap items-end gap-2" role="search" onSubmit={(e) => { e.preventDefault(); setPage(0); setTerm(q.trim()); }}>
        <label className="block min-w-60 flex-1 text-sm font-semibold">Find an address<input aria-label="Search addresses" className={inputCls} placeholder="Part of an email address" value={q} onChange={(e) => setQ(e.target.value)} /></label>
        <Button type="submit">Search</Button>
        {term && <Button type="button" variant="secondary" onClick={() => { setQ(""); setTerm(""); setPage(0); }}>Clear</Button>}
      </form>
      <ErrorBox error={list.error ?? lift.error} />
      <Card>
        <p className="mb-3 text-sm text-muted">{kind === "blocked" ? "We never send marketing email to these. The address bounced for good, or the person marked one of our emails as spam. If a block is a mistake (say, a full mailbox that’s now fixed), you can lift it." : "These people chose to stop. Only they can turn it back on, from the link at the bottom of an email or from their own settings. We can’t re-subscribe anyone on their behalf."}</p>
        {list.isLoading ? <p aria-busy="true">Loading…</p> : d && d.items.length === 0 ? <EmptyState title={term ? "Nobody matches that" : kind === "blocked" ? "No blocked addresses" : "Nobody has unsubscribed"}>{term ? "Try a different search." : "That’s a good sign. They’ll appear here if it happens."}</EmptyState> : (
          <>
            <ul className="divide-y divide-line text-sm">
              {d?.items.map((r) => (
                <li key={r.email} className="flex flex-wrap items-center justify-between gap-2 py-2.5">
                  <div className="min-w-0"><p className="break-all font-semibold">{r.email}</p><p className="text-xs text-muted">{REASON[r.reason] ?? r.reason} · {ago(r.at)}</p></div>
                  {kind === "blocked" && manage && <Button variant="secondary" onClick={() => setLifting(r.email)}>Lift the block</Button>}
                </li>
              ))}
            </ul>
            <div className="mt-3 flex flex-wrap items-center justify-between gap-2 text-sm"><span className="text-muted">{num(d?.total ?? 0)} in all</span><div className="flex items-center gap-2"><Button variant="secondary" disabled={page === 0} onClick={() => setPage(page - 1)}>Newer</Button><span>Page {page + 1} of {pages}</span><Button variant="secondary" disabled={page + 1 >= pages} onClick={() => setPage(page + 1)}>Older</Button></div></div>
          </>
        )}
      </Card>
      {lifting && <ConfirmDialog title="Lift this block?" confirmLabel="Lift the block" onConfirm={() => lift.mutate(lifting)} onCancel={() => setLifting(null)}>We’ll be able to send marketing email to <b>{lifting}</b> again. Only do this if you know the address works now. If it bounces again, it will be blocked again.</ConfirmDialog>}
    </div>
  );
}
