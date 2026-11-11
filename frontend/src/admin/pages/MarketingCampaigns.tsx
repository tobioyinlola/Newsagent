import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { Link } from "react-router-dom";
import { api, unwrap } from "../api/client";
import { Button, Card, ConfirmDialog, ErrorBox, inputCls } from "../components/ui";
import { Check, Crumbs, EmptyState, MARKETING, PageIntro, Step, useToast } from "../components/marketingUi";
import { useUrlState } from "../lib/urlState";
import { ago, num } from "../lib/format";
import { useCan } from "../lib/can";
import { describeRules, type FieldDef, type Preview, type Rules } from "../lib/segments";

type Variants = Record<string, { sent: number; opened: number; clicked: number }>;
type Test = { subject_b: string | null; mode: "split" | "winner"; test_percent: number; wait_hours: number; metric: "opens" | "clicks"; winner: "A" | "B" | null; decide_at: string | null };
type CampaignHours = { enabled: boolean; start: number; end: number };
type Counts = { deferred?: number; pending: number; held?: number; variants?: Variants; sent: number; skipped: number; failed: number; skipped_by_reason: Record<string, number>; opened?: number; clicked?: number };
type Campaign = { id: string; name: string; status: "draft" | "scheduled" | "sending" | "sent" | "cancelled"; segment_id: string; segment_name: string; copy_id: string; copy_name: string; copy_version: number; audience: number; send_at: string | null; started_at: string | null; finished_at: string | null; created_by: string; hours?: CampaignHours | null; test?: Test; email_b?: { subject: string }; counts?: Counts; preview?: Preview; email?: { subject: string; preheader: string; html: string } | null };
type Pick = { id: string; name: string };
type SegmentPick = Pick & { rules: Rules };

const STATUS: Record<Campaign["status"], [string, string]> = { draft: ["Draft", "bg-paper"], scheduled: ["Scheduled", "bg-peach-tint"], sending: ["Sending", "bg-lilac"], sent: ["Sent", "bg-lime-tint"], cancelled: ["Cancelled", "bg-brand-red"] };
const SAYS: Record<Campaign["status"], string> = { draft: "Not sent yet. Check it over, then send it.", scheduled: "Waiting for its send time.", sending: "Going out now, a few every minute.", sent: "Finished.", cancelled: "Stopped. Anyone not yet emailed won’t be." };
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


function Detail({ id, manage, engine }: { id: string; manage: boolean; engine: string }) {
  const qc = useQueryClient();
  const toast = useToast();
  const url = useUrlState();
  const q = useQuery({
    queryKey: ["campaign", id],
    queryFn: () => unwrap(api.GET("/v1/admin/marketing/campaigns/{campaign_id}", { params: { path: { campaign_id: id } } })) as unknown as Promise<Campaign>,
    refetchInterval: (query) => (["scheduled", "sending"].includes(query.state.data?.status ?? "") ? 5000 : false),
  });
  const [when, setWhen] = useState("");
  const [later, setLater] = useState(false);
  const [asking, setAsking] = useState<"send" | "cancel" | "delete" | null>(null);
  const [tested, setTested] = useState<string | null>(null);
  const refresh = async () => { setAsking(null); await qc.invalidateQueries({ queryKey: ["campaign", id] }); await qc.invalidateQueries({ queryKey: ["campaigns"] }); };
  const send = useMutation({
    mutationFn: () => unwrap(api.POST("/v1/admin/marketing/campaigns/{campaign_id}/schedule", { params: { path: { campaign_id: id } }, body: { send_at: later && when ? new Date(when).toISOString() : null, confirm_count: q.data!.preview!.reachable } })),
    onSuccess: async () => { await refresh(); toast(later ? "Campaign scheduled." : "Campaign is going out now."); },
  });
  const cancel = useMutation({ mutationFn: () => unwrap(api.POST("/v1/admin/marketing/campaigns/{campaign_id}/cancel", { params: { path: { campaign_id: id } } })), onSuccess: async () => { await refresh(); toast("Campaign cancelled."); } });
  const del = useMutation({ mutationFn: () => unwrap(api.DELETE("/v1/admin/marketing/campaigns/{campaign_id}", { params: { path: { campaign_id: id } } })), onSuccess: async () => { await qc.invalidateQueries({ queryKey: ["campaigns"] }); toast("Draft deleted."); url.set({ open: null }); } });
  const test = useMutation({
    mutationFn: (variant: "A" | "B") => unwrap(api.POST("/v1/admin/marketing/campaigns/{campaign_id}/test", { params: { path: { campaign_id: id } }, body: { variant } })),
    onSuccess: (r) => setTested((r as unknown as { sent_to: string }).sent_to),
  });
  const c = q.data;
  const reach = c?.preview?.reachable ?? 0;
  const draft = c?.status === "draft";
  const canSend = manage && draft && reach > 0 && engine !== "off" && (!later || !!when);
  const options = [c?.hours?.enabled && "sending hours", c?.test?.subject_b && "subject-line test"].filter(Boolean).join(" and ");
  return (
    <div className="space-y-4">
      <Crumbs trail={[["Campaigns", `${MARKETING}/campaigns`], [c?.name ?? "Campaign"]]} />
      <ErrorBox error={q.error ?? send.error ?? cancel.error ?? del.error ?? test.error} />
      {!c ? <p aria-busy="true">Loading…</p> : (
        <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,26rem)]">
          <div className="space-y-4">
            <Card>
              <div className="space-y-3 text-sm">
                <p className="flex flex-wrap items-center gap-2"><Badge s={c.status} /><span className="text-muted">{SAYS[c.status]}</span></p>
                <p>Sends <b>“{c.copy_name}”</b> (version {c.copy_version}) to <b>{c.segment_name}</b>.</p>
                {c.send_at && !draft && <p>{c.status === "scheduled" ? "Goes out" : "Started"} {new Date(c.send_at).toLocaleString()}{c.finished_at && <> · finished {ago(c.finished_at)}</>}</p>}
                {c.hours?.enabled && <p className="text-muted">Only emails people between {c.hours.start}:00 and {c.hours.end}:00 where they live. The rest wait for the morning.</p>}
                {!draft && <Progress c={c} />}
                <TestResults c={c} />
              </div>
            </Card>
            {draft && (
              <Card title="Before you send">
                <ul className="divide-y divide-line">
                  <Check done={reach > 0} action={<Link className="text-sm font-semibold underline" to={`${MARKETING}/segments`}>Check the segment</Link>}>
                    {reach > 0 ? <><b>{num(reach)}</b> {reach === 1 ? "person" : "people"} can be emailed{c.preview && c.preview.excluded > 0 ? ` (${num(c.preview.excluded)} more match but will be skipped: unsubscribed, bounced or suspended)` : ""}. The list is fixed again at the moment sending starts.</> : "Nobody in this segment can be emailed right now."}
                  </Check>
                  <Check done>The email is “{c.copy_name}”. Check how it looks on the right.</Check>
                  <Check done={tested !== null} action={manage && <div className="flex gap-2"><Button variant="secondary" disabled={test.isPending} onClick={() => test.mutate("A")}>{test.isPending ? "Sending…" : "Send me a test"}</Button>{c.test?.subject_b && <Button variant="secondary" disabled={test.isPending} onClick={() => test.mutate("B")}>Test subject B</Button>}</div>}>
                    {tested !== null ? <>Test sent to {tested}. Check your inbox (and spam).</> : <>Recommended: send yourself a test to see it in a real inbox. Nobody else gets it.</>}
                  </Check>
                  <Check done={engine !== "off"}>
                    {engine === "off" ? "Marketing email is switched off on the server, so nothing can be sent yet." : engine === "dry_run" ? "Test mode is on: sending is recorded in Activity but no email really goes out." : "Sending is switched on."}
                  </Check>
                </ul>
              </Card>
            )}
            {draft && manage && (
              <Card title="When should it go out?">
                <div className="space-y-3 text-sm">
                  <label className="flex items-center gap-2"><input type="radio" checked={!later} onChange={() => setLater(false)} /> <span><b>Now.</b> It starts within a minute.</span></label>
                  <label className="flex flex-wrap items-center gap-2"><input type="radio" checked={later} onChange={() => setLater(true)} /> <b>Later:</b> <input aria-label="Send time" type="datetime-local" disabled={!later} className={`${inputCls} !w-auto`} value={when} onChange={(e) => setWhen(e.target.value)} /></label>
                  <div className="flex flex-wrap gap-2 pt-1">
                    <Button disabled={!canSend || send.isPending} onClick={() => setAsking("send")}>Review and send</Button>
                    <Button variant="danger" onClick={() => setAsking("delete")}>Delete this draft</Button>
                  </div>
                  {!canSend && <p className="text-xs text-muted">{reach === 0 ? "You need at least one person who can be emailed." : engine === "off" ? "Sending is switched off on the server." : later && !when ? "Choose a time." : ""}</p>}
                </div>
              </Card>
            )}
            {draft && manage && (
              <details className="rounded-2xl border border-line bg-white p-4 shadow-sm">
                <summary className="cursor-pointer text-sm font-semibold">More options: sending hours and subject-line test{options ? ` (on: ${options})` : ""}</summary>
                <div className="mt-3"><CampaignSettings key={JSON.stringify([c.test, c.hours])} c={c} onSaved={() => { void qc.invalidateQueries({ queryKey: ["campaign", id] }); toast("Options saved."); }} /></div>
              </details>
            )}
            {manage && (c.status === "scheduled" || c.status === "sending") && <div><Button variant="danger" onClick={() => setAsking("cancel")}>Cancel this campaign</Button></div>}
          </div>
          <aside aria-label="The email" className="space-y-2 lg:sticky lg:top-4">
            <Card title="The email">
              {c.email ? (
                <div className="space-y-2">
                  <p className="rounded-lg border border-line bg-paper px-3 py-2 text-sm"><b>{c.email.subject}</b>{c.email.preheader && <span className="text-muted"> — {c.email.preheader}</span>}</p>
                  {c.email_b && <p className="rounded-lg border border-dashed border-line px-3 py-2 text-sm"><span className="text-xs font-bold text-muted">SUBJECT B: </span>{c.email_b.subject}</p>}
                  <iframe title="Email preview" sandbox="" srcDoc={c.email.html} className="h-[30rem] w-full rounded-lg border border-line bg-white" />
                  <p className="text-xs text-muted">Shown with example details. Each person sees their own.</p>
                </div>
              ) : <p className="text-sm text-muted">The email isn’t available.</p>}
            </Card>
          </aside>
        </div>
      )}
      {asking === "send" && c && <ConfirmDialog title="Send this campaign?" confirmLabel={later ? "Schedule it" : "Send now"} onConfirm={() => send.mutate()} onCancel={() => setAsking(null)}>“{c.email?.subject}” will go to <b>{num(reach)}</b> {reach === 1 ? "person" : "people"} {later && when ? `at ${new Date(when).toLocaleString()}` : "now"}, a few every minute{c.hours?.enabled ? `, only during ${c.hours.start}:00 to ${c.hours.end}:00 where each person lives (the rest wait for the morning)` : ""}. You can cancel while it is going out.</ConfirmDialog>}
      {asking === "cancel" && <ConfirmDialog title="Cancel this campaign?" confirmLabel="Cancel campaign" cancelLabel="Keep it going" onConfirm={() => cancel.mutate()} onCancel={() => setAsking(null)}>Anyone not yet emailed won’t be. Emails already sent can’t be taken back.</ConfirmDialog>}
      {asking === "delete" && <ConfirmDialog title="Delete this draft?" confirmLabel="Delete" onConfirm={() => del.mutate()} onCancel={() => setAsking(null)}>Nothing has been sent, so nothing is lost except this draft.</ConfirmDialog>}
    </div>
  );
}

function NewCampaign({ segments, copies, fields }: { segments: SegmentPick[]; copies: Pick[]; fields: FieldDef[] | undefined }) {
  const qc = useQueryClient();
  const toast = useToast();
  const url = useUrlState();
  const [segment_id, setSegment] = useState(url.get("segment") ?? "");
  const [copy_id, setCopy] = useState(url.get("copy") ?? "");
  const [name, setName] = useState("");
  const seg = segments.find((s) => s.id === segment_id);
  const cp = copies.find((c) => c.id === copy_id);
  const suggested = seg && cp ? `${cp.name} to ${seg.name}` : "";
  const create = useMutation({
    mutationFn: () => unwrap(api.POST("/v1/admin/marketing/campaigns", { body: { name: name.trim() || suggested, segment_id, copy_id, ab_mode: "split", test_percent: 20, wait_hours: 4, metric: "opens" } })),
    onSuccess: async (c) => { await qc.invalidateQueries({ queryKey: ["campaigns"] }); toast("Draft created. Check it over, then send it."); url.set({ new: null, segment: null, copy: null, open: (c as unknown as Campaign).id }); },
  });
  return (
    <div className="space-y-4">
      <Crumbs trail={[["Campaigns", `${MARKETING}/campaigns`], ["New campaign"]]} />
      <Card>
        <div className="space-y-6">
          <Step n={1} title="Who should get it?" hint="Pick one of your segments.">
            <label className="block text-sm font-semibold">Segment<select className={inputCls} value={segment_id} onChange={(e) => setSegment(e.target.value)}><option value="">Choose a segment…</option>{segments.map((s) => <option key={s.id} value={s.id}>{s.name}</option>)}</select></label>
            {seg && fields && <p className="text-xs text-muted">{describeRules(seg.rules, fields)}</p>}
            <Link className="text-sm font-semibold underline" to={`${MARKETING}/segments?edit=new`}>Need a different group? Make a new segment</Link>
          </Step>
          <Step n={2} title="What should they get?" hint="Pick one of the emails you’ve written.">
            <label className="block text-sm font-semibold">Email<select className={inputCls} value={copy_id} onChange={(e) => setCopy(e.target.value)}><option value="">Choose an email…</option>{copies.map((c) => <option key={c.id} value={c.id}>{c.name}</option>)}</select></label>
            <Link className="text-sm font-semibold underline" to={`${MARKETING}/copies?edit=new`}>Need a different email? Write a new one</Link>
          </Step>
          <Step n={3} title="Name this campaign" hint="Only you see it. You’ll choose when to send on the next page.">
            <label className="block text-sm font-semibold">Name<input className={inputCls} value={name} maxLength={120} placeholder={suggested || "e.g. Welcome nudge for new sign-ups"} onChange={(e) => setName(e.target.value)} /></label>
          </Step>
          <ErrorBox error={create.error} />
          <div className="flex flex-wrap items-center gap-2">
            <Button disabled={!segment_id || !copy_id || (!name.trim() && !suggested) || create.isPending} onClick={() => create.mutate()}>{create.isPending ? "Creating…" : "Create draft"}</Button>
            <Button variant="secondary" onClick={() => url.set({ new: null, segment: null, copy: null })}>Cancel</Button>
            <span className="text-xs text-muted">Nothing is sent yet. You’ll see who it reaches and the email first.</span>
          </div>
        </div>
      </Card>
    </div>
  );
}

export function CampaignsTab({ engine }: { engine: string }) {
  const manage = useCan()("marketing.manage");
  const url = useUrlState();
  const open = url.get("open");
  const creating = url.get("new") === "1";
  const list = useQuery({ queryKey: ["campaigns"], queryFn: () => unwrap(api.GET("/v1/admin/marketing/campaigns")).then((r) => (r as unknown as { items: Campaign[] }).items), refetchInterval: 10000 });
  const segments = useQuery({ queryKey: ["segments"], queryFn: () => unwrap(api.GET("/v1/admin/marketing/segments")).then((r) => (r as unknown as { items: SegmentPick[] }).items) });
  const copies = useQuery({ queryKey: ["copies"], queryFn: () => unwrap(api.GET("/v1/admin/marketing/copies")).then((r) => (r as unknown as { items: Pick[] }).items) });
  const fields = useQuery({ queryKey: ["segment-fields"], queryFn: () => unwrap(api.GET("/v1/admin/marketing/segment-fields")).then((r) => (r as unknown as { fields: FieldDef[] }).fields) });
  if (open) return <Detail id={open} manage={manage} engine={engine} />;
  if (creating && segments.data && copies.data) return <NewCampaign segments={segments.data} copies={copies.data} fields={fields.data} />;
  const noSegments = (segments.data?.length ?? 0) === 0;
  const noCopies = (copies.data?.length ?? 0) === 0;
  const blocked = !segments.isLoading && !copies.isLoading && (noSegments || noCopies);
  return (
    <div className="space-y-5">
      <PageIntro
        title="Campaigns"
        how={["Pick a segment (who) and one of your emails (what).", "Check the audience and the email, and send yourself a test.", "Send it now or choose a time. It goes out a few every minute, and you can cancel while it’s going.", "Come back here to see how many opened it and clicked."]}
        actions={manage && <Button disabled={blocked} onClick={() => url.set({ new: "1" })}>New campaign</Button>}
      >A campaign sends one email to one segment, once. Use it for announcements, or to nudge a group of people right now.</PageIntro>
      <ErrorBox error={list.error ?? segments.error ?? copies.error} />
      {list.isLoading ? <p aria-busy="true">Loading…</p> : blocked ? (
        <Card><EmptyState title="First, you need two things" actions={<>{noSegments && <Link className="rounded-lg border border-ink bg-brand-green px-4 py-2.5 text-sm font-semibold" to={`${MARKETING}/segments?edit=new`}>Make a segment</Link>}{noCopies && <Link className="rounded-lg border border-ink bg-brand-green px-4 py-2.5 text-sm font-semibold" to={`${MARKETING}/copies?edit=new`}>Write an email</Link>}</>}>
          A campaign needs {noSegments && noCopies ? "a segment (who gets it) and an email (what they get)" : noSegments ? "a segment: the group of people who get it" : "an email to send"}. {noSegments && !noCopies ? "You have an email already." : !noSegments && noCopies ? "You have a segment already." : ""}
        </EmptyState></Card>
      ) : list.data && list.data.length === 0 ? (
        <Card><EmptyState title="You haven’t made a campaign yet" actions={manage && <Button onClick={() => url.set({ new: "1" })}>Make your first campaign</Button>}>It takes a minute: choose who, choose the email, then review and send.</EmptyState></Card>
      ) : (
        <ul className="space-y-3">{list.data?.map((c) => (
          <li key={c.id} className="rounded-xl border border-line bg-white p-4 text-sm shadow-sm">
            <div className="flex flex-wrap items-start justify-between gap-3">
              <div className="min-w-0 space-y-1"><p className="text-base font-bold">{c.name} <Badge s={c.status} /></p><p className="text-muted">“{c.copy_name}” to {c.segment_name}{c.send_at && ` · ${new Date(c.send_at).toLocaleString()}`}</p>{c.counts && <p className="text-xs text-muted">{num(c.counts.sent)} of {num(c.audience)} sent{c.counts.opened !== undefined && c.counts.sent > 0 ? ` · ${num(c.counts.opened)} opened · ${num(c.counts.clicked ?? 0)} clicked` : ""}</p>}</div>
              <Button variant="secondary" onClick={() => url.set({ open: c.id })}>{c.status === "draft" ? "Open and finish" : "See results"}</Button>
            </div>
          </li>))}
        </ul>
      )}
    </div>
  );
}
