import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, unwrap } from "../../api/client";
import { useCan } from "../../lib/can";
import { Button, Card, ErrorBox, Field, Notice, inputCls } from "../ui";

const PROVIDERS = ["heygen", "synthesia", "mock"];

function Counts({ title, data }: { title: string; data: Record<string, number> | undefined }) {
  const rows = Object.entries(data ?? {});
  return (
    <div><h3 className="mb-1 text-sm font-semibold text-muted">{title}</h3>
      {rows.length ? <ul className="text-sm">{rows.map(([k, n]) => <li key={k} className="flex justify-between"><span>{k.replace("_", " ")}</span><span className="tabular-nums font-medium">{n}</span></li>)}</ul> : <p className="text-sm text-muted">none</p>}</div>
  );
}

const LANE_NAME: Record<string, string> = { avatar: "Presenter clips", render: "Final renders" };
const STEP_NAME: Record<string, string> = { anchor_render: "Presenter clips", question_clips: "Question clips", preview_render: "Preview render", final_render: "Final render", merge_render: "Final render" };

function span(sec: number | null | undefined): string {
  if (sec == null) return "n/a";
  if (sec < 90) return `${Math.round(sec)} s`;
  if (sec < 5400) return `${Math.round(sec / 60)} min`;
  return `${(sec / 3600).toFixed(1)} h`;
}

// Videos waiting for, or being given, presenter clips and renders. Only shown when the line is switched on (QUEUE_MODE=dispatcher).
function Line({ lanes }: { lanes: { lane: string; waiting: number; running: number; slots: number; oldest_wait_s: number; typical_s?: number | null; paused?: boolean }[] }) {
  const qc = useQueryClient();
  const canManage = useCan()("operations.manage");
  const items = useQuery({ queryKey: ["admin-line"], queryFn: () => unwrap(api.GET("/v1/admin/line", { params: { query: { limit: 100 } } })), refetchInterval: 10000 });
  const refresh = () => { void qc.invalidateQueries({ queryKey: ["admin-line"] }); void qc.invalidateQueries({ queryKey: ["admin-queue"] }); };
  const front = useMutation({ mutationFn: (id: string) => unwrap(api.POST("/v1/admin/line/{project_id}/front", { params: { path: { project_id: id } } })), onSuccess: refresh });
  const stop = useMutation({ mutationFn: (id: string) => unwrap(api.POST("/v1/admin/line/{project_id}/cancel", { params: { path: { project_id: id } } })), onSuccess: refresh });
  const pause = useMutation({ mutationFn: (v: { lane: string; paused: boolean }) => unwrap(api.POST("/v1/admin/line/lanes/{lane}/pause", { params: { path: { lane: v.lane } }, body: { paused: v.paused } })), onSuccess: refresh });
  return (
    <Card title="Line for presenter clips and renders">
      <div className="grid gap-4 sm:grid-cols-2">
        {lanes.map((l) => (
          <div key={l.lane} className="rounded-xl border border-line p-3 text-sm">
            <div className="flex items-baseline justify-between gap-2"><h3 className="font-semibold">{LANE_NAME[l.lane] ?? l.lane}</h3>{l.paused && <span className="text-xs font-semibold text-red-700">Paused</span>}</div>
            <p className="mt-1 text-muted">Running {l.running} of {l.slots} at once · waiting {l.waiting} · longest wait {span(l.oldest_wait_s)} · typical {span(l.typical_s)}</p>
            {canManage && <Button variant="secondary" className="mt-2" disabled={pause.isPending} onClick={() => pause.mutate({ lane: l.lane, paused: !l.paused })}>{l.paused ? "Release this line" : "Hold this line"}</Button>}
          </div>
        ))}
      </div>
      {!!items.data?.length && (
        <div className="mt-4 overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="text-xs text-muted"><tr><th className="py-1 pr-3">Business</th><th className="pr-3">Step</th><th className="pr-3">Place</th><th className="pr-3">Waited</th>{canManage && <th />}</tr></thead>
            <tbody>
              {items.data.map((i) => (
                <tr key={i.project_id} className="border-t border-line">
                  <td className="py-1.5 pr-3">{i.workspace_name}</td>
                  <td className="pr-3">{STEP_NAME[i.step] ?? i.step}</td>
                  <td className="pr-3">{i.state === "running" ? "Being made" : `${i.position}${i.priority > 0 ? " (moved up)" : ""}`}</td>
                  <td className="pr-3 tabular-nums">{span(i.waited_s)}</td>
                  {canManage && (
                    <td className="space-x-2 whitespace-nowrap text-right">
                      {i.state === "waiting" && <Button variant="secondary" disabled={front.isPending} onClick={() => front.mutate(i.project_id)}>Move to front</Button>}
                      <Button variant="secondary" disabled={stop.isPending} onClick={() => { if (confirm("Stop this video? The owner can retry it later.")) stop.mutate(i.project_id); }}>Stop</Button>
                    </td>
                  )}
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
      <ErrorBox error={front.error ?? stop.error ?? pause.error} />
    </Card>
  );
}

export function Operations() {
  const qc = useQueryClient();
  const canSet = useCan()("settings.manage");
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
      {!!q?.lanes?.length && <Line lanes={q.lanes} />}
      {canSet ? (
        <>
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
      ) : (
        <Notice tone="info">System switches (pause, failover, moderation) can only be changed by people whose role allows it.</Notice>
      )}
    </>
  );
}
