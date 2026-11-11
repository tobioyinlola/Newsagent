import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, Navigate, NavLink, useParams } from "react-router-dom";
import { api, unwrap } from "../api/client";
import { Button, Card, ErrorBox } from "../components/ui";
import { MARKETING, ToastProvider, useToast } from "../components/marketingUi";
import { num } from "../lib/format";
import { useCan } from "../lib/can";
import { ActivityTab } from "./MarketingActivity";
import { CampaignsTab } from "./MarketingCampaigns";
import { CopiesTab } from "./MarketingCopies";
import { OptoutsTab } from "./MarketingOptouts";
import { OverviewTab } from "./MarketingOverview";
import { SegmentsTab } from "./MarketingSegments";
import { WorkflowsTab } from "./MarketingWorkflows";

export type Status = { engine: "off" | "on" | "dry_run"; config: { paused: boolean; min_gap_days: number; daily_cap: number; per_minute: number; track: boolean }; sent_today: number; opted_out: number; suppressed: number; bounce_events: boolean };

// The sections, in the order you'd use them: look around, build, send, then check how it went.
const NAV: { group: string | null; items: { to: string; label: string; hint: string }[] }[] = [
  { group: null, items: [{ to: "", label: "Start here", hint: "Where to begin, and what to do next" }] },
  { group: "Build", items: [{ to: "segments", label: "Segments", hint: "Saved groups of people to email" }, { to: "copies", label: "Email copy", hint: "The emails you write" }] },
  { group: "Send", items: [{ to: "campaigns", label: "Campaigns", hint: "Send one email to a segment, once" }, { to: "workflows", label: "Workflows", hint: "Emails sent over time, automatically" }] },
  { group: "Review", items: [{ to: "activity", label: "Activity", hint: "Every email sent or held back, and why" }, { to: "optouts", label: "Unsubscribed", hint: "People and addresses we never email" }] },
];
const TABS = new Set(NAV.flatMap((g) => g.items.map((i) => i.to)));

// Is email going out? Said in plain words. Full on the Start here page; a slim one-line bar everywhere else, so the page itself stays in view.
function StatusBanner({ s, full }: { s: Status; full: boolean }) {
  const qc = useQueryClient();
  const toast = useToast();
  const manage = useCan()("marketing.manage");
  const change = useMutation({
    mutationFn: (c: Partial<Status["config"]>) => unwrap(api.PUT("/v1/admin/marketing/config", { body: { ...s.config, ...c } })),
    onSuccess: async (_r, c) => { await qc.invalidateQueries({ queryKey: ["marketing-status"] }); toast("paused" in c ? (c.paused ? "All marketing email is paused." : "Sending has resumed.") : "Setting saved."); },
  });
  const paused = s.engine !== "off" && s.config.paused;
  const [tone, title, desc, short] = s.engine === "off" ? ["border-line bg-paper", "Sending is switched off", "You can build segments, emails and drafts, but nothing will be emailed until it’s switched on by whoever manages the server.", "nothing can be sent yet"]
    : paused ? ["border-brand-red bg-red-tint", "All marketing email is paused", "Nothing is going out. Campaigns are waiting and workflows are frozen where they are, until you resume.", "everything is on hold"]
    : s.engine === "dry_run" ? ["border-brand-purple bg-lilac", "Test mode: nothing is really emailed", "Everything works as normal and is recorded in Activity, but no email leaves. Good for trying things out.", "no email leaves"]
    : ["border-ink bg-lime-tint", "Sending is on", `${num(s.sent_today)} of ${num(s.config.daily_cap)} emails sent today.`, `${num(s.sent_today)} of ${num(s.config.daily_cap)} sent today`];
  const needsBounces = s.engine === "on" && !s.bounce_events; // only matters once real email goes out
  return (
    <section aria-label="Sending status" className={`rounded-2xl border-2 ${full ? "p-4" : "px-4 py-2.5"} ${tone}`}>
      <div className="flex flex-wrap items-center justify-between gap-x-4 gap-y-2">
        <div className="min-w-0">
          <p className="font-bold">{title}{!full && <span className="text-sm font-normal"> · {short}</span>}</p>
          {full && <p className="text-sm">{desc}</p>}
        </div>
        {manage && s.engine !== "off" && <Button variant={paused ? "primary" : "secondary"} className="!px-3 !py-1.5" disabled={change.isPending} onClick={() => change.mutate({ paused: !s.config.paused })} title={paused ? "Start sending again" : "Stops every campaign and workflow within a minute"}>{paused ? "Resume sending" : "Pause all sending"}</Button>}
      </div>
      <ErrorBox error={change.error} />
      {needsBounces && (full
        ? <p className="mt-3 rounded-lg border border-brand-peach bg-peach-tint px-3 py-2 text-sm"><b>Set this up now:</b> bounces and spam complaints aren’t being reported to us, so bad addresses won’t block themselves and your sender reputation can suffer. Ask whoever manages the server to follow <code>docs/marketing-email-setup.md</code> (section 2).</p>
        : <p className="mt-1.5 text-sm"><span aria-hidden="true">⚠ </span>Bounces aren’t being reported yet. <Link className="font-semibold underline" to={MARKETING}>See what to do</Link></p>)}
      <details className="mt-2 text-sm">
        <summary className="cursor-pointer font-semibold underline underline-offset-2">{full ? "Sending rules and settings" : "Details and settings"}</summary>
        <div className="mt-2 space-y-3">
          {!full && <p>{desc}</p>}
          <ul className="list-disc space-y-1 pl-5">
            <li>Nobody gets more than one marketing email every <b>{s.config.min_gap_days} days</b>, so people aren’t flooded.</li>
            <li>At most <b>{num(s.config.daily_cap)}</b> emails a day, and about <b>{num(s.config.per_minute)}</b> a minute, so a big send is spread out.</li>
            <li>People who unsubscribed, bounced or marked us as spam ({num(s.opted_out)} unsubscribed, {num(s.suppressed)} blocked) are never emailed.</li>
            <li>Account emails like sign-in codes and receipts are never held back by any of this.</li>
          </ul>
          <label className="flex items-start gap-2"><input type="checkbox" className="mt-1" checked={s.config.track} disabled={!manage || change.isPending} onChange={(e) => change.mutate({ track: e.target.checked })} /><span><b>Count opens and clicks.</b> Adds a tiny invisible picture to each email and sends the button through our site, so you can see how many people opened and clicked. Opens are approximate; clicks are the number to trust.</span></label>
        </div>
      </details>
    </section>
  );
}

export function MarketingAdmin() {
  const tab = useParams()["*"] ?? "";
  const status = useQuery({ queryKey: ["marketing-status"], queryFn: () => unwrap(api.GET("/v1/admin/marketing/status")) as unknown as Promise<Status> });
  const s = status.data;
  if (!TABS.has(tab)) return <Navigate to={MARKETING} replace />;
  const engine = s?.engine ?? "off";
  return (
    <ToastProvider>
      <div className="space-y-5">
        <h1 className="text-2xl font-bold">Marketing</h1>
        <ErrorBox error={status.error} />
        {s ? <StatusBanner s={s} full={tab === ""} /> : !status.error && <Card><p aria-busy="true" className="text-sm text-muted">Loading…</p></Card>}
        <nav aria-label="Marketing sections" className="flex flex-wrap gap-x-5 gap-y-2 border-b border-line pb-3">
          {NAV.map((g) => (
            <div key={g.group ?? "start"} className="flex flex-wrap items-center gap-2">
              {g.group && <span className="text-[11px] font-bold uppercase tracking-widest text-muted">{g.group}</span>}
              {g.items.map((i) => (
                <NavLink key={i.to} end to={i.to ? `${MARKETING}/${i.to}` : MARKETING} title={i.hint} className={({ isActive }) => `rounded-lg border px-3 py-1.5 text-sm font-semibold sm:px-3.5 sm:py-2 ${isActive ? "border-ink bg-brand-green" : "border-line bg-white hover:border-ink"}`}>{i.label}</NavLink>
              ))}
            </div>
          ))}
        </nav>
        <main className="space-y-5" aria-live="polite">
          {tab === "" && <OverviewTab status={s} />}
          {tab === "segments" && <SegmentsTab />}
          {tab === "copies" && <CopiesTab />}
          {tab === "campaigns" && <CampaignsTab engine={engine} />}
          {tab === "workflows" && <WorkflowsTab engine={engine} />}
          {tab === "activity" && <ActivityTab />}
          {tab === "optouts" && <OptoutsTab />}
        </main>
      </div>
    </ToastProvider>
  );
}
