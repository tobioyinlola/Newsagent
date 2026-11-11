import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, unwrap } from "../api/client";
import { Button, Card, ConfirmDialog, ErrorBox, inputCls, Notice } from "../components/ui";
import { ago, num } from "../lib/format";
import { useCan } from "../lib/can";
import type { Preview } from "../lib/segments";

type Variants = Record<string, { sent: number; opened: number; clicked: number }>;
type Test = { subject_b: string | null; mode: "split" | "winner"; test_percent: number; wait_hours: number; metric: "opens" | "clicks"; winner: "A" | "B" | null; decide_at: string | null };
type CampaignHours = { enabled: boolean; start: number; end: number };
type Counts = { deferred?: number; pending: number; held?: number; variants?: Variants; sent: number; skipped: number; failed: number; skipped_by_reason: Record<string, number>; opened?: number; clicked?: number };
type Campaign = { id: string; name: string; status: "draft" | "scheduled" | "sending" | "sent" | "cancelled"; segment_id: string; segment_name: string; copy_id: string; copy_name: string; copy_version: number; audience: number; send_at: string | null; started_at: string | null; finished_at: string | null; created_by: string; hours?: CampaignHours | null; test?: Test; email_b?: { subject: string }; counts?: Counts; preview?: Preview; email?: { subject: string; preheader: string; html: string } | null };
type Pick = { id: string; name: string };

const STATUS: Record<Campaign["status"], [string, string]> = { draft: ["Draft", "bg-paper"], scheduled: ["Scheduled", "bg-peach-tint"], sending: ["Sending", "bg-lilac"], sent: ["Sent", "bg-lime-tint"], cancelled: ["Cancelled", "bg-brand-red"] };
const WHY: Record<string, string> = { too_soon: "emailed too recently", opted_out: "unsubscribed", suppressed: "blocked address", account_inactive: "account closed or suspended", cancelled: "campaign cancelled", account_gone: "account gone", already_sent: "already sent", error: "error" };
const Badge = ({ s }: { s: Campaign["status"] }) => <span className={`rounded-sm px-1.5 py-0.5 text-xs font-bold ${STATUS[s][1]}`}>{STATUS[s][0]}</span>;

function Progress({ c }: { c: Campaign }) {
  const k = c.counts;
  if (!k) return null;
  const done = k.sent + k.skipped + k.failed;
  const pct = c.audience ? Math.round((done / c.audience) * 100) : 0;
  return (
    <div className="space-y-1 text-sm">
      <div className="h-2 overflow-hidden rounded-full bg-line" role="progressbar" aria-label="Campaign progress" aria-valuenow={pct} aria-valuemin={0} aria-valuemax={100}><div className="h-full bg-brand-green" style={{ width: `${pct}%` }} /></div>
      <p><b>{num(k.sent)}</b> sent · {num(k.pending + (k.held ?? 0))} waiting{(k.deferred ?? 0) > 0 ? ` (${num(k.deferred ?? 0)} for their morning)` : ""} · {num(k.skipped)} skipped · {num(k.failed)} failed (of {num(c.audience)})</p>
      {k.sent > 0 && k.opened !== undefined && <p><b>{num(k.opened)}</b> opened ({Math.round((k.opened / k.sent) * 100)}%) · <b>{num(k.clicked ?? 0)}</b> clicked the button ({Math.round(((k.clicked ?? 0) / k.sent) * 100)}%)<span className="block text-xs text-muted">Opens are approximate: some mail apps load images for everyone, others block them. Clicks are the more reliable number.</span></p>}
      {Object.keys(k.skipped_by_reason).length > 0 && <p className="text-xs text-muted">Skipped: {Object.entries(k.skipped_by_reason).map(([r, n]) => `${n} ${WHY[r] ?? r}`).join(", ")}</p>}
    </div>
  );
}

const pct = (n: number, d: number) => (d ? `${Math.round((n / d) * 100)}%` : "–");

function TestResults({ c }: { c: Campaign }) {
  const v = c.counts?.variants ?? {};
  const t = c.test;
  if (!t?.subject_b || Object.keys(v).length === 0) return null;
  return (
    <div className="space-y-2">
      <p className="font-semibold">Subject line test</p>
      <table className="w-full text-sm">
        <caption className="sr-only">Results for each subject line</caption>
        <thead><tr className="text-left text-xs text-muted"><th className="py-1">Subject</th><th>Sent</th><th>Opened</th><th>Clicked</th></tr></thead>
        <tbody>
          {(["A", "B"] as const).map((k) => (
            <tr key={k} className="border-t border-line">
              <td className="py-1.5 pr-2"><b>{k}</b> {k === "A" ? c.email?.subject : c.email_b?.subject}{t.winner === k && <span className="ml-2 rounded-sm bg-lime-tint px-1.5 py-0.5 text-xs font-bold">Winner</span>}</td>
              <td className="tabular-nums">{num(v[k]?.sent ?? 0)}</td>
              <td className="tabular-nums">{num(v[k]?.opened ?? 0)} ({pct(v[k]?.opened ?? 0, v[k]?.sent ?? 0)})</td>
              <td className="tabular-nums">{num(v[k]?.clicked ?? 0)} ({pct(v[k]?.clicked ?? 0, v[k]?.sent ?? 0)})</td>
            </tr>
          ))}
        </tbody>
      </table>
      {t.mode === "winner" && !t.winner && c.status !== "cancelled" && <p className="text-xs text-muted">{t.decide_at ? `The better subject (by ${t.metric}) goes to everyone else at ${new Date(t.decide_at).toLocaleString()}.` : "Sending the test group first; then we wait for results before choosing."}</p>}
      {t.winner && <p className="text-xs text-muted">Subject {t.winner} won on {t.metric} and went to everyone who was waiting. These numbers are the test group only.</p>}
    </div>
  );
}

function CampaignSettings({ c, onSaved }: { c: Campaign; onSaved: () => void }) {
  const t = c.test;
  const [on, setOn] = useState(!!t?.subject_b);
  const [b, setB] = useState(t?.subject_b ?? "");
  const [mode, setMode] = useState<Test["mode"]>(t?.mode ?? "split");
  const [percent, setPercent] = useState(t?.test_percent ?? 20);
  const [hours, setHours] = useState(t?.wait_hours ?? 4);
  const [metric, setMetric] = useState<Test["metric"]>(t?.metric ?? "opens");
  const [hoursOn, setHoursOn] = useState(!!c.hours?.enabled);
  const [start, setStart] = useState(c.hours?.start ?? 9);
  const [end, setEnd] = useState(c.hours?.end ?? 18);
  const save = useMutation({
    mutationFn: () => unwrap(api.PUT("/v1/admin/marketing/campaigns/{campaign_id}", { params: { path: { campaign_id: c.id } }, body: { name: c.name, segment_id: c.segment_id, copy_id: c.copy_id, subject_b: on ? b : "", ab_mode: mode, test_percent: percent, wait_hours: hours, metric, hours: hoursOn ? { enabled: true, start, end } : null } })),
    onSuccess: onSaved,
  });
  return (
    <div className="space-y-3">
    <fieldset className="space-y-2 rounded-xl border border-line p-3">
      <legend className="px-1 font-semibold">Sending hours</legend>
      <label className="flex items-center gap-2"><input type="checkbox" checked={hoursOn} onChange={(e) => setHoursOn(e.target.checked)} /> Only email people during the day where they live</label>
      {hoursOn && <div className="flex flex-wrap items-center gap-2">between <input aria-label="From hour" type="number" min={0} max={23} className={`${inputCls} !w-20`} value={start} onChange={(e) => setStart(Number(e.target.value))} /> and <input aria-label="To hour" type="number" min={1} max={24} className={`${inputCls} !w-20`} value={end} onChange={(e) => setEnd(Number(e.target.value))} /> o’clock <span className="text-xs text-muted">(by their country; Nigeria’s time if we don’t know it). Anyone outside it waits for the morning, so a big campaign can take a day or more to finish.</span></div>}
      {!hoursOn && <p className="text-xs text-muted">Off: everyone is emailed as soon as it starts, whatever the time where they live.</p>}
    </fieldset>
    <fieldset className="space-y-2 rounded-xl border border-line p-3">
      <legend className="px-1 font-semibold">Subject line test</legend>
      <label className="flex items-center gap-2"><input type="checkbox" checked={on} onChange={(e) => setOn(e.target.checked)} /> Try a second subject line</label>
      {on && (
        <div className="space-y-3">
          <p className="text-xs text-muted">A is the email’s own subject: <b>{c.email?.subject}</b></p>
          <label className="block">Subject B<input className={inputCls} value={b} maxLength={200} onChange={(e) => setB(e.target.value)} /></label>
          <label className="flex items-start gap-2"><input type="radio" className="mt-1" checked={mode === "split"} onChange={() => setMode("split")} /><span><b>Split everyone</b> half and half, then compare how they did.</span></label>
          <label className="flex items-start gap-2"><input type="radio" className="mt-1" checked={mode === "winner"} onChange={() => setMode("winner")} /><span><b>Test a few, then send the better one to the rest.</b> Needs at least 20 people and “Count opens and clicks” on.</span></label>
          {mode === "winner" && (
            <div className="flex flex-wrap items-center gap-2 pl-6">
              Test on <input aria-label="Test share" type="number" min={10} max={50} className={`${inputCls} !w-20`} value={percent} onChange={(e) => setPercent(Number(e.target.value))} />% of people, wait <input aria-label="Hours to wait" type="number" min={1} max={72} className={`${inputCls} !w-20`} value={hours} onChange={(e) => setHours(Number(e.target.value))} /> hours, then pick by
              <select aria-label="Pick the winner by" className={`${inputCls} !w-auto`} value={metric} onChange={(e) => setMetric(e.target.value as Test["metric"])}><option value="opens">opens (approximate)</option><option value="clicks">clicks</option></select>
            </div>
          )}
        </div>
      )}
    </fieldset>
    <ErrorBox error={save.error} />
    <Button variant="secondary" disabled={save.isPending || (on && !b.trim()) || (hoursOn && start >= end)} onClick={() => save.mutate()}>{save.isPending ? "Saving…" : "Save settings"}</Button>
    </div>
  );
}

function Detail({ id, manage, engine, onClose }: { id: string; manage: boolean; engine: string; onClose: () => void }) {
  const qc = useQueryClient();
  const q = useQuery({
    queryKey: ["campaign", id],
    queryFn: () => unwrap(api.GET("/v1/admin/marketing/campaigns/{campaign_id}", { params: { path: { campaign_id: id } } })) as unknown as Promise<Campaign>,
    refetchInterval: (query) => (["scheduled", "sending"].includes(query.state.data?.status ?? "") ? 5000 : false),
  });
  const [when, setWhen] = useState("");
  const [later, setLater] = useState(false);
  const [asking, setAsking] = useState<"send" | "cancel" | "delete" | null>(null);
  const refresh = async () => { setAsking(null); await qc.invalidateQueries({ queryKey: ["campaign", id] }); await qc.invalidateQueries({ queryKey: ["campaigns"] }); };
  const send = useMutation({
    mutationFn: () => unwrap(api.POST("/v1/admin/marketing/campaigns/{campaign_id}/schedule", { params: { path: { campaign_id: id } }, body: { send_at: later && when ? new Date(when).toISOString() : null, confirm_count: q.data!.preview!.reachable } })),
    onSuccess: refresh,
  });
  const cancel = useMutation({ mutationFn: () => unwrap(api.POST("/v1/admin/marketing/campaigns/{campaign_id}/cancel", { params: { path: { campaign_id: id } } })), onSuccess: refresh });
  const del = useMutation({ mutationFn: () => unwrap(api.DELETE("/v1/admin/marketing/campaigns/{campaign_id}", { params: { path: { campaign_id: id } } })), onSuccess: async () => { await qc.invalidateQueries({ queryKey: ["campaigns"] }); onClose(); } });
  const c = q.data;
  const reach = c?.preview?.reachable ?? 0;
  const canSend = manage && c?.status === "draft" && reach > 0 && engine !== "off" && (!later || when);
  return (
    <Card title={c?.name ?? "Campaign"} actions={<Button variant="secondary" onClick={onClose}>Back</Button>}>
      <ErrorBox error={q.error ?? send.error ?? cancel.error ?? del.error} />
      {!c ? <p aria-busy="true">Loading…</p> : (
        <div className="grid gap-6 lg:grid-cols-2">
          <div className="space-y-4 text-sm">
            <p><Badge s={c.status} /> <span className="ml-2 text-muted">{c.segment_name} · “{c.copy_name}” version {c.copy_version} · by {c.created_by}{c.hours?.enabled ? ` · sends ${c.hours.start}:00 to ${c.hours.end}:00 local time` : ""}</span></p>
            {c.send_at && c.status !== "draft" && <p>{c.status === "scheduled" ? "Goes out" : "Started"} {new Date(c.send_at).toLocaleString()}{c.finished_at && <> · finished {ago(c.finished_at)}</>}</p>}
            <Progress c={c} />
            <TestResults c={c} />
            {manage && c.status === "draft" && <CampaignSettings key={JSON.stringify([c.test, c.hours])} c={c} onSaved={() => void qc.invalidateQueries({ queryKey: ["campaign", id] })} />}
            {c.preview && (
              <div className="space-y-1"><p><b className="text-lg tabular-nums">{num(reach)}</b> people can be emailed{c.preview.excluded > 0 && <span className="text-muted"> ({num(c.preview.excluded)} more match but will be skipped)</span>}.</p>
                {c.preview.sample.length > 0 && <ul className="divide-y divide-line rounded-lg border border-line">{c.preview.sample.map((s) => <li key={s.user_id} className="break-all px-3 py-1.5">{s.email} <span className="text-muted">· {s.company}</span></li>)}</ul>}
                <p className="text-xs text-muted">The list is fixed again at the moment sending starts.</p></div>
            )}
            {manage && c.status === "draft" && (
              <fieldset className="space-y-2">
                <legend className="font-semibold">When</legend>
                <label className="flex items-center gap-2"><input type="radio" checked={!later} onChange={() => setLater(false)} /> Send now</label>
                <label className="flex items-center gap-2"><input type="radio" checked={later} onChange={() => setLater(true)} /> Schedule for <input aria-label="Send time" type="datetime-local" disabled={!later} className={`${inputCls} !w-auto`} value={when} onChange={(e) => setWhen(e.target.value)} /></label>
                {engine === "off" && <Notice tone="warn">Marketing email is switched off on the server (MARKETING_EMAIL), so this can’t be sent yet.</Notice>}
                {engine === "dry_run" && <Notice tone="info">Dry run: nothing will really be emailed; each send is only logged.</Notice>}
                {reach === 0 && <Notice tone="warn">Nobody in this segment can be emailed right now.</Notice>}
              </fieldset>
            )}
            <div className="flex flex-wrap gap-2">
              {manage && c.status === "draft" && <Button disabled={!canSend || send.isPending} onClick={() => setAsking("send")}>Review and send</Button>}
              {manage && c.status === "draft" && <Button variant="danger" onClick={() => setAsking("delete")}>Delete draft</Button>}
              {manage && (c.status === "scheduled" || c.status === "sending") && <Button variant="danger" onClick={() => setAsking("cancel")}>Cancel campaign</Button>}
            </div>
          </div>
          <div className="space-y-2">
            <p className="text-sm font-semibold">The email <span className="font-normal text-muted">(with example details{c.email_b ? `; subject B would read “${c.email_b.subject}”` : ""})</span></p>
            {c.email ? <><p className="rounded-lg border border-line bg-paper px-3 py-2 text-sm"><b>{c.email.subject}</b>{c.email.preheader && <span className="text-muted"> — {c.email.preheader}</span>}</p><iframe title="Email preview" sandbox="" srcDoc={c.email.html} className="h-[30rem] w-full rounded-lg border border-line bg-white" /></> : <p className="text-sm text-muted">The email isn’t available.</p>}
          </div>
        </div>
      )}
      {asking === "send" && c && <ConfirmDialog title="Send this campaign?" confirmLabel={later ? "Schedule it" : "Send now"} onConfirm={() => send.mutate()} onCancel={() => setAsking(null)}>“{c.email?.subject}” will go to <b>{num(reach)}</b> people {later && when ? `at ${new Date(when).toLocaleString()}` : "now"}, a few every minute{c.hours?.enabled ? `, only during ${c.hours.start}:00 to ${c.hours.end}:00 where each person lives (the rest wait for the morning)` : ""}. You can cancel while it is going out.</ConfirmDialog>}
      {asking === "cancel" && <ConfirmDialog title="Cancel this campaign?" confirmLabel="Cancel campaign" cancelLabel="Keep it going" onConfirm={() => cancel.mutate()} onCancel={() => setAsking(null)}>Anyone not yet emailed won’t be. Emails already sent can’t be taken back.</ConfirmDialog>}
      {asking === "delete" && <ConfirmDialog title="Delete this draft?" confirmLabel="Delete" onConfirm={() => del.mutate()} onCancel={() => setAsking(null)} />}
    </Card>
  );
}

export function CampaignsTab({ engine }: { engine: string }) {
  const qc = useQueryClient();
  const manage = useCan()("marketing.manage");
  const [open, setOpen] = useState<string | null>(null);
  const [form, setForm] = useState<{ name: string; segment_id: string; copy_id: string } | null>(null);
  const list = useQuery({ queryKey: ["campaigns"], queryFn: () => unwrap(api.GET("/v1/admin/marketing/campaigns")).then((r) => (r as unknown as { items: Campaign[] }).items), refetchInterval: 10000 });
  const segments = useQuery({ queryKey: ["segments"], queryFn: () => unwrap(api.GET("/v1/admin/marketing/segments")).then((r) => (r as unknown as { items: Pick[] }).items) });
  const copies = useQuery({ queryKey: ["copies"], queryFn: () => unwrap(api.GET("/v1/admin/marketing/copies")).then((r) => (r as unknown as { items: Pick[] }).items) });
  const create = useMutation({
    mutationFn: () => unwrap(api.POST("/v1/admin/marketing/campaigns", { body: { ...form!, ab_mode: "split", test_percent: 20, wait_hours: 4, metric: "opens" } })),
    onSuccess: async (c) => { await qc.invalidateQueries({ queryKey: ["campaigns"] }); setForm(null); setOpen((c as unknown as Campaign).id); },
  });
  if (open) return <Detail id={open} manage={manage} engine={engine} onClose={() => setOpen(null)} />;
  const missing = (segments.data?.length ?? 0) === 0 || (copies.data?.length ?? 0) === 0;
  return (
    <>
      <ErrorBox error={list.error ?? segments.error ?? copies.error} />
      {form && (
        <Card title="New campaign" actions={<Button variant="secondary" onClick={() => setForm(null)}>Cancel</Button>}>
          <div className="space-y-3">
            <label className="block text-sm font-semibold">Name<input className={inputCls} value={form.name} maxLength={120} placeholder="e.g. Nudge: no video yet" onChange={(e) => setForm({ ...form, name: e.target.value })} /></label>
            <label className="block text-sm font-semibold">Send to<select className={inputCls} value={form.segment_id} onChange={(e) => setForm({ ...form, segment_id: e.target.value })}><option value="">Choose a segment…</option>{segments.data?.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}</select></label>
            <label className="block text-sm font-semibold">Email<select className={inputCls} value={form.copy_id} onChange={(e) => setForm({ ...form, copy_id: e.target.value })}><option value="">Choose an email…</option>{copies.data?.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}</select></label>
            <ErrorBox error={create.error} />
            <Button disabled={!form.name.trim() || !form.segment_id || !form.copy_id || create.isPending} onClick={() => create.mutate()}>Create draft</Button>
            <p className="text-xs text-muted">Nothing is sent yet. Next you’ll see who it reaches and the email itself.</p>
          </div>
        </Card>
      )}
      {!form && (
        <Card title="Campaigns" actions={manage && <Button disabled={missing} onClick={() => setForm({ name: "", segment_id: "", copy_id: "" })}>New campaign</Button>}>
          {missing && !list.isLoading && <p className="mb-3 text-sm text-muted">Make at least one segment and one email copy first.</p>}
          {list.isLoading ? <p aria-busy="true">Loading…</p> : list.data && list.data.length === 0 ? <p className="text-sm text-muted">No campaigns yet. A campaign sends one email to one segment, now or at a set time.</p> : (
            <ul className="space-y-3">{list.data?.map((c) => (
              <li key={c.id} className="flex flex-wrap items-start justify-between gap-2 rounded-xl border border-line p-3 text-sm">
                <div className="space-y-1"><p className="font-bold">{c.name} <Badge s={c.status} /></p><p className="text-muted">{c.segment_name} · “{c.copy_name}” v{c.copy_version}{c.send_at && ` · ${new Date(c.send_at).toLocaleString()}`}</p>{c.counts && <p className="text-xs text-muted">{num(c.counts.sent)} of {num(c.audience)} sent</p>}</div>
                <Button variant="secondary" onClick={() => setOpen(c.id)}>Open</Button>
              </li>))}
            </ul>
          )}
        </Card>
      )}
    </>
  );
}
