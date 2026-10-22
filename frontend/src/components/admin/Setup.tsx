import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, unwrap } from "../../api/client";
import { Button, Card, ErrorBox, Field, inputCls, Notice } from "../ui";

export function Setup() {
  const qc = useQueryClient();
  const ws = useQuery({ queryKey: ["admin-ws"], queryFn: () => unwrap(api.GET("/v1/admin/workspaces")) });
  const budgets = useQuery({ queryKey: ["admin-budgets"], queryFn: () => unwrap(api.GET("/v1/admin/vendor-budgets")) });
  const [inv, setInv] = useState({ email: "", workspace_name: "", credits: "20", spend_cap: "50" });
  const [vb, setVb] = useState({ vendor: "heygen", limit: "100" });
  const invite = useMutation({
    mutationFn: () => unwrap(api.POST("/v1/admin/invites", { body: { email: inv.email, workspace_name: inv.workspace_name, credits: inv.credits, spend_cap: inv.spend_cap } })),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["admin-ws"] }),
  });
  const patch = useMutation({
    mutationFn: ({ id, body }: { id: string; body: Record<string, unknown> }) => unwrap(api.PATCH("/v1/admin/workspaces/{workspace_id}", { params: { path: { workspace_id: id } }, body })),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["admin-ws"] }),
  });
  const setBudget = useMutation({ mutationFn: () => unwrap(api.PUT("/v1/admin/vendor-budgets", { body: { vendor: vb.vendor, limit: vb.limit } })), onSuccess: () => qc.invalidateQueries({ queryKey: ["admin-budgets"] }) });
  const link = invite.data ? `${location.origin}/login?invite=${encodeURIComponent(invite.data.code)}` : null;

  return (
    <>
      <Card title="Invite a startup">
        <form className="grid gap-3 sm:grid-cols-2" onSubmit={(e) => { e.preventDefault(); invite.mutate(); }}>
          <Field label="Invitee email">{(id) => <input id={id} type="email" required className={inputCls} value={inv.email} onChange={(e) => setInv({ ...inv, email: e.target.value })} />}</Field>
          <Field label="Startup name">{(id) => <input id={id} required className={inputCls} value={inv.workspace_name} onChange={(e) => setInv({ ...inv, workspace_name: e.target.value })} />}</Field>
          <Field label="Starting credits">{(id) => <input id={id} type="number" min="0" step="any" className={inputCls} value={inv.credits} onChange={(e) => setInv({ ...inv, credits: e.target.value })} />}</Field>
          <Field label="Spend cap">{(id) => <input id={id} type="number" min="0" step="any" className={inputCls} value={inv.spend_cap} onChange={(e) => setInv({ ...inv, spend_cap: e.target.value })} />}</Field>
          <div className="sm:col-span-2"><Button type="submit" disabled={invite.isPending}>Create invite</Button></div>
        </form>
        <ErrorBox error={invite.error} />
        {link && <div className="mt-3"><Notice tone="ok">Send this link to {inv.email} (single use, expires in 14 days):<br /><code className="break-all">{link}</code></Notice></div>}
      </Card>

      <Card title="Vendor budgets (this month)">
        <p className="mb-3 text-sm text-muted">A vendor with no budget is blocked. Operators are alerted at 80%.</p>
        <table className="mb-4 w-full text-sm"><caption className="sr-only">Vendor budgets</caption><thead><tr className="text-left text-muted"><th>Vendor</th><th>Period</th><th className="text-right">Spent</th><th className="text-right">Limit</th></tr></thead>
          <tbody>{budgets.data?.map((b) => <tr key={b.vendor + b.period} className="border-t border-line"><td className="py-1">{b.vendor}</td><td>{b.period}</td><td className="text-right">{Number(b.spent).toFixed(2)}</td><td className="text-right">{Number(b.limit).toFixed(2)}</td></tr>)}</tbody></table>
        <form className="flex flex-wrap items-end gap-3" onSubmit={(e) => { e.preventDefault(); setBudget.mutate(); }}>
          <Field label="Vendor">{(id) => <select id={id} className={inputCls} value={vb.vendor} onChange={(e) => setVb({ ...vb, vendor: e.target.value })}>{["heygen", "renderer", "transcription", "mock"].map((v) => <option key={v}>{v}</option>)}</select>}</Field>
          <Field label="Monthly limit">{(id) => <input id={id} type="number" min="0" step="any" className={inputCls} value={vb.limit} onChange={(e) => setVb({ ...vb, limit: e.target.value })} />}</Field>
          <Button type="submit" variant="secondary">Set budget</Button>
        </form>
        <ErrorBox error={setBudget.error} />
      </Card>

      <Card title="Workspaces">
        <ErrorBox error={ws.error ?? patch.error} />
        <ul className="divide-y divide-line">
          {ws.data?.map((w) => (
            <li key={w.id} className="flex flex-wrap items-center justify-between gap-2 py-3 text-sm">
              <span><strong>{w.name}</strong> · {Number(w.credit_balance).toFixed(2)} credits · spent {Number(w.spent_total).toFixed(2)} / cap {Number(w.spend_cap).toFixed(2)}{w.suspended && " · suspended"}{w.share_disabled && " · sharing off"}</span>
              <span className="flex gap-2">
                <Button variant="secondary" onClick={() => patch.mutate({ id: w.id, body: { credit_balance: String(Number(w.credit_balance) + 10) } })}>+10 credits</Button>
                <Button variant="secondary" onClick={() => patch.mutate({ id: w.id, body: { share_disabled: !w.share_disabled } })}>{w.share_disabled ? "Enable" : "Disable"} sharing</Button>
                <Button variant={w.suspended ? "secondary" : "danger"} onClick={() => patch.mutate({ id: w.id, body: { suspended: !w.suspended } })}>{w.suspended ? "Unsuspend" : "Suspend"}</Button>
              </span>
            </li>
          ))}
        </ul>
      </Card>
    </>
  );
}
