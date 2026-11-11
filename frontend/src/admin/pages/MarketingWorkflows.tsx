import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, unwrap } from "../api/client";
import { Button, Card, ConfirmDialog, ErrorBox, inputCls, Notice } from "../components/ui";
import { num } from "../lib/format";
import { useCan } from "../lib/can";
import type { Preview } from "../lib/segments";

type Step = { type: "email"; copy_id: string; copy_version?: number; only_if_segment_id?: string | null } | { type: "wait"; days: number; hours: number } | { type: "branch"; segment_id: string; yes_to?: number | null; no_to?: number | null } | { type: "end" };
type Hours = { enabled: boolean; start: number; end: number };
type Stats = { active: number; completed: number; exited: number; exits: Record<string, number>; sent_by_step: Record<string, number>; opened_by_step?: Record<string, number>; clicked_by_step?: Record<string, number> };
type Workflow = { id: string; name: string; status: "draft" | "active" | "paused" | "stopped"; trigger_segment_id: string; trigger_segment_name: string; goal_segment_id: string | null; goal_segment_name: string; steps: Step[]; hours: Hours; reentry_days?: number | null; stats?: Stats; preview?: Preview };
type Pick = { id: string; name: string };

const STATUS: Record<Workflow["status"], [string, string]> = { draft: ["Draft", "bg-paper"], active: ["On", "bg-lime-tint"], paused: ["Paused", "bg-peach-tint"], stopped: ["Stopped", "bg-brand-red"] };
const EXIT: Record<string, string> = { goal_reached: "reached the goal", existing_at_start: "were already members when it was switched on", opted_out: "unsubscribed", suppressed: "had a blocked address", account_inactive: "closed or suspended", account_gone: "account gone", workflow_stopped: "left when it was stopped" };
const Badge = ({ s }: { s: Workflow["status"] }) => <span className={`rounded-sm px-1.5 py-0.5 text-xs font-bold ${STATUS[s][1]}`}>{STATUS[s][0]}</span>;
const DEFAULT_HOURS: Hours = { enabled: true, start: 9, end: 18 };
const waitText = (s: { days: number; hours: number }) => [s.days && `${s.days} day${s.days === 1 ? "" : "s"}`, s.hours && `${s.hours} hour${s.hours === 1 ? "" : "s"}`].filter(Boolean).join(" ");

// Branch targets are step numbers, so they must follow the steps when one is moved or removed.
function retarget(steps: Step[], map: (old: number) => number | null): Step[] {
  const fix = (t?: number | null) => (t == null ? null : map(t));
  return steps.map((s) => (s.type === "branch" ? { ...s, yes_to: fix(s.yes_to), no_to: fix(s.no_to) } : s));
}
const target = (t: number | null | undefined, at: number) => (t != null && t > at ? t : null); // only forward jumps are allowed; anything else means "finish"

function Funnel({ w, copyName, segName }: { w: Workflow; copyName: (id: string) => string; segName: (id: string) => string }) {
  const st = w.stats;
  return (
    <div className="space-y-3 text-sm">
      {st && <p><b>{num(st.active)}</b> in progress · <b>{num(st.completed)}</b> finished · <b>{num(st.exited)}</b> left{Object.keys(st.exits).length > 0 && <span className="text-muted"> ({Object.entries(st.exits).map(([r, n]) => `${num(n)} ${EXIT[r] ?? r}`).join(", ")})</span>}</p>}
      <ol className="space-y-2">
        {w.steps.map((s, i) => (
          <li key={i} className="rounded-lg border border-line px-3 py-2">
            {s.type === "wait" ? <span className="text-muted">Wait {waitText(s)}</span> : s.type === "end" ? <span className="text-muted">Finish here</span> : s.type === "branch" ? <span><b>If</b> in “{segName(s.segment_id)}”: {s.yes_to != null ? `go to step ${s.yes_to + 1}` : "finish"}; otherwise {s.no_to != null ? `go to step ${s.no_to + 1}` : "finish"}</span> : <span><b>Email:</b> {copyName(s.copy_id)}{s.copy_version ? ` (v${s.copy_version})` : ""}{s.only_if_segment_id && <span className="text-muted"> · only if in “{segName(s.only_if_segment_id)}”</span>}{st && <span className="ml-2 rounded-sm bg-lime-tint px-1.5 py-0.5 text-xs font-semibold">{num(st.sent_by_step[String(i)] ?? 0)} sent</span>}{st && (st.sent_by_step[String(i)] ?? 0) > 0 && <span className="ml-2 text-xs text-muted">{num(st.opened_by_step?.[String(i)] ?? 0)} opened · {num(st.clicked_by_step?.[String(i)] ?? 0)} clicked</span>}</span>}
          </li>
        ))}
      </ol>
    </div>
  );
}

function Builder({ wf, segments, copies, onDone }: { wf: Workflow | null; segments: Pick[]; copies: Pick[]; onDone: (id?: string) => void }) {
  const qc = useQueryClient();
  const [name, setName] = useState(wf?.name ?? "");
  const [trigger, setTrigger] = useState(wf?.trigger_segment_id ?? "");
  const [goal, setGoal] = useState(wf?.goal_segment_id ?? "");
  const [hours, setHours] = useState<Hours>(wf?.hours && "start" in wf.hours ? wf.hours : DEFAULT_HOURS);
  const [steps, setSteps] = useState<Step[]>(wf?.steps ?? [{ type: "email", copy_id: "" }]);
  const [again, setAgain] = useState(!!wf?.reentry_days);
  const [days, setDays] = useState(wf?.reentry_days ?? 30);
  const patch = (i: number, p: Partial<Step>) => setSteps(steps.map((s, j) => (j === i ? ({ ...s, ...p } as Step) : s)));
  const move = (i: number, d: -1 | 1) => { const j = i + d; if (j < 0 || j >= steps.length) return; const n = [...steps]; [n[i], n[j]] = [n[j], n[i]]; setSteps(retarget(n, (k) => (k === i ? j : k === j ? i : k))); };
  const remove = (i: number) => setSteps(retarget(steps.filter((_, j) => j !== i), (k) => (k === i ? null : k > i ? k - 1 : k)));
  const label = (s: Step, k: number) => `Step ${k + 1}: ${s.type === "email" ? copies.find((c) => c.id === s.copy_id)?.name ?? "email" : s.type === "wait" ? `wait ${waitText(s)}` : s.type === "end" ? "finish" : "branch"}`;
  const body = () => ({ name, trigger_segment_id: trigger, goal_segment_id: goal || null, hours, reentry_days: again ? days : null, steps: steps.map((s, i) => (s.type === "email" ? { type: "email" as const, copy_id: s.copy_id, only_if_segment_id: s.only_if_segment_id || null } : s.type === "branch" ? { type: "branch" as const, segment_id: s.segment_id, yes_to: target(s.yes_to, i), no_to: target(s.no_to, i) } : s)) });
  const save = useMutation({
    mutationFn: () => (wf ? unwrap(api.PUT("/v1/admin/marketing/workflows/{workflow_id}", { params: { path: { workflow_id: wf.id } }, body: body() as never })) : unwrap(api.POST("/v1/admin/marketing/workflows", { body: body() as never }))),
    onSuccess: async (r) => { await qc.invalidateQueries({ queryKey: ["workflows"] }); await qc.invalidateQueries({ queryKey: ["workflow"] }); onDone((r as unknown as Workflow).id); },
  });
  const ready = name.trim() && trigger && steps.length > 0 && steps.every((s) => (s.type === "email" ? s.copy_id : s.type === "wait" ? s.days + s.hours > 0 : s.type === "branch" ? s.segment_id : true));
  return (
    <Card title={wf ? "Edit workflow" : "New workflow"} actions={<Button variant="secondary" onClick={() => onDone(wf?.id)}>Cancel</Button>}>
      <div className="space-y-4 text-sm">
        <label className="block font-semibold">Name<input className={inputCls} value={name} maxLength={120} onChange={(e) => setName(e.target.value)} /></label>
        <div className="grid gap-3 sm:grid-cols-2">
          <label className="block font-semibold">Who gets in<select className={inputCls} value={trigger} onChange={(e) => setTrigger(e.target.value)}><option value="">Choose a segment…</option>{segments.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}</select><span className="mt-1 block text-xs font-normal text-muted">Anyone who matches this segment joins, now or later.</span></label>
          <label className="block font-semibold">Goal (optional)<select className={inputCls} value={goal} onChange={(e) => setGoal(e.target.value)}><option value="">No goal</option>{segments.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}</select><span className="mt-1 block text-xs font-normal text-muted">Anyone who matches this leaves the workflow, so they stop getting emails once they’ve done what you wanted.</span></label>
        </div>
        <fieldset className="space-y-2">
          <legend className="font-semibold">Steps</legend>
          <ol className="space-y-3">
            {steps.map((s, i) => (
              <li key={i} className="space-y-2 rounded-xl border border-line p-3">
                <div className="flex flex-wrap items-center justify-between gap-2">
                  <b>{i + 1}. {s.type === "email" ? "Send an email" : s.type === "wait" ? "Wait" : s.type === "branch" ? "Branch" : "Finish here"}</b>
                  <div className="flex gap-2">
                    <Button variant="secondary" type="button" aria-label={`Move step ${i + 1} up`} disabled={i === 0} onClick={() => move(i, -1)}>↑</Button>
                    <Button variant="secondary" type="button" aria-label={`Move step ${i + 1} down`} disabled={i === steps.length - 1} onClick={() => move(i, 1)}>↓</Button>
                    <Button variant="secondary" type="button" aria-label={`Remove step ${i + 1}`} onClick={() => remove(i)}>Remove</Button>
                  </div>
                </div>
                {s.type === "email" ? (
                  <div className="grid gap-2 sm:grid-cols-2">
                    <label className="block">Email<select className={inputCls} value={s.copy_id} onChange={(e) => patch(i, { copy_id: e.target.value })}><option value="">Choose an email…</option>{copies.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</select></label>
                    <label className="block">Only send if they’re in (optional)<select className={inputCls} value={s.only_if_segment_id ?? ""} onChange={(e) => patch(i, { only_if_segment_id: e.target.value || null })}><option value="">Everyone</option>{segments.map((g) => <option key={g.id} value={g.id}>{g.name}</option>)}</select></label>
                  </div>
                ) : s.type === "end" ? (
                  <p className="text-muted">Anyone who gets here leaves the workflow as finished.</p>
                ) : s.type === "branch" ? (
                  <div className="space-y-2">
                    <label className="block">If they’re in<select className={inputCls} value={s.segment_id} onChange={(e) => patch(i, { segment_id: e.target.value })}><option value="">Choose a segment…</option>{segments.map((g) => <option key={g.id} value={g.id}>{g.name}</option>)}</select></label>
                    <div className="grid gap-2 sm:grid-cols-2">
                      {([["yes_to", "go to"], ["no_to", "if not, go to"]] as const).map(([k, text]) => (
                        <label key={k} className="block">{text}<select aria-label={k === "yes_to" ? `Step ${i + 1} if in the group` : `Step ${i + 1} if not in the group`} className={inputCls} value={String(target(s[k], i) ?? "")} onChange={(e) => patch(i, { [k]: e.target.value === "" ? null : Number(e.target.value) } as Partial<Step>)}><option value="">Finish</option>{steps.map((t, n) => (n > i ? <option key={n} value={n}>{label(t, n)}</option> : null))}</select></label>
                      ))}
                    </div>
                    <p className="text-xs text-muted">A branch can only jump forward, so a workflow can never loop. Put “Finish here” at the end of a path to stop people running on into the other one.</p>
                  </div>
                ) : (
                  <div className="flex items-center gap-2"><input aria-label="Days" type="number" min={0} max={90} className={`${inputCls} !w-20`} value={s.days} onChange={(e) => patch(i, { days: Number(e.target.value) })} /> days <input aria-label="Hours" type="number" min={0} max={23} className={`${inputCls} !w-20`} value={s.hours} onChange={(e) => patch(i, { hours: Number(e.target.value) })} /> hours</div>
                )}
              </li>
            ))}
          </ol>
          <div className="flex gap-2">
            <Button type="button" variant="secondary" onClick={() => setSteps([...steps, { type: "email", copy_id: "" }])}>Add an email</Button>
            <Button type="button" variant="secondary" onClick={() => setSteps([...steps, { type: "wait", days: 1, hours: 0 }])}>Add a wait</Button>
            <Button type="button" variant="secondary" onClick={() => setSteps([...steps, { type: "branch", segment_id: "", yes_to: null, no_to: null }])}>Add a branch</Button>
            <Button type="button" variant="secondary" onClick={() => setSteps([...steps, { type: "end" }])}>Add a finish</Button>
          </div>
        </fieldset>
        <fieldset className="space-y-2">
          <legend className="font-semibold">Sending hours</legend>
          <label className="flex items-center gap-2"><input type="checkbox" checked={hours.enabled} onChange={(e) => setHours({ ...hours, enabled: e.target.checked })} /> Only email during the day where the person lives</label>
          {hours.enabled && <div className="flex items-center gap-2">between <input aria-label="From hour" type="number" min={0} max={23} className={`${inputCls} !w-20`} value={hours.start} onChange={(e) => setHours({ ...hours, start: Number(e.target.value) })} /> and <input aria-label="To hour" type="number" min={1} max={24} className={`${inputCls} !w-20`} value={hours.end} onChange={(e) => setHours({ ...hours, end: Number(e.target.value) })} /> o’clock <span className="text-xs text-muted">(by their country; Nigeria’s time if we don’t know it)</span></div>}
        </fieldset>
        <fieldset className="space-y-2">
          <legend className="font-semibold">Going through again</legend>
          <label className="flex items-center gap-2"><input type="checkbox" checked={again} onChange={(e) => setAgain(e.target.checked)} /> Let people go through it again</label>
          {again && <div className="flex flex-wrap items-center gap-2">once they have finished, and at least <input aria-label="Days before re-entry" type="number" min={7} max={365} className={`${inputCls} !w-24`} value={days} onChange={(e) => setDays(Number(e.target.value))} /> days have passed, if they match “who gets in” again.</div>}
          {!again && <p className="text-xs text-muted">Off: everyone goes through at most once.</p>}
        </fieldset>
        <ErrorBox error={save.error} />
        <Button disabled={!ready || save.isPending} onClick={() => save.mutate()}>{save.isPending ? "Saving…" : "Save draft"}</Button>
      </div>
    </Card>
  );
}

function Detail({ id, segments, copies, engine, manage, onClose }: { id: string; segments: Pick[]; copies: Pick[]; engine: string; manage: boolean; onClose: () => void }) {
  const qc = useQueryClient();
  const q = useQuery({
    queryKey: ["workflow", id],
    queryFn: () => unwrap(api.GET("/v1/admin/marketing/workflows/{workflow_id}", { params: { path: { workflow_id: id } } })) as unknown as Promise<Workflow>,
    refetchInterval: (query) => (query.state.data?.status === "active" ? 10000 : false),
  });
  const [editing, setEditing] = useState(false);
  const [asking, setAsking] = useState<"on" | "stop" | "delete" | null>(null);
  const [existing, setExisting] = useState(false);
  const refresh = async () => { setAsking(null); await qc.invalidateQueries({ queryKey: ["workflow", id] }); await qc.invalidateQueries({ queryKey: ["workflows"] }); };
  const w = q.data;
  const reach = w?.preview?.reachable ?? 0;
  const act = useMutation({
    mutationFn: (a: "pause" | "resume" | "stop") => unwrap(api.POST("/v1/admin/marketing/workflows/{workflow_id}/{action}", { params: { path: { workflow_id: id, action: a } } })),
    onSuccess: refresh,
  });
  const on = useMutation({
    mutationFn: () => unwrap(api.POST("/v1/admin/marketing/workflows/{workflow_id}/activate", { params: { path: { workflow_id: id } }, body: { include_existing: existing, confirm_count: reach } })),
    onSuccess: refresh,
  });
  const del = useMutation({ mutationFn: () => unwrap(api.DELETE("/v1/admin/marketing/workflows/{workflow_id}", { params: { path: { workflow_id: id } } })), onSuccess: async () => { await qc.invalidateQueries({ queryKey: ["workflows"] }); onClose(); } });
  const copyName = (cid: string) => copies.find((c) => c.id === cid)?.name ?? "(deleted email)";
  const segName = (sid: string) => segments.find((s) => s.id === sid)?.name ?? "(deleted segment)";
  if (editing && w) return <Builder wf={w} segments={segments} copies={copies} onDone={() => { setEditing(false); void refresh(); }} />;
  return (
    <Card title={w?.name ?? "Workflow"} actions={<Button variant="secondary" onClick={onClose}>Back</Button>}>
      <ErrorBox error={q.error ?? act.error ?? on.error ?? del.error} />
      {!w ? <p aria-busy="true">Loading…</p> : (
        <div className="space-y-4 text-sm">
          <p><Badge s={w.status} /> <span className="ml-2 text-muted">Who gets in: {w.trigger_segment_name}{w.goal_segment_name && ` · Goal: ${w.goal_segment_name}`}{w.hours.enabled ? ` · Sends ${w.hours.start}:00 to ${w.hours.end}:00 local time` : " · Sends at any hour"}{w.reentry_days ? ` · People can go through again after ${w.reentry_days} days` : ""}</span></p>
          <Funnel w={w} copyName={copyName} segName={segName} />
          {w.status === "draft" && w.preview && <p><b className="text-lg tabular-nums">{num(reach)}</b> people match “{w.trigger_segment_name}” and can be emailed right now.</p>}
          {w.status === "draft" && engine === "off" && <Notice tone="warn">Marketing email is switched off on the server (MARKETING_EMAIL), so this can’t be switched on yet.</Notice>}
          {w.status === "draft" && engine === "dry_run" && <Notice tone="info">Dry run: nothing will really be emailed; each send is only logged.</Notice>}
          {manage && (
            <div className="flex flex-wrap gap-2">
              {w.status === "draft" && <Button variant="secondary" onClick={() => setEditing(true)}>Edit</Button>}
              {w.status === "draft" && <Button disabled={engine === "off" || on.isPending} onClick={() => setAsking("on")}>Switch on…</Button>}
              {w.status === "draft" && <Button variant="danger" onClick={() => setAsking("delete")}>Delete draft</Button>}
              {w.status === "active" && <Button variant="secondary" disabled={act.isPending} onClick={() => act.mutate("pause")}>Pause</Button>}
              {w.status === "paused" && <Button disabled={act.isPending} onClick={() => act.mutate("resume")}>Resume</Button>}
              {(w.status === "active" || w.status === "paused") && <Button variant="danger" onClick={() => setAsking("stop")}>Stop for good</Button>}
            </div>
          )}
        </div>
      )}
      {asking === "on" && w && (
        <ConfirmDialog title="Switch this workflow on?" confirmLabel="Switch on" onConfirm={() => on.mutate()} onCancel={() => setAsking(null)}>
          <p>The words and rules are fixed as they are now. Emails go out a few at a time, inside the sending hours.</p>
          <fieldset className="mt-3 space-y-2">
            <label className="flex items-start gap-2"><input type="radio" className="mt-1" checked={!existing} onChange={() => setExisting(false)} /><span><b>Only people who match from now on.</b> {reach === 1 ? "The 1 person who matches today is" : `The ${num(reach)} people who match today are`} left out.</span></label>
            <label className="flex items-start gap-2"><input type="radio" className="mt-1" checked={existing} onChange={() => setExisting(true)} /><span><b>Include {reach === 1 ? "the 1 person who matches" : `the ${num(reach)} people who match`} today</b> as well, and everyone who matches later.</span></label>
          </fieldset>
        </ConfirmDialog>
      )}
      {asking === "stop" && <ConfirmDialog title="Stop this workflow for good?" confirmLabel="Stop it" onConfirm={() => act.mutate("stop")} onCancel={() => setAsking(null)}>Everyone still in it leaves and gets no more emails from it. This can’t be undone. To pause for a while, use Pause instead.</ConfirmDialog>}
      {asking === "delete" && <ConfirmDialog title="Delete this draft?" confirmLabel="Delete" onConfirm={() => del.mutate()} onCancel={() => setAsking(null)} />}
    </Card>
  );
}

export function WorkflowsTab({ engine }: { engine: string }) {
  const qc = useQueryClient();
  const manage = useCan()("marketing.manage");
  const [open, setOpen] = useState<string | null>(null);
  const [building, setBuilding] = useState(false);
  const list = useQuery({ queryKey: ["workflows"], queryFn: () => unwrap(api.GET("/v1/admin/marketing/workflows")).then((r) => (r as unknown as { items: Workflow[] }).items), refetchInterval: 15000 });
  const segments = useQuery({ queryKey: ["segments"], queryFn: () => unwrap(api.GET("/v1/admin/marketing/segments")).then((r) => (r as unknown as { items: Pick[] }).items) });
  const copies = useQuery({ queryKey: ["copies"], queryFn: () => unwrap(api.GET("/v1/admin/marketing/copies")).then((r) => (r as unknown as { items: Pick[] }).items) });
  const starter = useMutation({
    mutationFn: () => unwrap(api.POST("/v1/admin/marketing/workflows/starter")),
    onSuccess: async (w) => { await Promise.all(["workflows", "segments", "copies"].map((k) => qc.invalidateQueries({ queryKey: [k] }))); setOpen((w as unknown as Workflow).id); },
  });
  const seg = segments.data ?? [];
  const cop = copies.data ?? [];
  if (building) return <Builder wf={null} segments={seg} copies={cop} onDone={(id) => { setBuilding(false); if (id) setOpen(id); }} />;
  if (open) return <Detail id={open} segments={seg} copies={cop} engine={engine} manage={manage} onClose={() => setOpen(null)} />;
  return (
    <>
      <ErrorBox error={list.error ?? segments.error ?? copies.error ?? starter.error} />
      <Card title="Workflows" actions={manage && <div className="flex gap-2"><Button variant="secondary" disabled={starter.isPending} onClick={() => starter.mutate()}>{starter.isPending ? "Making it…" : "Start from the welcome sequence"}</Button><Button disabled={seg.length === 0 || cop.length === 0} onClick={() => setBuilding(true)}>New workflow</Button></div>}>
        {list.isLoading ? <p aria-busy="true">Loading…</p> : list.data && list.data.length === 0 ? (
          <p className="text-sm text-muted">No workflows yet. A workflow emails people over time: for example a welcome now, a nudge after 3 days if they haven’t made a video, and a credits reminder after a week. “Start from the welcome sequence” makes exactly that as a draft you can open and change.</p>
        ) : (
          <ul className="space-y-3">{list.data?.map((w) => (
            <li key={w.id} className="flex flex-wrap items-start justify-between gap-2 rounded-xl border border-line p-3 text-sm">
              <div className="space-y-1"><p className="font-bold">{w.name} <Badge s={w.status} /></p><p className="text-muted">Who gets in: {w.trigger_segment_name} · {w.steps.filter((s) => s.type === "email").length} emails</p>{w.stats && <p className="text-xs text-muted">{num(w.stats.active)} in progress · {num(w.stats.completed)} finished · {num(w.stats.exited)} left</p>}</div>
              <Button variant="secondary" onClick={() => setOpen(w.id)}>Open</Button>
            </li>))}
          </ul>
        )}
      </Card>
    </>
  );
}
