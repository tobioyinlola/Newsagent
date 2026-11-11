import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { Link, useNavigate } from "react-router-dom";
import { api, unwrap } from "../api/client";
import { Button, Card, ErrorBox } from "../components/ui";
import { Check, GLOSSARY, MARKETING, PageIntro, useToast } from "../components/marketingUi";
import { num } from "../lib/format";
import { useCan } from "../lib/can";
import type { Status } from "./Marketing";

type Item = { id: string };
type Campaign = Item & { status: string };
type Workflow = Item & { status: string };
const go = "inline-flex items-center rounded-lg border border-ink bg-brand-green px-3.5 py-2 text-sm font-semibold";

// Where to begin: what the three ideas are, a checklist that tracks what's done, and where things stand.
export function OverviewTab({ status }: { status: Status | undefined }) {
  const qc = useQueryClient();
  const toast = useToast();
  const nav = useNavigate();
  const manage = useCan()("marketing.manage");
  const segments = useQuery({ queryKey: ["segments"], queryFn: () => unwrap(api.GET("/v1/admin/marketing/segments")).then((r) => (r as unknown as { items: Item[] }).items) });
  const copies = useQuery({ queryKey: ["copies"], queryFn: () => unwrap(api.GET("/v1/admin/marketing/copies")).then((r) => (r as unknown as { items: Item[] }).items) });
  const campaigns = useQuery({ queryKey: ["campaigns"], queryFn: () => unwrap(api.GET("/v1/admin/marketing/campaigns")).then((r) => (r as unknown as { items: Campaign[] }).items) });
  const workflows = useQuery({ queryKey: ["workflows"], queryFn: () => unwrap(api.GET("/v1/admin/marketing/workflows")).then((r) => (r as unknown as { items: Workflow[] }).items) });
  const starter = useMutation({
    mutationFn: () => unwrap(api.POST("/v1/admin/marketing/workflows/starter")),
    onSuccess: async (w) => { await Promise.all(["workflows", "segments", "copies"].map((k) => qc.invalidateQueries({ queryKey: [k] }))); toast("Welcome sequence created as a draft. Look it over, then turn it on."); nav(`${MARKETING}/workflows?open=${(w as unknown as Item).id}`); },
  });
  const loading = segments.isLoading || copies.isLoading || campaigns.isLoading || workflows.isLoading;
  const nSeg = segments.data?.length ?? 0;
  const nCopy = copies.data?.length ?? 0;
  const liveCampaigns = campaigns.data?.filter((c) => ["scheduled", "sending"].includes(c.status)).length ?? 0;
  const sentCampaigns = campaigns.data?.filter((c) => ["scheduled", "sending", "sent"].includes(c.status)).length ?? 0;
  const runningFlows = workflows.data?.filter((w) => w.status === "active").length ?? 0;
  const engineOk = !!status && status.engine !== "off";
  const steps: { done: boolean; key: string; node: React.ReactNode; action?: React.ReactNode }[] = [
    { key: "engine", done: engineOk, node: engineOk ? (status?.engine === "dry_run" ? "Sending is in test mode (nothing is really emailed yet)." : "Sending is switched on.") : "Sending is switched off. Ask whoever manages the server to turn it on (try test mode first).", },
    { key: "bounces", done: !!status?.bounce_events, node: status?.bounce_events ? "Bounces and spam complaints are being reported to us." : "Set up bounce and spam-complaint reporting, so bad addresses block themselves. This protects your sender reputation.", action: <a className="text-sm font-semibold underline" href="#setup-help">How</a> },
    { key: "segment", done: nSeg > 0, node: nSeg > 0 ? <>You have {nSeg} segment{nSeg === 1 ? "" : "s"}.</> : "Make a segment: the group of people you want to email.", action: <Link className={go} to={`${MARKETING}/segments?edit=new`}>Make a segment</Link> },
    { key: "email", done: nCopy > 0, node: nCopy > 0 ? <>You have {nCopy} email{nCopy === 1 ? "" : "s"} written.</> : "Write an email: what they’ll receive.", action: <Link className={go} to={`${MARKETING}/copies?edit=new`}>Write an email</Link> },
    { key: "send", done: sentCampaigns > 0 || runningFlows > 0, node: sentCampaigns > 0 || runningFlows > 0 ? "You’ve sent a campaign or turned on a workflow." : "Send a campaign, or turn on a workflow. Send yourself a test first.", action: <Link className={go} to={nSeg > 0 && nCopy > 0 ? `${MARKETING}/campaigns?new=1` : `${MARKETING}/campaigns`}>Send a campaign</Link> },
  ];
  const done = steps.filter((s) => s.done).length;
  const next = steps.find((s) => !s.done)?.key;
  return (
    <div className="space-y-6">
      <PageIntro title="Start here">New to this? Marketing works in three steps. Do them in order and you’ll have sent your first email in a few minutes.</PageIntro>
      <ol className="grid gap-3 md:grid-cols-3" aria-label="The three steps">
        {[
          { n: 1, title: "Who", text: "Build a segment: a saved group of people, like “joined this week and hasn’t made a video”.", to: "segments", count: `${nSeg} saved`, cta: "Segments" },
          { n: 2, title: "What", text: "Write the email once: a subject, a message and a button. Use it again and again.", to: "copies", count: `${nCopy} written`, cta: "Email copy" },
          { n: 3, title: "When", text: "Send it once now or later (a campaign), or set up emails that follow people over time (a workflow).", to: "campaigns", count: `${liveCampaigns} going out · ${runningFlows} workflow${runningFlows === 1 ? "" : "s"} on`, cta: "Campaigns" },
        ].map((c) => (
          <li key={c.n} className="flex flex-col rounded-2xl border border-line bg-white p-4 shadow-sm">
            <span aria-hidden="true" className="flex h-8 w-8 items-center justify-center rounded-full border border-ink bg-brand-green text-sm font-bold">{c.n}</span>
            <h3 className="mt-2 text-lg font-bold">{c.title}</h3>
            <p className="mt-1 flex-1 text-sm text-muted">{c.text}</p>
            <p className="mt-3 text-xs text-muted">{loading ? "…" : c.count}</p>
            <Link to={`${MARKETING}/${c.to}`} className="mt-2 text-sm font-semibold underline">{c.cta} →</Link>
          </li>
        ))}
      </ol>
      <Card title={loading || !status ? "Get ready to send" : `Get ready to send · ${done} of ${steps.length} done`}>
        <ErrorBox error={segments.error ?? copies.error ?? campaigns.error ?? workflows.error} />
        {loading || !status ? <p aria-busy="true" className="text-sm text-muted">Checking what’s already done…</p> : <ul className="divide-y divide-line">
          {steps.map((s) => <Check key={s.key} done={s.done} action={s.key === next ? s.action : s.key === "bounces" ? s.action : undefined}>{s.key === next && <span className="mr-2 rounded-sm bg-brand-green px-1.5 py-0.5 text-xs font-bold">Next</span>}{s.node}</Check>)}
        </ul>}
        <p id="setup-help" className="mt-3 text-xs text-muted">Setting up bounce reporting is a one-time job for whoever manages the server: it’s explained step by step in <code>docs/marketing-email-setup.md</code>.</p>
      </Card>
      {manage && (workflows.data?.length ?? 1) === 0 && (
        <Card title="Want a head start?">
          <div className="flex flex-wrap items-center justify-between gap-3 text-sm">
            <p className="max-w-xl text-muted">Create a ready-made <b className="text-ink">welcome sequence</b>: it welcomes new sign-ups, nudges anyone who hasn’t made a video after 3 days, and reminds people about credits after a week. You can change everything before turning it on.</p>
            <Button disabled={starter.isPending} onClick={() => starter.mutate()}>{starter.isPending ? "Making it…" : "Create the welcome sequence"}</Button>
          </div>
          <ErrorBox error={starter.error} />
        </Card>
      )}
      {status && (
        <Card title="Where things stand">
          <dl className="grid grid-cols-2 gap-4 text-sm md:grid-cols-4">
            {[["Sent today", num(status.sent_today), "marketing emails"], ["Campaigns going out", String(liveCampaigns), "scheduled or sending"], ["Workflows running", String(runningFlows), "turned on"], ["Won’t be emailed", num(status.opted_out + status.suppressed), `${num(status.opted_out)} unsubscribed · ${num(status.suppressed)} blocked`]].map(([k, v, sub]) => (
              <div key={k}><dt className="text-xs text-muted">{k}</dt><dd className="text-2xl font-bold tabular-nums">{v}</dd><dd className="text-xs text-muted">{sub}</dd></div>
            ))}
          </dl>
          <p className="mt-4 text-sm"><Link className="font-semibold underline" to={`${MARKETING}/activity`}>See every email sent →</Link></p>
        </Card>
      )}
      <details className="rounded-2xl border border-line bg-white p-4 text-sm shadow-sm">
        <summary className="cursor-pointer font-semibold">What do these words mean?</summary>
        <dl className="mt-3 grid gap-x-6 gap-y-3 sm:grid-cols-2">{GLOSSARY.map(([term, meaning]) => <div key={term}><dt className="font-bold">{term}</dt><dd className="text-muted">{meaning}</dd></div>)}</dl>
      </details>
    </div>
  );
}
