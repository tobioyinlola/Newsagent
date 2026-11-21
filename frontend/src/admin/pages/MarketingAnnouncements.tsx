import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, unwrap, unwrapPage } from "../api/client";
import { AnnouncementCard } from "../../components/AnnouncementCard";
import { Pager } from "../../components/Pager";
import { usePaged } from "../../lib/usePaged";
import { Button, Card, ConfirmDialog, ErrorBox, inputCls } from "../components/ui";
import { EmptyState, PageIntro, useToast } from "../components/marketingUi";
import { useCan } from "../lib/can";
import { num } from "../lib/format";

type Item = {
  id: string; title: string; message: string; button_label: string; button_url: string; shows_from: string; shows_until: string; ended_at: string | null;
  status: "scheduled" | "live" | "ended"; created_by: string; email: null | { campaign_id: string; status: string; audience: number; sent?: number };
};
const when = (v: string) => new Date(v).toLocaleString(undefined, { day: "numeric", month: "short", hour: "2-digit", minute: "2-digit" });
const BADGE: Record<string, string> = { live: "bg-lime-tint", scheduled: "bg-peach-tint", ended: "bg-paper" };

// An announcement: a pop-up customers see after signing in for as long as you choose, and (if you tick it) an email to everyone as well.
export function AnnouncementsTab({ engine }: { engine: string }) {
  const manage = useCan()("marketing.manage");
  const qc = useQueryClient();
  const toast = useToast();
  const [creating, setCreating] = useState(false);
  const list = usePaged(["announcements", "list"], (limit, offset) => unwrapPage<Item>(api.GET("/v1/admin/marketing/announcements", { params: { query: { limit, offset } } }), (b) => b.items, offset), { size: 10, refetchInterval: 20000 });
  const end = useMutation({
    mutationFn: (id: string) => unwrap(api.POST("/v1/admin/marketing/announcements/{announcement_id}/end", { params: { path: { announcement_id: id } } })),
    onSuccess: async () => { await qc.invalidateQueries({ queryKey: ["announcements"] }); toast("The pop-up has been stopped."); },
  });
  if (creating) return <NewAnnouncement engine={engine} onDone={() => setCreating(false)} />;
  return (
    <div className="space-y-5">
      <PageIntro
        title="Announcements"
        how={["Write the message once.", "Choose how long the pop-up keeps appearing when customers sign in. Each person can close it for good.", "Tick the email to also send it to everyone. People who unsubscribed are never emailed."]}
        actions={manage && <Button onClick={() => setCreating(true)}>New announcement</Button>}
      >Tell every customer something important: a pop-up when they sign in, and optionally an email too.</PageIntro>
      <ErrorBox error={list.query.error ?? end.error} />
      {list.query.isLoading ? <p aria-busy="true">Loading…</p> : list.total === 0 ? (
        <Card><EmptyState title="You haven’t sent an announcement yet" actions={manage && <Button onClick={() => setCreating(true)}>Write your first</Button>}>It shows as a pop-up when customers sign in, for as long as you choose.</EmptyState></Card>
      ) : (
        <ul className="space-y-3">
          {list.items.map((a) => (
            <li key={a.id} className="rounded-xl border border-line bg-white p-4 text-sm shadow-sm">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0 space-y-1">
                  <p className="text-base font-bold [overflow-wrap:anywhere]">{a.title} <span className={`ml-1 rounded-sm px-1.5 py-0.5 align-middle text-xs font-semibold capitalize ${BADGE[a.status]}`}>{a.status}</span></p>
                  <p className="text-muted [overflow-wrap:anywhere]">{a.message.length > 140 ? `${a.message.slice(0, 140)}…` : a.message}</p>
                  <p className="text-muted">Pop-up: {a.status === "scheduled" ? `starts ${when(a.shows_from)}, ` : ""}{a.status === "ended" ? `ended ${when(a.ended_at ?? a.shows_until)}` : `until ${when(a.shows_until)}`}</p>
                  <p className="text-muted">{a.email ? <>Email: {a.email.status === "sent" ? "sent to" : "to"} {num(a.email.audience)} people{a.email.status !== "sent" ? ` (${a.email.status})` : ""}</> : "No email"} · by {a.created_by}</p>
                </div>
                {manage && a.status !== "ended" && <Button variant="secondary" disabled={end.isPending} onClick={() => { if (confirm("Stop showing this pop-up now? An email that has already gone out cannot be taken back.")) end.mutate(a.id); }}>Stop the pop-up</Button>}
              </div>
            </li>
          ))}
        </ul>
      )}
      <Pager total={list.total} page={list.page} size={list.size} onPage={list.setPage} noun="announcements" busy={list.query.isFetching} />
    </div>
  );
}

function NewAnnouncement({ engine, onDone }: { engine: string; onDone: () => void }) {
  const qc = useQueryClient();
  const toast = useToast();
  const [f, setF] = useState({ title: "", message: "", button_label: "", button_url: "", show_for: "3", unit: "days" as "hours" | "days", later: false, starts_at: "", send_email: engine !== "off" });
  const [confirm, setConfirm] = useState(false);
  const audience = useQuery({ queryKey: ["announcement-audience"], queryFn: () => unwrap(api.GET("/v1/admin/marketing/announcements/audience")) as unknown as Promise<{ reachable: number; email_engine: string }> });
  const reachable = audience.data?.reachable ?? 0;
  const emailOff = engine === "off";
  const publish = useMutation({
    mutationFn: () => unwrap(api.POST("/v1/admin/marketing/announcements", { body: {
      title: f.title.trim(), message: f.message.trim(), button_label: f.button_label.trim(), button_url: f.button_url.trim(),
      show_for: Number(f.show_for), unit: f.unit, starts_at: f.later && f.starts_at ? new Date(f.starts_at).toISOString() : null,
      send_email: f.send_email && !emailOff, confirm_count: f.send_email && !emailOff ? reachable : null,
    } as never })),
    onSuccess: async () => { setConfirm(false); await qc.invalidateQueries({ queryKey: ["announcements"] }); toast("Announcement published."); onDone(); },
    onError: () => setConfirm(false),
  });
  const set = <K extends keyof typeof f>(k: K, v: (typeof f)[K]) => setF((x) => ({ ...x, [k]: v }));
  const ok = f.title.trim() && f.message.trim() && Number(f.show_for) >= 1 && (!f.later || f.starts_at) && !!f.button_label.trim() === !!f.button_url.trim();
  const emailing = f.send_email && !emailOff;
  return (
    <div className="space-y-5">
      <PageIntro title="New announcement">Write it once. It appears as a pop-up when customers sign in, and can be emailed to everyone too.</PageIntro>
      <div className="grid gap-5 lg:grid-cols-[minmax(0,1fr)_minmax(0,24rem)]">
        <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); publish.reset(); setConfirm(true); }}>
          <Card>
            <div className="space-y-4">
              <label className="block text-sm font-semibold">Headline<input className={inputCls} maxLength={120} required value={f.title} onChange={(e) => set("title", e.target.value)} /></label>
              <label className="block text-sm font-semibold">Message<textarea className={inputCls} rows={5} maxLength={2000} required value={f.message} onChange={(e) => set("message", e.target.value)} /><span className="mt-1 block text-right text-xs font-normal text-muted">{f.message.length} / 2000</span></label>
              <div className="grid gap-3 sm:grid-cols-2">
                <label className="block text-sm font-semibold">Button text (optional)<input className={inputCls} maxLength={60} value={f.button_label} onChange={(e) => set("button_label", e.target.value)} placeholder="See what’s new" /></label>
                <label className="block text-sm font-semibold">Where the button goes<input className={inputCls} maxLength={500} value={f.button_url} onChange={(e) => set("button_url", e.target.value)} placeholder="https://… or /distribution/request" /></label>
              </div>
            </div>
          </Card>
          <Card title="How long the pop-up shows">
            <div className="flex flex-wrap items-end gap-3">
              <label className="block text-sm font-semibold">Keep showing it for<input type="number" min={1} max={f.unit === "days" ? 90 : 2160} className={`${inputCls} w-28`} value={f.show_for} onChange={(e) => set("show_for", e.target.value)} /></label>
              <label className="block text-sm font-semibold"><span className="sr-only">Unit</span><select aria-label="Hours or days" className={`${inputCls} w-28`} value={f.unit} onChange={(e) => set("unit", e.target.value as "hours" | "days")}><option value="hours">hours</option><option value="days">days</option></select></label>
            </div>
            <p className="mt-2 text-xs text-muted">It appears each time someone signs in during this time, until they close it for good.</p>
            <label className="mt-3 flex items-center gap-2 text-sm"><input type="checkbox" checked={f.later} onChange={(e) => set("later", e.target.checked)} /> Start later (otherwise it starts right away)</label>
            {f.later && <label className="mt-2 block text-sm font-semibold">Start at<input type="datetime-local" className={inputCls} value={f.starts_at} onChange={(e) => set("starts_at", e.target.value)} /></label>}
          </Card>
          <Card title="Email">
            <label className="flex items-start gap-2 text-sm"><input type="checkbox" className="mt-1" checked={emailing} disabled={emailOff} onChange={(e) => set("send_email", e.target.checked)} /><span><b>Also email it to everyone</b><span className="block text-muted">{emailOff ? "Marketing email is switched off on the server, so the email can’t be sent. Ask whoever manages the server to turn it on." : audience.isLoading ? "Counting…" : `About ${num(reachable)} people will be emailed. People who unsubscribed or whose address bounced are left out.`}</span></span></label>
          </Card>
          <ErrorBox error={publish.error} />
          <div className="flex flex-wrap gap-3"><Button type="submit" disabled={!ok || publish.isPending}>Review and publish</Button><Button type="button" variant="secondary" onClick={onDone}>Cancel</Button></div>
        </form>
        <aside aria-label="Preview" className="space-y-2">
          <p className="text-sm font-semibold">What customers will see</p>
          <div className="flex justify-center rounded-xl bg-ink/80 p-4"><AnnouncementCard a={{ title: f.title || "Your headline", message: f.message || "Your message appears here." }}>{f.button_label && <span className="inline-block rounded-sm border-2 border-ink bg-brand-green px-5 py-2 text-sm font-bold">{f.button_label}</span>}</AnnouncementCard></div>
        </aside>
      </div>
      {confirm && <ConfirmDialog title="Publish this announcement?" confirmLabel={publish.isPending ? "Publishing…" : "Publish"} onConfirm={() => publish.mutate()} onCancel={() => setConfirm(false)}>
        It will show as a pop-up when customers sign in, for {f.show_for} {f.unit}{f.later && f.starts_at ? `, starting ${when(f.starts_at)}` : ", starting now"}.{emailing ? ` It will also be emailed to about ${num(reachable)} people.` : " No email will be sent."} You can stop the pop-up any time, but an email can’t be taken back.
      </ConfirmDialog>}
    </div>
  );
}
