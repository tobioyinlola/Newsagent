import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, unwrap } from "../../api/client";
import { useCan } from "../../lib/can";
import { Button, Card, ErrorBox, Field, Notice, inputCls } from "../ui";

export function BillingAdmin() {
  const qc = useQueryClient();
  const can = useCan();
  const packs = useQuery({ queryKey: ["admin-packs"], queryFn: () => unwrap(api.GET("/v1/admin/packs")) });
  const ws = useQuery({ queryKey: ["admin-ws"], queryFn: () => unwrap(api.GET("/v1/admin/workspaces")), enabled: can("customers.view") });
  const [p, setP] = useState({ name: "", credits: "20", price: "25" });
  const [m, setM] = useState({ workspace: "", credits: "20", ref: "", note: "" });
  const create = useMutation({ mutationFn: () => unwrap(api.POST("/v1/admin/packs", { body: { name: p.name, credits: p.credits, price_usd: p.price } })), onSuccess: () => { setP({ ...p, name: "" }); qc.invalidateQueries({ queryKey: ["admin-packs"] }); } });
  const toggle = useMutation({ mutationFn: ({ id, active }: { id: string; active: boolean }) => unwrap(api.PATCH("/v1/admin/packs/{pack_id}", { params: { path: { pack_id: id } }, body: { active } })), onSuccess: () => qc.invalidateQueries({ queryKey: ["admin-packs"] }) });
  const manual = useMutation({ mutationFn: () => unwrap(api.POST("/v1/admin/workspaces/{workspace_id}/credits", { params: { path: { workspace_id: m.workspace } }, body: { credits: m.credits, ref: m.ref, note: m.note } })), onSuccess: () => qc.invalidateQueries({ queryKey: ["admin-ws"] }) });
  return (
    <>
      <Card title="Credit packs">
        <p className="mb-3 text-sm text-muted">What customers can buy. Prices are decided by you; the payment provider is configured separately.</p>
        <ul className="mb-4 divide-y divide-line text-sm">{packs.data?.map((k) => (
          <li key={k.id} className="flex items-center justify-between py-2"><span><strong>{k.name}</strong> · {Number(k.credits)} credits · ${Number(k.price_usd).toFixed(2)}</span>
            {can("finance.manage") && <Button variant="secondary" onClick={() => toggle.mutate({ id: k.id, active: false })}>Retire</Button>}</li>))}
          {packs.data?.length === 0 && <li className="py-2 text-muted">No packs yet.</li>}</ul>
        {can("finance.manage") && <form className="flex flex-wrap items-end gap-3" onSubmit={(e) => { e.preventDefault(); create.mutate(); }}>
          <Field label="Name">{(id) => <input id={id} required className={inputCls} value={p.name} onChange={(e) => setP({ ...p, name: e.target.value })} />}</Field>
          <Field label="Credits">{(id) => <input id={id} type="number" min="1" step="any" className={inputCls} value={p.credits} onChange={(e) => setP({ ...p, credits: e.target.value })} />}</Field>
          <Field label="Price (USD)">{(id) => <input id={id} type="number" min="0" step="any" className={inputCls} value={p.price} onChange={(e) => setP({ ...p, price: e.target.value })} />}</Field>
          <Button type="submit" disabled={create.isPending}>Add pack</Button>
        </form>}
        <ErrorBox error={create.error ?? toggle.error} />
      </Card>
      {can("customers.manage") && <Card title="Record an offline payment">
        <p className="mb-3 text-sm text-muted">For a bank transfer or invoice. The reference makes a double submit harmless.</p>
        <form className="grid gap-3 sm:grid-cols-2" onSubmit={(e) => { e.preventDefault(); manual.mutate(); }}>
          <Field label="Workspace">{(id) => <select id={id} required className={inputCls} value={m.workspace} onChange={(e) => setM({ ...m, workspace: e.target.value })}><option value="">Choose…</option>{ws.data?.map((w) => <option key={w.id} value={w.id}>{w.name}</option>)}</select>}</Field>
          <Field label="Credits">{(id) => <input id={id} type="number" min="0.01" step="any" className={inputCls} value={m.credits} onChange={(e) => setM({ ...m, credits: e.target.value })} />}</Field>
          <Field label="Reference (invoice or transfer id)">{(id) => <input id={id} required className={inputCls} value={m.ref} onChange={(e) => setM({ ...m, ref: e.target.value })} />}</Field>
          <Field label="Note">{(id) => <input id={id} className={inputCls} value={m.note} onChange={(e) => setM({ ...m, note: e.target.value })} />}</Field>
          <div className="sm:col-span-2"><Button type="submit" disabled={manual.isPending}>Add credits</Button></div>
        </form>
        <ErrorBox error={manual.error} />
        {manual.data && <div className="mt-3"><Notice tone="ok">{manual.data.duplicate ? "That reference was already recorded. Nothing was added." : "Credits added."}</Notice></div>}
      </Card>}
    </>
  );
}
