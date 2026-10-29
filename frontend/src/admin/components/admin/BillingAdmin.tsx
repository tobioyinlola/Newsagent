import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, unwrap } from "../../api/client";
import { useCan } from "../../lib/can";
import { Button, Card, ErrorBox, Field, Notice, inputCls } from "../ui";

export function BillingAdmin() {
  const qc = useQueryClient();
  const can = useCan();
  const ws = useQuery({ queryKey: ["admin-ws"], queryFn: () => unwrap(api.GET("/v1/admin/workspaces")), enabled: can("customers.view") });
  const [m, setM] = useState({ workspace: "", credits: "20", ref: "", note: "" });
  const manual = useMutation({ mutationFn: () => unwrap(api.POST("/v1/admin/workspaces/{workspace_id}/credits", { params: { path: { workspace_id: m.workspace } }, body: { credits: m.credits, ref: m.ref, note: m.note } })), onSuccess: () => qc.invalidateQueries({ queryKey: ["admin-ws"] }) });
  return (
    <>
      <Card title="Credit prices">
        <p className="text-sm text-muted">One video costs 1 credit. Customers get 1 free credit when they sign up, then buy $10, $50, $100 or $200 of credits at $2.70 a credit. These are set in the server settings, not here.</p>
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
