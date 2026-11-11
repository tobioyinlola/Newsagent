import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { type ReactNode, useState } from "react";
import { api, unwrap } from "../api/client";
import { Button, Card, ConfirmDialog, ErrorBox, inputCls, Notice } from "../components/ui";
import { Crumbs, EmptyState, MARKETING, PageIntro, Step as FormStep, useToast } from "../components/marketingUi";
import { useUrlState } from "../lib/urlState";
import { num } from "../lib/format";
import { useCan } from "../lib/can";
import type { Preview } from "../lib/segments";

type Step = { type: "email"; copy_id: string; copy_version?: number; only_if_segment_id?: string | null } | { type: "wait"; days: number; hours: number } | { type: "branch"; segment_id: string; yes_to?: number | null; no_to?: number | null } | { type: "end" };
type Hours = { enabled: boolean; start: number; end: number };
type Stats = { active: number; completed: number; exited: number; exits: Record<string, number>; sent_by_step: Record<string, number>; opened_by_step?: Record<string, number>; clicked_by_step?: Record<string, number> };
type Workflow = { id: string; name: string; status: "draft" | "active" | "paused" | "stopped"; trigger_segment_id: string; trigger_segment_name: string; goal_segment_id: string | null; goal_segment_name: string; steps: Step[]; hours: Hours; reentry_days?: number | null; stats?: Stats; preview?: Preview };
type Pick = { id: string; name: string };

const STATUS: Record<Workflow["status"], [string, string, string]> = {
  draft: ["Draft", "bg-paper", "Not running yet. Check the steps, then turn it on."],
  active: ["On", "bg-lime-tint", "Running. People join as they match the segment, and move along on their own."],
  paused: ["Paused", "bg-peach-tint", "Frozen. Nobody gets an email and nobody moves on until you resume it."],
  stopped: ["Stopped", "bg-brand-red", "Ended for good. Everyone who was in it has left."],
};
const EXIT: Record<string, string> = { goal_reached: "reached the goal", existing_at_start: "were already members when it was turned on", opted_out: "unsubscribed", suppressed: "had a blocked address", account_inactive: "closed or suspended", account_gone: "account gone", workflow_stopped: "left when it was stopped" };
const Badge = ({ s }: { s: Workflow["status"] }) => <span className={`rounded-sm px-1.5 py-0.5 text-xs font-bold ${STATUS[s][1]}`}>{STATUS[s][0]}</span>;
const DEFAULT_HOURS: Hours = { enabled: true, start: 9, end: 18 };
const waitText = (s: { days: number; hours: number }) => [s.days && `${s.days} day${s.days === 1 ? "" : "s"}`, s.hours && `${s.hours} hour${s.hours === 1 ? "" : "s"}`].filter(Boolean).join(" ");
const ICON: Record<Step["type"], string> = { email: "✉", wait: "⏱", branch: "⑂", end: "■" };
const KIND: Record<Step["type"], string> = { email: "Send an email", wait: "Wait", branch: "Branch (if / else)", end: "Finish here" };

// Branch targets are step numbers, so they must follow the steps when one is moved or removed.
function retarget(steps: Step[], map: (old: number) => number | null): Step[] {
  const fix = (t?: number | null) => (t == null ? null : map(t));
  return steps.map((s) => (s.type === "branch" ? { ...s, yes_to: fix(s.yes_to), no_to: fix(s.no_to) } : s));
}
const target = (t: number | null | undefined, at: number) => (t != null && t > at ? t : null); // only forward jumps are allowed; anything else means "finish"

// A number in a circle with a line down to the next one: the steps read as a journey, top to bottom.
function Timeline({ children }: { children: ReactNode[] }) {
  return <ol className="relative space-y-3 before:absolute before:bottom-6 before:left-[0.95rem] before:top-6 before:w-px before:bg-line">{children}</ol>;
}
function Node({ n, type, children, actions }: { n: number; type: Step["type"]; children: ReactNode; actions?: ReactNode }) {
  return (
    <li className="relative flex gap-3">
      <span aria-hidden="true" title={KIND[type]} className="z-10 flex h-8 w-8 shrink-0 items-center justify-center rounded-full border border-ink bg-white text-sm font-bold">{ICON[type]}</span>
      <div className="min-w-0 flex-1 rounded-xl border border-line bg-white p-3 text-sm">
        <div className="flex flex-wrap items-start justify-between gap-2"><p className="font-bold"><span className="text-muted">Step {n} · </span>{KIND[type]}</p>{actions}</div>
        <div className="mt-2 space-y-2">{children}</div>
      </div>
    </li>
  );
}

// What happens, and how many people it has reached, step by step.
function Journey({ w, copyName, segName }: { w: Workflow; copyName: (id: string) => string; segName: (id: string) => string }) {
  const st = w.stats;
  return (
    <Timeline>
      {w.steps.map((s, i) => (
        <Node key={i} n={i + 1} type={s.type}>
          {s.type === "wait" && <p>Wait <b>{waitText(s)}</b>, then carry on.</p>}
          {s.type === "end" && <p className="text-muted">Anyone who gets here is finished and leaves the workflow.</p>}
          {s.type === "branch" && <p>If they’re in <b>“{segName(s.segment_id)}”</b>: {s.yes_to != null ? <>go to <b>step {s.yes_to + 1}</b></> : "finish"}. Otherwise: {s.no_to != null ? <>go to <b>step {s.no_to + 1}</b></> : "finish"}.</p>}
          {s.type === "email" && (
            <>
              <p><b>“{copyName(s.copy_id)}”</b>{s.copy_version ? <span className="text-muted"> (version {s.copy_version})</span> : ""}</p>
              {s.only_if_segment_id && <p className="text-muted">Only if they’re in “{segName(s.only_if_segment_id)}”. Everyone else skips this email and carries on.</p>}
              {st && (st.sent_by_step[String(i)] ?? 0) > 0 && <p className="text-xs text-muted"><b className="text-ink">{num(st.sent_by_step[String(i)] ?? 0)}</b> sent · {num(st.opened_by_step?.[String(i)] ?? 0)} opened · {num(st.clicked_by_step?.[String(i)] ?? 0)} clicked</p>}
            </>
          )}
        </Node>
      ))}
    </Timeline>
  );
}

function Summary({ w }: { w: Workflow }) {
  return (
    <ul className="list-disc space-y-1 pl-5 text-sm text-muted">
      <li>Everyone in <b className="text-ink">“{w.trigger_segment_name}”</b> gets it, as soon as they match.</li>
      {w.goal_segment_name && <li>It stops early for anyone who joins <b className="text-ink">“{w.goal_segment_name}”</b> (the goal), so they don’t keep getting emails.</li>}
      <li>{w.hours.enabled ? <>Emails only go out between <b className="text-ink">{w.hours.start}:00 and {w.hours.end}:00</b> where the person lives.</> : "Emails can go out at any hour."}</li>
      <li>{w.reentry_days ? <>People can go through it again after <b className="text-ink">{w.reentry_days} days</b>, if they match again.</> : "Everyone goes through it once."}</li>
    </ul>
  );
}

function Builder({ wf, segments, copies, onDone }: { wf: Workflow | null; segments: Pick[]; copies: Pick[]; onDone: (id?: string) => void }) {
  const qc = useQueryClient();
  const toast = useToast();
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
    onSuccess: async (r) => { await qc.invalidateQueries({ queryKey: ["workflows"] }); await qc.invalidateQueries({ queryKey: ["workflow"] }); toast("Draft saved. Turn it on when you’re ready."); onDone((r as unknown as Workflow).id); },
  });
  const problems = [
    !name.trim() && "Give it a name.",
    !trigger && "Choose who gets in.",
    steps.some((s) => s.type === "email" && !s.copy_id) && "Choose an email for every email step.",
    steps.some((s) => s.type === "wait" && s.days + s.hours <= 0) && "Every wait needs some time.",
    steps.some((s) => s.type === "branch" && !s.segment_id) && "Choose a segment for every branch.",
    hours.enabled && hours.start >= hours.end && "The sending hours must start before they end.",
  ].filter(Boolean) as string[];
  return (
    <div className="space-y-4">
      <Crumbs trail={[["Workflows", `${MARKETING}/workflows`], [wf ? `Edit “${wf.name}”` : "New workflow"]]} />
      <Card>
        <div className="space-y-7 text-sm">
          <FormStep n={1} title="Name it and choose who gets in">
            <label className="block font-semibold">Name<input className={inputCls} value={name} maxLength={120} placeholder="e.g. Welcome sequence" onChange={(e) => setName(e.target.value)} /></label>
            <label className="block font-semibold">Who gets in<select className={inputCls} value={trigger} onChange={(e) => setTrigger(e.target.value)}><option value="">Choose a segment…</option>{segments.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}</select><span className="mt-1 block text-xs font-normal text-muted">Anyone who matches this segment joins the workflow, now or later. For example “Joined in the last day” gets every new sign-up as they arrive.</span></label>
          </FormStep>
          <FormStep n={2} title="Decide what happens" hint="Steps run top to bottom for each person. Add emails and waits, and move them around.">
            <Timeline>
              {steps.map((s, i) => (
                <Node key={i} n={i + 1} type={s.type} actions={
                  <div className="flex gap-1.5">
                    <Button variant="secondary" type="button" aria-label={`Move step ${i + 1} up`} disabled={i === 0} onClick={() => move(i, -1)}>↑</Button>
                    <Button variant="secondary" type="button" aria-label={`Move step ${i + 1} down`} disabled={i === steps.length - 1} onClick={() => move(i, 1)}>↓</Button>
                    <Button variant="secondary" type="button" aria-label={`Remove step ${i + 1}`} onClick={() => remove(i)}>Remove</Button>
                  </div>}>
                  {s.type === "email" && (
                    <div className="grid gap-2 sm:grid-cols-2">
                      <label className="block">Which email?<select className={inputCls} value={s.copy_id} onChange={(e) => patch(i, { copy_id: e.target.value })}><option value="">Choose an email…</option>{copies.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</select></label>
                      <label className="block">Only send it to people in… <span className="text-muted">(optional)</span><select className={inputCls} value={s.only_if_segment_id ?? ""} onChange={(e) => patch(i, { only_if_segment_id: e.target.value || null })}><option value="">Everyone (don’t filter)</option>{segments.map((g) => <option key={g.id} value={g.id}>{g.name}</option>)}</select></label>
                    </div>
                  )}
                  {s.type === "wait" && <div className="flex flex-wrap items-center gap-2">Wait <input aria-label="Days" type="number" min={0} max={90} className={`${inputCls} !w-20`} value={s.days} onChange={(e) => patch(i, { days: Number(e.target.value) })} /> days and <input aria-label="Hours" type="number" min={0} max={23} className={`${inputCls} !w-20`} value={s.hours} onChange={(e) => patch(i, { hours: Number(e.target.value) })} /> hours, then carry on.</div>}
                  {s.type === "end" && <p className="text-muted">Anyone who gets here leaves the workflow as finished. Use it at the end of one path so people don’t run on into another.</p>}
                  {s.type === "branch" && (
                    <div className="space-y-2">
                      <label className="block">If they’re in<select className={inputCls} value={s.segment_id} onChange={(e) => patch(i, { segment_id: e.target.value })}><option value="">Choose a segment…</option>{segments.map((g) => <option key={g.id} value={g.id}>{g.name}</option>)}</select></label>
                      <div className="grid gap-2 sm:grid-cols-2">
                        {([["yes_to", "…then go to"], ["no_to", "…if not, go to"]] as const).map(([k, text]) => (
                          <label key={k} className="block">{text}<select aria-label={k === "yes_to" ? `Step ${i + 1} if in the group` : `Step ${i + 1} if not in the group`} className={inputCls} value={String(target(s[k], i) ?? "")} onChange={(e) => patch(i, { [k]: e.target.value === "" ? null : Number(e.target.value) } as Partial<Step>)}><option value="">Finish</option>{steps.map((t, n) => (n > i ? <option key={n} value={n}>{label(t, n)}</option> : null))}</select></label>
                        ))}
                      </div>
                      <p className="text-xs text-muted">Example: “If they’re in <i>Has made a video</i>, go to the thank-you email; if not, go to the reminder.” A branch can only jump forward, so a workflow can never loop.</p>
                    </div>
                  )}
                </Node>
              ))}
            </Timeline>
            <div className="flex flex-wrap gap-2" role="group" aria-label="Add a step">
              <Button type="button" variant="secondary" onClick={() => setSteps([...steps, { type: "email", copy_id: "" }])}>+ Email</Button>
              <Button type="button" variant="secondary" onClick={() => setSteps([...steps, { type: "wait", days: 1, hours: 0 }])}>+ Wait</Button>
              <Button type="button" variant="secondary" onClick={() => setSteps([...steps, { type: "branch", segment_id: "", yes_to: null, no_to: null }])}>+ Branch (if / else)</Button>
              <Button type="button" variant="secondary" onClick={() => setSteps([...steps, { type: "end" }])}>+ Finish</Button>
            </div>
          </FormStep>
          <FormStep n={3} title="Stop it early when they’ve done what you wanted" hint="Optional. Pick a segment that means “success”, like people who have bought credits.">
            <label className="block font-semibold">Goal<select className={inputCls} value={goal} onChange={(e) => setGoal(e.target.value)}><option value="">No goal: everyone finishes the whole workflow</option>{segments.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}</select><span className="mt-1 block text-xs font-normal text-muted">Anyone who matches this leaves the workflow, so they stop getting emails once they’ve acted.</span></label>
          </FormStep>
          <FormStep n={4} title="Choose when emails can go out">
            <label className="flex items-center gap-2"><input type="checkbox" checked={hours.enabled} onChange={(e) => setHours({ ...hours, enabled: e.target.checked })} /> Only email during the day where the person lives</label>
            {hours.enabled && <div className="flex flex-wrap items-center gap-2">between <input aria-label="From hour" type="number" min={0} max={23} className={`${inputCls} !w-20`} value={hours.start} onChange={(e) => setHours({ ...hours, start: Number(e.target.value) })} /> and <input aria-label="To hour" type="number" min={1} max={24} className={`${inputCls} !w-20`} value={hours.end} onChange={(e) => setHours({ ...hours, end: Number(e.target.value) })} /> o’clock <span className="text-xs text-muted">(by their country; Nigeria’s time if we don’t know it)</span></div>}
          </FormStep>
          <FormStep n={5} title="Can people go through it again?">
            <label className="flex items-center gap-2"><input type="checkbox" checked={again} onChange={(e) => setAgain(e.target.checked)} /> Yes, let people go through it again</label>
            {again ? <div className="flex flex-wrap items-center gap-2">once they have finished, and at least <input aria-label="Days before re-entry" type="number" min={7} max={365} className={`${inputCls} !w-24`} value={days} onChange={(e) => setDays(Number(e.target.value))} /> days have passed, if they match “who gets in” again.</div> : <p className="text-xs text-muted">Off: everyone goes through it at most once.</p>}
          </FormStep>
          {problems.length > 0 && <Notice tone="info"><p className="font-semibold">Before you can save:</p><ul className="list-disc pl-5">{problems.map((p) => <li key={p}>{p}</li>)}</ul></Notice>}
          <ErrorBox error={save.error} />
          <div className="flex flex-wrap gap-2">
            <Button disabled={problems.length > 0 || save.isPending} onClick={() => save.mutate()}>{save.isPending ? "Saving…" : "Save draft"}</Button>
            <Button variant="secondary" onClick={() => onDone(wf?.id)}>Cancel</Button>
          </div>
        </div>
      </Card>
    </div>
  );
}

function Detail({ id, segments, copies, engine, manage }: { id: string; segments: Pick[]; copies: Pick[]; engine: string; manage: boolean }) {
  const qc = useQueryClient();
  const toast = useToast();
  const url = useUrlState();
  const q = useQuery({
    queryKey: ["workflow", id],
    queryFn: () => unwrap(api.GET("/v1/admin/marketing/workflows/{workflow_id}", { params: { path: { workflow_id: id } } })) as unknown as Promise<Workflow>,
    refetchInterval: (query) => (query.state.data?.status === "active" ? 10000 : false),
  });
  const [asking, setAsking] = useState<"on" | "stop" | "delete" | null>(null);
  const [existing, setExisting] = useState(false);
  const refresh = async () => { setAsking(null); await qc.invalidateQueries({ queryKey: ["workflow", id] }); await qc.invalidateQueries({ queryKey: ["workflows"] }); };
  const w = q.data;
  const reach = w?.preview?.reachable ?? 0;
  const act = useMutation({
    mutationFn: (a: "pause" | "resume" | "stop") => unwrap(api.POST("/v1/admin/marketing/workflows/{workflow_id}/{action}", { params: { path: { workflow_id: id, action: a } } })),
    onSuccess: async (_r, a) => { await refresh(); toast(a === "pause" ? "Workflow paused." : a === "resume" ? "Workflow resumed." : "Workflow stopped."); },
  });
  const on = useMutation({
    mutationFn: () => unwrap(api.POST("/v1/admin/marketing/workflows/{workflow_id}/activate", { params: { path: { workflow_id: id } }, body: { include_existing: existing, confirm_count: reach } })),
    onSuccess: async () => { await refresh(); toast("Workflow is on."); },
  });
  const del = useMutation({ mutationFn: () => unwrap(api.DELETE("/v1/admin/marketing/workflows/{workflow_id}", { params: { path: { workflow_id: id } } })), onSuccess: async () => { await qc.invalidateQueries({ queryKey: ["workflows"] }); toast("Draft deleted."); url.set({ open: null }); } });
  const copyName = (cid: string) => copies.find((c) => c.id === cid)?.name ?? "(deleted email)";
  const segName = (sid: string) => segments.find((s) => s.id === sid)?.name ?? "(deleted segment)";
  if (url.get("edit") === "1" && w) return <Builder wf={w} segments={segments} copies={copies} onDone={() => { url.set({ edit: null }); void refresh(); }} />;
  return (
    <div className="space-y-4">
      <Crumbs trail={[["Workflows", `${MARKETING}/workflows`], [w?.name ?? "Workflow"]]} />
      <ErrorBox error={q.error ?? act.error ?? on.error ?? del.error} />
      {!w ? <p aria-busy="true">Loading…</p> : (
        <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,22rem)]">
          <Card title="What happens">
            <div className="space-y-4">
              <p className="flex flex-wrap items-center gap-2 text-sm"><Badge s={w.status} /><span className="text-muted">{STATUS[w.status][2]}</span></p>
              <Journey w={w} copyName={copyName} segName={segName} />
            </div>
          </Card>
          <div className="space-y-4 lg:sticky lg:top-4">
            <Card title="In short"><Summary w={w} /></Card>
            {w.stats && w.status !== "draft" && (
              <Card title="Who’s in it">
                <p className="text-sm"><b className="text-lg tabular-nums">{num(w.stats.active)}</b> in progress · <b>{num(w.stats.completed)}</b> finished · <b>{num(w.stats.exited)}</b> left</p>
                {Object.keys(w.stats.exits).length > 0 && <ul className="mt-2 list-disc space-y-0.5 pl-5 text-xs text-muted">{Object.entries(w.stats.exits).map(([r, n]) => <li key={r}>{num(n)} {EXIT[r] ?? r}</li>)}</ul>}
              </Card>
            )}
            {w.status === "draft" && (
              <Card title="Ready to start?">
                <div className="space-y-3 text-sm">
                  {w.preview && <p><b className="text-lg tabular-nums">{num(reach)}</b> {reach === 1 ? "person matches" : "people match"} “{w.trigger_segment_name}” and can be emailed right now.</p>}
                  {engine === "off" && <Notice tone="warn">Marketing email is switched off on the server, so this can’t be turned on yet.</Notice>}
                  {engine === "dry_run" && <Notice tone="info">Test mode: nothing will really be emailed; each send is only recorded.</Notice>}
                  {manage && <div className="flex flex-wrap gap-2"><Button disabled={engine === "off" || on.isPending} onClick={() => setAsking("on")}>Turn on…</Button><Button variant="secondary" onClick={() => url.set({ edit: "1" })}>Edit steps</Button><Button variant="danger" onClick={() => setAsking("delete")}>Delete draft</Button></div>}
                </div>
              </Card>
            )}
            {manage && (w.status === "active" || w.status === "paused") && (
              <Card title="Controls">
                <div className="space-y-3 text-sm">
                  <div className="flex flex-wrap gap-2">
                    {w.status === "active" && <Button variant="secondary" disabled={act.isPending} onClick={() => act.mutate("pause")}>Pause</Button>}
                    {w.status === "paused" && <Button disabled={act.isPending} onClick={() => act.mutate("resume")}>Resume</Button>}
                    <Button variant="danger" onClick={() => setAsking("stop")}>Stop for good</Button>
                  </div>
                  <p className="text-xs text-muted">Pause is temporary: everyone stays where they are. Stop is permanent. Steps can’t be edited while it’s running, so to change them, stop it and make a new one.</p>
                </div>
              </Card>
            )}
          </div>
        </div>
      )}
      {asking === "on" && w && (
        <ConfirmDialog title="Turn this workflow on?" confirmLabel="Turn on" onConfirm={() => on.mutate()} onCancel={() => setAsking(null)}>
          <p>The words and rules are fixed as they are now. Emails go out a few at a time{w.hours.enabled ? `, between ${w.hours.start}:00 and ${w.hours.end}:00 where each person lives` : ""}.</p>
          <fieldset className="mt-3 space-y-2">
            <legend className="font-semibold">What about people who already match today?</legend>
            <label className="flex items-start gap-2"><input type="radio" className="mt-1" checked={!existing} onChange={() => setExisting(false)} /><span><b>Leave them out.</b> {reach === 1 ? "The 1 person who matches today is" : `The ${num(reach)} people who match today are`} skipped. Only people who match from now on go through it.</span></label>
            <label className="flex items-start gap-2"><input type="radio" className="mt-1" checked={existing} onChange={() => setExisting(true)} /><span><b>Include them.</b> {reach === 1 ? "The 1 person who matches" : `The ${num(reach)} people who match`} today go through it too, as well as everyone who matches later.</span></label>
          </fieldset>
        </ConfirmDialog>
      )}
      {asking === "stop" && <ConfirmDialog title="Stop this workflow for good?" confirmLabel="Stop it" onConfirm={() => act.mutate("stop")} onCancel={() => setAsking(null)}>Everyone still in it leaves and gets no more emails from it. This can’t be undone. To pause for a while, use Pause instead.</ConfirmDialog>}
      {asking === "delete" && <ConfirmDialog title="Delete this draft?" confirmLabel="Delete" onConfirm={() => del.mutate()} onCancel={() => setAsking(null)}>It has never run, so nothing is lost except this draft.</ConfirmDialog>}
    </div>
  );
}

export function WorkflowsTab({ engine }: { engine: string }) {
  const qc = useQueryClient();
  const toast = useToast();
  const manage = useCan()("marketing.manage");
  const url = useUrlState();
  const open = url.get("open");
  const building = url.get("new") === "1";
  const list = useQuery({ queryKey: ["workflows"], queryFn: () => unwrap(api.GET("/v1/admin/marketing/workflows")).then((r) => (r as unknown as { items: Workflow[] }).items), refetchInterval: 15000 });
  const segments = useQuery({ queryKey: ["segments"], queryFn: () => unwrap(api.GET("/v1/admin/marketing/segments")).then((r) => (r as unknown as { items: Pick[] }).items) });
  const copies = useQuery({ queryKey: ["copies"], queryFn: () => unwrap(api.GET("/v1/admin/marketing/copies")).then((r) => (r as unknown as { items: Pick[] }).items) });
  const starter = useMutation({
    mutationFn: () => unwrap(api.POST("/v1/admin/marketing/workflows/starter")),
    onSuccess: async (w) => { await Promise.all(["workflows", "segments", "copies"].map((k) => qc.invalidateQueries({ queryKey: [k] }))); toast("Welcome sequence created as a draft. Look it over, then turn it on."); url.set({ open: (w as unknown as Workflow).id }); },
  });
  const seg = segments.data ?? [];
  const cop = copies.data ?? [];
  if (building) return <Builder wf={null} segments={seg} copies={cop} onDone={(id) => url.set({ new: null, ...(id ? { open: id } : {}) })} />;
  if (open) return <Detail id={open} segments={seg} copies={cop} engine={engine} manage={manage} />;
  const noSetup = seg.length === 0 || cop.length === 0;
  return (
    <div className="space-y-5">
      <PageIntro
        title="Workflows"
        how={["Choose who gets in: anyone who matches a segment joins, now or later.", "Add the steps: send an email, wait a few days, send another. You can send different emails to different people with a branch.", "Optionally set a goal (like “bought credits”). Anyone who reaches it leaves, so nobody keeps getting emails they no longer need.", "Turn it on. It runs by itself, inside the sending hours, and you can pause it any time."]}
        actions={manage && <Button variant="secondary" disabled={noSetup} onClick={() => url.set({ new: "1" })}>New workflow</Button>}
      >A workflow emails people over time, on its own. For example: a welcome today, a nudge in 3 days if they haven’t made a video, and a reminder after a week.</PageIntro>
      <ErrorBox error={list.error ?? segments.error ?? copies.error ?? starter.error} />
      {list.isLoading ? <p aria-busy="true">Loading…</p> : list.data && list.data.length === 0 ? (
        <Card>
          <EmptyState title="Start with a ready-made welcome sequence" actions={manage && <Button disabled={starter.isPending} onClick={() => starter.mutate()}>{starter.isPending ? "Making it…" : "Create the welcome sequence"}</Button>}>
            It welcomes new sign-ups, nudges anyone who hasn’t made a video after 3 days, and reminds people about credits after a week. It stops for anyone who buys credits. You can change every part of it before turning it on.
          </EmptyState>
          {manage && !noSetup && <p className="mt-4 text-center text-sm text-muted">Or <button type="button" className="font-semibold underline" onClick={() => url.set({ new: "1" })}>build your own from scratch</button>.</p>}
        </Card>
      ) : (
        <>
          <ul className="space-y-3">{list.data?.map((w) => (
            <li key={w.id} className="rounded-xl border border-line bg-white p-4 text-sm shadow-sm">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0 space-y-1"><p className="text-base font-bold">{w.name} <Badge s={w.status} /></p><p className="text-muted">Who gets in: {w.trigger_segment_name} · {w.steps.filter((s) => s.type === "email").length} emails</p>{w.stats && <p className="text-xs text-muted">{num(w.stats.active)} in progress · {num(w.stats.completed)} finished · {num(w.stats.exited)} left</p>}</div>
                <Button variant="secondary" onClick={() => url.set({ open: w.id })}>{w.status === "draft" ? "Open and finish" : "See how it’s going"}</Button>
              </div>
            </li>))}
          </ul>
          {manage && !list.data?.some((w) => w.name === "Welcome sequence") && <p className="text-sm text-muted">Want a head start? <button type="button" className="font-semibold underline" disabled={starter.isPending} onClick={() => starter.mutate()}>Create the welcome sequence</button>.</p>}
        </>
      )}
    </div>
  );
}
