import { keepPreviousData, useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, unwrap } from "../api/client";
import { Pager } from "../../components/Pager";
import { usePaged } from "../../lib/usePaged";
import { Stat } from "../components/Charts";
import { WordingFix } from "../components/WordingFix";
import { type CustomerProfile, profileRows, STATUS } from "../lib/profileLabels";
import { useCan } from "../lib/can";
import { Button, Card, ErrorBox, inputCls } from "../components/ui";
import { ago, date, num, usd } from "../lib/format";
import { downloadAuthed } from "../lib/download";

export function Customers() {
  const [q, setQ] = useState("");
  const [term, setTerm] = useState("");
  const paged = usePaged(["customers", term], (limit, offset) => unwrap(api.GET("/v1/admin/customers", { params: { query: { q: term, limit, offset } } })));
  const list = { data: { items: paged.items, total: paged.total }, isLoading: paged.query.isLoading, error: paged.query.error };
  return (
    <>
      <h1 className="text-2xl font-bold">Customers</h1>
      <form className="flex gap-2" role="search" onSubmit={(e) => { e.preventDefault(); setTerm(q.trim()); }}>
        <input data-tour="customers-search" aria-label="Search customers" placeholder="Search by company or email" className={inputCls} value={q} onChange={(e) => setQ(e.target.value)} />
        <Button type="submit">Search</Button>
      </form>
      <ErrorBox error={list.error} />
      <Card>
        {list.isLoading ? <p aria-busy="true">Loading…</p> : list.data && list.data.items.length === 0 ? <p className="text-sm text-muted">{term ? "No customers match that search." : "No customers yet."}</p> : (
          <>
          <ul aria-label="Customers" className="divide-y divide-line sm:hidden">{list.data?.items.map((c) => (
            <li key={c.workspace_id} className="py-3">
              <div className="flex items-start justify-between gap-3"><Link className="min-w-0 break-words font-bold underline" to={`/customers/${c.workspace_id}`}>{c.company}</Link><span className={`shrink-0 rounded-sm px-1.5 py-0.5 text-xs font-bold ${c.status === "suspended" ? "bg-brand-red" : "bg-lime-tint"}`}>{c.status}</span></div>
              <p className="mt-0.5 break-all text-sm text-muted">{c.owner_email}</p>
              <dl className="mt-2 grid grid-cols-3 gap-2 text-sm"><div><dt className="text-xs text-muted">Paid</dt><dd className="tabular-nums">{usd(c.paid_usd)}</dd></div><div><dt className="text-xs text-muted">Credits</dt><dd className="tabular-nums">{num(c.credits)}</dd></div><div><dt className="text-xs text-muted">Videos</dt><dd className="tabular-nums">{c.videos}</dd></div></dl>
              <p className="mt-2 text-xs text-muted">Signed up {date(c.signed_up_at)} · last seen {ago(c.last_login_at)}</p>
            </li>))}</ul>
          <div className="hidden overflow-x-auto sm:block">
            <table className="w-full text-sm"><caption className="sr-only">Customers, newest sign-up first</caption>
              <thead><tr className="text-left text-muted"><th className="py-1">Company</th><th>Owner</th><th>Signed up</th><th>Last seen</th><th>Status</th><th className="text-right">Paid</th><th className="text-right">Credits</th><th className="text-right">Videos</th></tr></thead>
              <tbody>{list.data?.items.map((c) => (
                <tr key={c.workspace_id} className="border-t border-line">
                  <td className="py-1.5 font-bold"><Link className="underline" to={`/customers/${c.workspace_id}`}>{c.company}</Link></td>
                  <td>{c.owner_email}</td><td>{date(c.signed_up_at)}</td><td>{ago(c.last_login_at)}</td>
                  <td><span className={`rounded-sm px-1.5 py-0.5 text-xs font-bold ${c.status === "suspended" ? "bg-brand-red" : "bg-lime-tint"}`}>{c.status}</span></td>
                  <td className="text-right tabular-nums">{usd(c.paid_usd)}</td><td className="text-right tabular-nums">{num(c.credits)}</td><td className="text-right tabular-nums">{c.videos}</td>
                </tr>))}</tbody>
            </table>
          </div>
          </>
        )}
        <Pager total={paged.total} page={paged.page} size={paged.size} onPage={paged.setPage} onSize={paged.setSize} noun="customers" busy={paged.query.isFetching} />
      </Card>
    </>
  );
}

export function CustomerDetail() {
  const { id = "" } = useParams();
  const SIZE = 10; // rows per list: videos and payments page separately
  const [vPage, setVPage] = useState(0); const [pPage, setPPage] = useState(0);
  const q = useQuery({ queryKey: ["customer", id, vPage, pPage], queryFn: () => unwrap(api.GET("/v1/admin/customers/{workspace_id}", { params: { path: { workspace_id: id }, query: { limit: SIZE, offset: vPage * SIZE, payments_offset: pPage * SIZE } } })), placeholderData: keepPreviousData });
  const qc = useQueryClient();
  const can = useCan();
  const refresh = () => qc.invalidateQueries({ queryKey: ["customer", id] });
  const path = (project_id: string) => ({ params: { path: { project_id } } });
  const del = useMutation({ mutationFn: (pid: string) => unwrap(api.DELETE("/v1/admin/projects/{project_id}", path(pid))), onSuccess: refresh });
  const takeDown = useMutation({ mutationFn: (pid: string) => unwrap(api.DELETE("/v1/admin/projects/{project_id}/publication", path(pid))), onSuccess: refresh });
  const putBack = useMutation({ mutationFn: (pid: string) => unwrap(api.POST("/v1/admin/projects/{project_id}/publication", path(pid))), onSuccess: refresh });
  const remake = useMutation({ mutationFn: (pid: string) => unwrap(api.POST("/v1/admin/projects/{project_id}/presenter", { ...path(pid), body: {} })), onSuccess: refresh });
  if (q.isLoading) return <p aria-busy="true">Loading…</p>;
  if (q.error || !q.data) return <><Link className="underline" to="/customers">← Customers</Link><ErrorBox error={q.error ?? new Error("Not found")} /></>;
  const c = q.data;
  const projectsTotal = Math.max(c.projects_total ?? 0, c.projects.length); const paymentsTotal = Math.max(c.payments_total ?? 0, c.payments.length); // never fewer than the rows on screen (and older replies carry no totals)
  const paid = c.paid_usd !== undefined ? Number(c.paid_usd) : c.payments.reduce((n, p) => n + Number(p.usd ?? 0), 0);
  return (
    <>
      <Link className="text-sm font-bold underline" to="/customers">← Customers</Link>
      <div className="flex flex-wrap items-center gap-3">
        <h1 className="text-2xl font-bold">{c.company}</h1>
        <span className={`rounded-sm px-2 py-0.5 text-xs font-bold ${c.status === "suspended" ? "bg-brand-red" : "bg-lime-tint"}`}>{c.status}</span>
        <Link className="ml-auto text-sm font-bold underline" to="/setup">Manage limits, credits and suspension</Link>
      </div>
      <dl className="grid grid-cols-2 gap-3 md:grid-cols-4">
        <Stat label="Signed up" value={date(c.signed_up_at)} sub={`plan: ${c.plan}`} />
        <Stat label="Paid" value={usd(paid)} sub={`${paymentsTotal} payment${paymentsTotal === 1 ? "" : "s"}`} />
        <Stat label="Credits left" value={num(c.credits)} sub={`${num(c.spent_credits)} spent in total`} />
        <Stat label="Spend cap" value={Number(c.spend_cap) ? num(c.spend_cap) : "none"} />
      </dl>
      <Card title="What they told us">
        {(() => {
          const rows = profileRows((c.profile ?? {}) as CustomerProfile);
          const where = [c.city, c.country].filter(Boolean).join(", ");
          return <>
            <p className="mb-3 text-sm text-muted">{STATUS[c.profile_status ?? "not_started"] ?? c.profile_status}. From sign-up and the first-run questions.</p>
            <dl className="grid gap-x-6 gap-y-2 text-sm sm:grid-cols-2">
              {where && <div><dt className="text-muted">Based in</dt><dd className="font-semibold">{where}</dd></div>}
              {c.industry && <div><dt className="text-muted">Industry</dt><dd className="font-semibold capitalize">{c.industry.replace(/_/g, " ")}</dd></div>}
              {rows.map(([k, v]) => <div key={k}><dt className="text-muted">{k}</dt><dd className="font-semibold break-words">{v}</dd></div>)}
            </dl>
            {rows.length === 0 && <p className="mt-2 text-sm text-muted">They have not answered any of the questions.</p>}
          </>;
        })()}
      </Card>
      <Card title="People">
        <table className="w-full text-sm"><caption className="sr-only">People</caption>
          <thead><tr className="text-left text-muted"><th className="py-1">Email</th><th>Role</th><th>Joined</th><th>Last seen</th></tr></thead>
          <tbody>{c.users.map((u) => <tr key={u.email} className="border-t border-line"><td className="py-1.5">{u.email}</td><td>{u.role}</td><td>{date(u.created_at)}</td><td>{ago(u.last_login_at)}</td></tr>)}</tbody>
        </table>
      </Card>
      <Card title="Videos">
        {projectsTotal === 0 ? <p className="text-sm text-muted">No videos yet.</p> : (
          <table className="w-full text-sm"><caption className="sr-only">Videos</caption>
            <thead><tr className="text-left text-muted"><th className="py-1">Video</th><th>Stage</th><th>Interview</th><th>Started</th><th>Finished</th><th className="text-right">Vendor cost</th>{can("content.manage") && <th className="text-right">Actions</th>}</tr></thead>
            <tbody>{c.projects.map((p) => <tr key={p.id} className="border-t border-line"><td className="py-1.5 font-mono">{p.id.slice(0, 6)}</td><td className="capitalize">{p.state.replace(/_/g, " ")}</td><td>{p.interview === "none" ? "—" : p.interview === "live" ? "AI interview" : "link"}</td><td>{ago(p.created_at)}</td><td>{p.completed_at ? date(p.completed_at) : "—"}</td><td className="text-right tabular-nums">{usd(p.cost_usd)}</td>{can("content.manage") && (
              <td className="space-x-2 whitespace-nowrap text-right">
                {p.state === "final_ready" && (p.published
                  ? <Button variant="secondary" disabled={takeDown.isPending} onClick={() => { if (confirm("Take this story off Latest Stories? The video stays.")) takeDown.mutate(p.id); }}>Take story down</Button>
                  : <Button variant="secondary" disabled={putBack.isPending} onClick={() => putBack.mutate(p.id)}>Publish story</Button>)}
                {p.state === "final_ready" && <WordingFix projectId={p.id} onDone={refresh} />}
                {p.state === "final_ready" && can("content.manage") && <Button variant="secondary" disabled={remake.isPending} onClick={() => { if (confirm("Make this video again with the default presenter? The presenter's clips are made again (a vendor cost, not the customer's credits), the founder's answers are never changed, and the current video stays until the new one is ready.")) remake.mutate(p.id); }}>Remake with the default presenter</Button>}
                <Button variant="danger" disabled={del.isPending} onClick={() => { if (confirm("Delete this video and all its files? This can't be undone.")) del.mutate(p.id); }}>Delete video</Button>
              </td>)}</tr>)}</tbody>
          </table>
        )}
        <ErrorBox error={del.error ?? takeDown.error ?? putBack.error ?? remake.error} />
        <Pager total={projectsTotal} page={vPage} size={SIZE} onPage={setVPage} noun="videos" busy={q.isFetching} />
      </Card>
      <WalletHistory id={id} balance={c.credits} />
      <Card title="Payments">
        {paymentsTotal === 0 ? <p className="text-sm text-muted">No payments yet.</p> : (
          <table className="w-full text-sm"><caption className="sr-only">Payments</caption>
            <thead><tr className="text-left text-muted"><th className="py-1">When</th><th>Type</th><th className="text-right">Amount</th><th className="text-right">Credits</th></tr></thead>
            <tbody>{c.payments.map((p, i) => <tr key={i} className="border-t border-line"><td className="py-1.5">{date(p.when)}</td><td>{p.kind === "bank_transfer" ? "Bank transfer" : p.kind === "card" ? "Card" : "Offline"}</td><td className="text-right tabular-nums">{p.usd == null ? "not recorded" : usd(p.usd)}</td><td className="text-right tabular-nums">{num(p.credits)}</td></tr>)}</tbody>
          </table>
        )}
        <Pager total={paymentsTotal} page={pPage} size={SIZE} onPage={setPPage} noun="payments" busy={q.isFetching} />
      </Card>
    </>
  );
}

const GROUPS: [Group, string][] = [["all", "Everything"], ["payments", "Payments and credits added"], ["usage", "Usage"]];
type Group = "all" | "payments" | "usage";
const stamp = (v: string) => new Date(v).toLocaleString(undefined, { day: "numeric", month: "short", year: "numeric", hour: "2-digit", minute: "2-digit" });

// Everything that ever moved this customer's wallet: credits bought, free credits, refunds, and credits used for videos and distribution.
function WalletHistory({ id, balance }: { id: string; balance: string }) {
  const [group, setGroup] = useState<Group>("all");
  const [err, setErr] = useState<string | null>(null);
  const paged = usePaged(["ledger", id, group], (limit, offset) => unwrap(api.GET("/v1/admin/customers/{workspace_id}/ledger", { params: { path: { workspace_id: id }, query: { group, limit, offset } } })));
  const q = paged.query;
  const d = q.data;
  useEffect(() => { // arriving from the Wallets list (#wallet): the page loads before this part exists
    if (d && window.location.hash === "#wallet") document.getElementById("wallet")?.scrollIntoView({ block: "center" });
  }, [d]);
  const csv = () => downloadAuthed(`/v1/admin/customers/${id}/ledger.csv?group=${group}`, `wallet-${group}.csv`).catch((e) => setErr(e.message));
  return (
    <Card title="Wallet history" actions={<Button variant="secondary" onClick={() => void csv()}>Download CSV</Button>}>
      <div id="wallet" className="mb-3 flex flex-wrap items-center gap-2" role="group" aria-label="Show">
        <span className="mr-2 text-sm">Balance now: <strong className="tabular-nums">{num(balance)} credits</strong></span>
        {GROUPS.map(([k, label]) => <button key={k} type="button" aria-pressed={group === k} onClick={() => setGroup(k)} className={`min-h-9 rounded-full border px-3 text-sm font-semibold ${group === k ? "border-ink bg-ink text-white" : "border-line"}`}>{label}</button>)}
      </div>
      <ErrorBox error={q.error ?? (err ? new Error(err) : null)} />
      {q.isLoading ? <p aria-busy="true">Loading…</p> : d && d.items.length === 0 ? <p className="text-sm text-muted">Nothing here yet.</p> : (
        <>
        <ol className="space-y-2 sm:hidden" aria-label="Wallet history, newest first">
          {d?.items.map((t) => (
            <li key={t.id} className="rounded-lg border border-line p-3 text-sm">
              <div className="flex items-baseline justify-between gap-2"><span className="font-semibold">{t.label}</span><span className={`font-semibold tabular-nums ${Number(t.amount) < 0 ? "text-red-700" : "text-green-800"}`}>{Number(t.amount) > 0 ? "+" : ""}{num(t.amount)}</span></div>
              {(t.description || t.stage) && <p className="text-xs text-muted">{t.description ?? ""}{t.stage ? ` (${t.stage})` : ""}{t.project_id ? ` · ${t.project_id.slice(0, 6)}` : ""}</p>}
              <p className="mt-1 flex justify-between gap-2 text-xs text-muted"><span>{stamp(t.when)}</span><span>Balance after: <span className="tabular-nums">{num(t.balance_after)}</span></span></p>
            </li>
          ))}
        </ol>
        <div className="hidden overflow-x-auto sm:block">
          <table className="w-full text-sm"><caption className="sr-only">Wallet history, newest first</caption>
            <thead><tr className="text-left text-muted"><th className="py-1">When</th><th>What</th><th>Details</th><th className="text-right">Credits</th><th className="text-right">Balance after</th></tr></thead>
            <tbody>{d?.items.map((t) => (
              <tr key={t.id} className="border-t border-line">
                <td className="whitespace-nowrap py-1.5">{stamp(t.when)}</td>
                <td>{t.label}</td>
                <td className="text-muted">{t.description ?? ""}{t.stage ? ` (${t.stage})` : ""}{t.project_id ? <> · <span className="font-mono">{t.project_id.slice(0, 6)}</span></> : null}</td>
                <td className={`text-right font-semibold tabular-nums ${Number(t.amount) < 0 ? "text-red-700" : "text-green-800"}`}>{Number(t.amount) > 0 ? "+" : ""}{num(t.amount)}</td>
                <td className="text-right tabular-nums">{num(t.balance_after)}</td>
              </tr>))}</tbody>
          </table>
        </div>
        </>
      )}
      <Pager total={paged.total} page={paged.page} size={paged.size} onPage={paged.setPage} onSize={paged.setSize} noun="entries" busy={q.isFetching} />
    </Card>
  );
}
