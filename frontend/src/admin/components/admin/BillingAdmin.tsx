import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, unwrap } from "../../api/client";
import { useCan } from "../../lib/can";
import { Button, Card, ConfirmDialog, ErrorBox, Field, Notice, inputCls } from "../ui";

export function BillingAdmin() {
  const qc = useQueryClient();
  const can = useCan();
  const ws = useQuery({ queryKey: ["admin-ws"], queryFn: () => unwrap(api.GET("/v1/admin/workspaces")), enabled: can("customers.view") });
  const [m, setM] = useState({ workspace: "", credits: "20", ref: "", note: "" });
  const manual = useMutation({ mutationFn: () => unwrap(api.POST("/v1/admin/workspaces/{workspace_id}/credits", { params: { path: { workspace_id: m.workspace } }, body: { credits: m.credits, ref: m.ref, note: m.note } })), onSuccess: () => qc.invalidateQueries({ queryKey: ["admin-ws"] }) });
  // Adding credit to a wallet is real money: nothing is sent until the summary below is confirmed.
  const [confirming, setConfirming] = useState(false);
  const chosen = ws.data?.find((w) => w.id === m.workspace);
  const fmt = (n: number) => n.toLocaleString("en-US", { minimumFractionDigits: 2, maximumFractionDigits: 2 });
  const adding = Number(m.credits);
  const before = Number(chosen?.credit_balance ?? 0);
  return (
    <>
      <Card title="Credit prices">
        <p className="text-sm text-muted">One video costs 1 credit. Customers get 1 free credit when they sign up, then buy $10, $50, $100 or $200 of credits at $2.70 a credit. These are set in the server settings, not here.</p>
      </Card>
      {can("customers.manage") && <Card title="Record an offline payment">
        <p className="mb-3 text-sm text-muted">For a bank transfer or invoice. The reference makes a double submit harmless.</p>
        <form className="grid gap-3 sm:grid-cols-2" onSubmit={(e) => { e.preventDefault(); manual.reset(); setConfirming(true); }}>
          <Field label="Workspace">{(id) => <select id={id} required className={inputCls} value={m.workspace} onChange={(e) => setM({ ...m, workspace: e.target.value })}><option value="">Choose…</option>{ws.data?.map((w) => <option key={w.id} value={w.id}>{w.name}</option>)}</select>}</Field>
          <Field label="Credits">{(id) => <input id={id} type="number" min="0.01" step="any" required className={inputCls} value={m.credits} onChange={(e) => setM({ ...m, credits: e.target.value })} />}</Field>
          <Field label="Reference (invoice or transfer id)">{(id) => <input id={id} required className={inputCls} value={m.ref} onChange={(e) => setM({ ...m, ref: e.target.value })} />}</Field>
          <Field label="Note">{(id) => <input id={id} className={inputCls} value={m.note} onChange={(e) => setM({ ...m, note: e.target.value })} />}</Field>
          <div className="sm:col-span-2"><Button type="submit" disabled={manual.isPending}>Add credits</Button></div>
        </form>
        {confirming && chosen && (
          <ConfirmDialog
            title={`Add ${fmt(adding)} credits to ${chosen.name}?`}
            confirmLabel={`Yes, add ${fmt(adding)} credits`}
            onCancel={() => setConfirming(false)}
            onConfirm={() => { setConfirming(false); manual.mutate(); }}
          >
            <dl className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-1" aria-label="Credit summary">
              <dt className="text-muted">Workspace</dt><dd className="font-semibold">{chosen.name}</dd>
              <dt className="text-muted">Balance now</dt><dd>{fmt(before)} credits</dd>
              <dt className="text-muted">Adding</dt><dd className="font-semibold">+{fmt(adding)} credits</dd>
              <dt className="text-muted">New balance</dt><dd className="font-semibold">{fmt(before + adding)} credits</dd>
              <dt className="text-muted">Reference</dt><dd className="break-all">{m.ref}</dd>
              {m.note.trim() && <><dt className="text-muted">Note</dt><dd className="break-words">{m.note}</dd></>}
            </dl>
            <p className="mt-3 text-muted">Credits go into this workspace's wallet straight away and can be spent at once. Check the business and the amount.</p>
          </ConfirmDialog>
        )}
        <ErrorBox error={manual.error} />
        {manual.data && <div className="mt-3"><Notice tone="ok">{manual.data.duplicate ? "That reference was already recorded. Nothing was added." : "Credits added."}</Notice></div>}
      </Card>}
    </>
  );
}
