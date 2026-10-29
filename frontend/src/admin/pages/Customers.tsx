import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link, useParams } from "react-router-dom";
import { api, unwrap } from "../api/client";
import { Stat } from "../components/Charts";
import { useCan } from "../lib/can";
import { Button, Card, ErrorBox, inputCls } from "../components/ui";
import { ago, date, num, usd } from "../lib/format";

const PAGE = 25;

export function Customers() {
  const [q, setQ] = useState("");
  const [term, setTerm] = useState("");
  const [page, setPage] = useState(0);
  const list = useQuery({
    queryKey: ["customers", term, page],
    queryFn: () => unwrap(api.GET("/v1/admin/customers", { params: { query: { q: term, limit: PAGE, offset: page * PAGE } } })),
  });
  const pages = Math.max(1, Math.ceil((list.data?.total ?? 0) / PAGE));
  return (
    <>
      <h1 className="text-2xl font-bold">Customers</h1>
      <form className="flex gap-2" role="search" onSubmit={(e) => { e.preventDefault(); setPage(0); setTerm(q.trim()); }}>
        <input aria-label="Search customers" placeholder="Search by company or email" className={inputCls} value={q} onChange={(e) => setQ(e.target.value)} />
        <Button type="submit">Search</Button>
      </form>
      <ErrorBox error={list.error} />
      <Card>
        {list.isLoading ? <p aria-busy="true">Loading…</p> : list.data && list.data.items.length === 0 ? <p className="text-sm text-muted">{term ? "No customers match that search." : "No customers yet."}</p> : (
          <div className="overflow-x-auto">
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
        )}
        {list.data && list.data.total > PAGE && (
          <div className="mt-3 flex items-center justify-between text-sm">
            <span className="text-muted">{list.data.total} customers · page {page + 1} of {pages}</span>
            <span className="flex gap-2"><Button variant="secondary" disabled={page === 0} onClick={() => setPage(page - 1)}>Previous</Button><Button variant="secondary" disabled={page + 1 >= pages} onClick={() => setPage(page + 1)}>Next</Button></span>
          </div>
        )}
      </Card>
    </>
  );
}

export function CustomerDetail() {
  const { id = "" } = useParams();
  const q = useQuery({ queryKey: ["customer", id], queryFn: () => unwrap(api.GET("/v1/admin/customers/{workspace_id}", { params: { path: { workspace_id: id } } })) });
  const qc = useQueryClient();
  const can = useCan();
  const refresh = () => qc.invalidateQueries({ queryKey: ["customer", id] });
  const path = (project_id: string) => ({ params: { path: { project_id } } });
  const del = useMutation({ mutationFn: (pid: string) => unwrap(api.DELETE("/v1/admin/projects/{project_id}", path(pid))), onSuccess: refresh });
  const takeDown = useMutation({ mutationFn: (pid: string) => unwrap(api.DELETE("/v1/admin/projects/{project_id}/publication", path(pid))), onSuccess: refresh });
  const putBack = useMutation({ mutationFn: (pid: string) => unwrap(api.POST("/v1/admin/projects/{project_id}/publication", path(pid))), onSuccess: refresh });
  if (q.isLoading) return <p aria-busy="true">Loading…</p>;
  if (q.error || !q.data) return <><Link className="underline" to="/customers">← Customers</Link><ErrorBox error={q.error ?? new Error("Not found")} /></>;
  const c = q.data;
  const paid = c.payments.reduce((n, p) => n + Number(p.usd ?? 0), 0);
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
        <Stat label="Paid" value={usd(paid)} sub={`${c.payments.length} payment${c.payments.length === 1 ? "" : "s"}`} />
        <Stat label="Credits left" value={num(c.credits)} sub={`${num(c.spent_credits)} spent in total`} />
        <Stat label="Spend cap" value={Number(c.spend_cap) ? num(c.spend_cap) : "none"} />
      </dl>
      <Card title="People">
        <table className="w-full text-sm"><caption className="sr-only">People</caption>
          <thead><tr className="text-left text-muted"><th className="py-1">Email</th><th>Role</th><th>Joined</th><th>Last seen</th></tr></thead>
          <tbody>{c.users.map((u) => <tr key={u.email} className="border-t border-line"><td className="py-1.5">{u.email}</td><td>{u.role}</td><td>{date(u.created_at)}</td><td>{ago(u.last_login_at)}</td></tr>)}</tbody>
        </table>
      </Card>
      <Card title="Videos">
        {c.projects.length === 0 ? <p className="text-sm text-muted">No videos yet.</p> : (
          <table className="w-full text-sm"><caption className="sr-only">Videos</caption>
            <thead><tr className="text-left text-muted"><th className="py-1">Video</th><th>Stage</th><th>Interview</th><th>Started</th><th>Finished</th><th className="text-right">Vendor cost</th>{can("content.manage") && <th className="text-right">Actions</th>}</tr></thead>
            <tbody>{c.projects.map((p) => <tr key={p.id} className="border-t border-line"><td className="py-1.5 font-mono">{p.id.slice(0, 6)}</td><td className="capitalize">{p.state.replace(/_/g, " ")}</td><td>{p.interview === "none" ? "—" : p.interview === "live" ? "AI interview" : "link"}</td><td>{ago(p.created_at)}</td><td>{p.completed_at ? date(p.completed_at) : "—"}</td><td className="text-right tabular-nums">{usd(p.cost_usd)}</td>{can("content.manage") && (
              <td className="space-x-2 whitespace-nowrap text-right">
                {p.state === "final_ready" && (p.published
                  ? <Button variant="secondary" disabled={takeDown.isPending} onClick={() => { if (confirm("Take this story off Latest Stories? The video stays.")) takeDown.mutate(p.id); }}>Take story down</Button>
                  : <Button variant="secondary" disabled={putBack.isPending} onClick={() => putBack.mutate(p.id)}>Publish story</Button>)}
                <Button variant="danger" disabled={del.isPending} onClick={() => { if (confirm("Delete this video and all its files? This can't be undone.")) del.mutate(p.id); }}>Delete video</Button>
              </td>)}</tr>)}</tbody>
          </table>
        )}
        <ErrorBox error={del.error ?? takeDown.error ?? putBack.error} />
      </Card>
      <Card title="Payments">
        {c.payments.length === 0 ? <p className="text-sm text-muted">No payments yet.</p> : (
          <table className="w-full text-sm"><caption className="sr-only">Payments</caption>
            <thead><tr className="text-left text-muted"><th className="py-1">When</th><th>Type</th><th className="text-right">Amount</th><th className="text-right">Credits</th></tr></thead>
            <tbody>{c.payments.map((p, i) => <tr key={i} className="border-t border-line"><td className="py-1.5">{date(p.when)}</td><td>{p.kind === "card" ? "Card" : "Offline"}</td><td className="text-right tabular-nums">{p.usd == null ? "not recorded" : usd(p.usd)}</td><td className="text-right tabular-nums">{num(p.credits)}</td></tr>)}</tbody>
          </table>
        )}
      </Card>
    </>
  );
}
