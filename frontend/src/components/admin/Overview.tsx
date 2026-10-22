import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, unwrap } from "../../api/client";
import { Button, Card, ErrorBox, Field, Notice, inputCls } from "../ui";

const PROVIDERS = ["heygen", "synthesia", "mock"];

function Counts({ title, data }: { title: string; data: Record<string, number> | undefined }) {
  const rows = Object.entries(data ?? {});
  return (
    <div><h3 className="mb-1 text-sm font-semibold text-muted">{title}</h3>
      {rows.length ? <ul className="text-sm">{rows.map(([k, n]) => <li key={k} className="flex justify-between"><span>{k.replace("_", " ")}</span><span className="tabular-nums font-medium">{n}</span></li>)}</ul> : <p className="text-sm text-muted">none</p>}</div>
  );
}

export function Overview() {
  const qc = useQueryClient();
  const queue = useQuery({ queryKey: ["admin-queue"], queryFn: () => unwrap(api.GET("/v1/admin/queue")), refetchInterval: 10000 });
  const settings = useQuery({ queryKey: ["admin-settings"], queryFn: () => unwrap(api.GET("/v1/admin/settings")) });
  const [reason, setReason] = useState("");
  const patch = useMutation({
    mutationFn: (body: Record<string, unknown>) => unwrap(api.PATCH("/v1/admin/settings", { body })),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["admin-settings"] }); qc.invalidateQueries({ queryKey: ["admin-queue"] }); },
  });
  const s = settings.data;
  const q = queue.data;
  return (
    <>
      {q?.paused && <Notice tone="warn"><strong>Paid steps are paused.</strong> New work is held in "limit reached" until you resume.</Notice>}
      <Card title="Queue">
        <div className="grid gap-6 sm:grid-cols-4">
          <Counts title="Videos" data={q?.projects} /><Counts title="Jobs" data={q?.jobs} /><Counts title="Founder answers" data={q?.takes} />
          <div><h3 className="mb-1 text-sm font-semibold text-muted">Waiting for review</h3><p className="text-3xl font-bold tabular-nums">{q?.moderation_pending ?? 0}</p></div>
        </div>
      </Card>
      <Card title="Emergency pause">
        <p className="mb-3 text-sm text-muted">Stops every paid step (avatar, rendering, transcription) immediately. Videos in progress move to "limit reached" and resume with Retry once you turn this off. Use it for a vendor incident or runaway spend.</p>
        <div className="flex flex-wrap items-end gap-3">
          {!s?.paused && <Field label="Reason (shown to nobody, kept in the audit log)">{(id) => <input id={id} className={inputCls} value={reason} onChange={(e) => setReason(e.target.value)} />}</Field>}
          <Button variant={s?.paused ? "primary" : "danger"} disabled={patch.isPending} onClick={() => patch.mutate({ paused: !s?.paused, pause_reason: s?.paused ? "" : reason })}>{s?.paused ? "Resume paid steps" : "Pause all paid steps"}</Button>
        </div>
        <ErrorBox error={patch.error} />
      </Card>
      <Card title="Avatar provider failover">
        <p className="mb-3 text-sm text-muted">If the primary provider fails or its monthly budget is used up, clips are made with the secondary (its own budget applies). Operators are emailed.</p>
        <div className="grid gap-3 sm:grid-cols-3">
          <Field label="Primary">{(id) => <select id={id} className={inputCls} value={s?.avatar_primary ?? "heygen"} onChange={(e) => patch.mutate({ avatar_primary: e.target.value })}>{PROVIDERS.map((p) => <option key={p}>{p}</option>)}</select>}</Field>
          <Field label="Secondary">{(id) => <select id={id} className={inputCls} value={s?.avatar_secondary ?? "none"} onChange={(e) => patch.mutate({ avatar_secondary: e.target.value })}>{["none", ...PROVIDERS].map((p) => <option key={p}>{p}</option>)}</select>}</Field>
          <label className="flex items-center gap-2 pt-6 text-sm"><input type="checkbox" checked={!!s?.avatar_failover} onChange={(e) => patch.mutate({ avatar_failover: e.target.checked })} /> Fail over automatically</label>
        </div>
      </Card>
      <Card title="Content moderation">
        <div className="flex flex-wrap items-center gap-4 text-sm">
          <label className="flex items-center gap-2">Mode
            <select aria-label="Moderation mode" className={inputCls + " w-auto"} value={s?.moderation_mode ?? "enforce"} onChange={(e) => patch.mutate({ moderation_mode: e.target.value })}>
              <option value="enforce">Enforce (hold and block)</option><option value="log_only">Log only (nothing is held)</option></select></label>
          <label className="flex items-center gap-2"><input type="checkbox" checked={!!s?.moderation_llm} onChange={(e) => patch.mutate({ moderation_llm: e.target.checked })} /> Also check with the AI reviewer</label>
        </div>
        {s?.moderation_mode === "log_only" && <div className="mt-3"><Notice tone="warn">Moderation is in log-only mode: borderline content will not be held for review.</Notice></div>}
      </Card>
    </>
  );
}
