import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { distributionApi } from "../../lib/distribution";
import { Button, Card, ErrorBox, Notice, inputCls } from "../components/ui";
import { getToken } from "../lib/auth";
import { useCan } from "../lib/can";

const request = <T,>(path: string, method = "GET", body?: unknown) => distributionApi<T>(path, getToken(), method, body);

type Template = { id: string; name: string; subject: string; body: string };
type Step = { id: string; label: string; never_auto: boolean; default: string };
type Config = { templates: Template[]; default_template: string; sender_name: string; sender_title: string; footer_address: string; mode: string; daily_cap: number; ai_turn_limit: number; paused: boolean; policy: Record<string, string> };
type ConfigOut = { config: Config; variables: string[]; steps: Step[]; engine_on: boolean; reply_domain: string };
type Thread = { id: string; request_id: string; outlet_name: string; contact_name: string; contact_email: string; status: string; ai_paused: boolean; updated_at: string | null; last: { direction: string; status: string; snippet: string } | null };
type Message = { id: string; direction: "in" | "out"; kind: string; status: string; subject: string; body: string; sender: string; actor: string; created_at: string | null; sent_at: string | null; ai: { step?: string; intent?: string; reasons?: string[]; summary?: string; suspicious?: boolean; has_account_details?: boolean; sender_mismatch?: boolean; error?: string; approved_by?: string; edited?: boolean } };
type Facts = { quoted_price?: number; currency?: string | null; deadline?: string; last_intent?: string; has_account_details?: boolean; account_masked?: string; account_verified?: boolean; account_verified_by?: string | null };
type Detail = { thread: Thread; messages: Message[]; facts: Facts; request: { id: string; headline: string; status: string } | null; placement: { id: string; internal_status: string; status: string } | null };
type ContactRow = { row: number; outlet: string; outlet_name: string | null; contact_name: string; contact_email: string; template: string | null; status: string };

const STATUS: Record<string, string> = { awaiting_reply: "Waiting for the outlet", replied: "Outlet replied", needs_approval: "Needs your approval", agreed: "Agreed", closed: "Closed", do_not_contact: "Do not contact" };
const tone = (s: string) => (s === "needs_approval" ? "border-brand-red bg-red-tint" : s === "replied" ? "border-brand-purple bg-lilac" : s === "agreed" ? "border-ink bg-lime-tint" : "border-line bg-paper");
const when = (v: string | null) => (v ? new Date(v).toLocaleString() : "");
const ROW_STATUS: Record<string, string> = { ok: "Will be saved", unchanged: "Already saved", unknown_outlet: "No outlet with that name", bad_email: "Not a valid email" };

function Facts({ facts, canManage, revealed, onReveal, onVerify, busy }: { facts: Facts; canManage: boolean; revealed: { details: Record<string, string>; messages: { id: string; text: string }[] } | null; onReveal: () => void; onVerify: () => void; busy: boolean }) {
  const has = facts.quoted_price != null || facts.deadline || facts.has_account_details;
  if (!has) return null;
  return (
    <div className="space-y-2 rounded-lg border border-line bg-paper p-3 text-sm">
      <p className="font-semibold">What the agent understood</p>
      <ul className="space-y-1">
        {facts.quoted_price != null && <li>Their price: <strong>{facts.quoted_price} {facts.currency ?? ""}</strong> (not agreed by us)</li>}
        {facts.deadline && <li>Date or deadline mentioned: {facts.deadline}</li>}
      </ul>
      {facts.has_account_details && (
        <div className="rounded border border-brand-red bg-red-tint p-2">
          <p className="font-semibold">They sent account details: {facts.account_masked}</p>
          <p className="mt-1 text-xs">Never pay on an email alone. Confirm these with the outlet another way first (call a number you already know, or write to a contact you already had). We only record payments; the agent never pays.</p>
          {facts.account_verified ? <p className="mt-1 text-xs font-semibold">Confirmed by {facts.account_verified_by}.</p> : null}
          {revealed && <dl className="mt-2 grid gap-x-3 text-xs sm:grid-cols-2">{Object.entries(revealed.details).filter(([, v]) => v).map(([k, v]) => <div key={k}><dt className="inline font-semibold">{k.replace("_", " ")}: </dt><dd className="inline">{v}</dd></div>)}</dl>}
          {canManage && <div className="mt-2 flex flex-wrap gap-2"><Button type="button" variant="secondary" disabled={busy} onClick={onReveal}>Show the full details (recorded)</Button>{!facts.account_verified && <Button type="button" variant="secondary" disabled={busy} onClick={onVerify}>I confirmed these with the outlet</Button>}</div>}
        </div>
      )}
    </div>
  );
}

function Conversations() {
  const qc = useQueryClient();
  const canManage = useCan()("operations.manage");
  const [status, setStatus] = useState("");
  const [q, setQ] = useState("");
  const [openId, setOpenId] = useState<string | null>(null);
  const list = useQuery({ queryKey: ["outreach-threads", status, q], queryFn: () => request<{ threads: Thread[]; counts: Record<string, number> }>(`admin/outreach/threads?${new URLSearchParams({ ...(status ? { status } : {}), ...(q.trim() ? { q: q.trim() } : {}) })}`), refetchInterval: 20000 });
  const detail = useQuery({ queryKey: ["outreach-thread", openId], queryFn: () => request<Detail>(`admin/outreach/threads/${openId}`), enabled: !!openId, refetchInterval: 15000 });
  const [text, setText] = useState("");
  useEffect(() => setText(""), [openId]);
  const refresh = () => { void qc.invalidateQueries({ queryKey: ["outreach-threads"] }); void qc.invalidateQueries({ queryKey: ["outreach-thread", openId] }); };
  const send = useMutation({ mutationFn: () => request(`admin/outreach/threads/${openId}/reply`, "POST", { body: text }), onSuccess: () => { setText(""); refresh(); } });
  const approve = useMutation({ mutationFn: (v: { mid: string; body: string }) => request(`admin/outreach/threads/${openId}/messages/${v.mid}/approve`, "POST", { body: v.body }), onSuccess: refresh });
  const discard = useMutation({ mutationFn: (mid: string) => request(`admin/outreach/threads/${openId}/messages/${mid}/discard`, "POST"), onSuccess: refresh });
  const askAi = useMutation({ mutationFn: () => request(`admin/outreach/threads/${openId}/ai-draft`, "POST"), onSuccess: () => window.setTimeout(refresh, 2500) });
  const [revealed, setRevealed] = useState<{ details: Record<string, string>; messages: { id: string; text: string }[] } | null>(null);
  const reveal = useMutation({ mutationFn: () => request<{ details: Record<string, string>; messages: { id: string; text: string }[] }>(`admin/outreach/threads/${openId}/account-details`), onSuccess: setRevealed });
  const verify = useMutation({ mutationFn: () => request(`admin/outreach/threads/${openId}/account-details/verify`, "POST"), onSuccess: refresh });
  const [edits, setEdits] = useState<Record<string, string>>({});
  useEffect(() => { setRevealed(null); setEdits({}); }, [openId]);
  const mark = useMutation({ mutationFn: (v: { status?: string; ai_paused?: boolean }) => request(`admin/outreach/threads/${openId}/status`, "POST", v), onSuccess: refresh });
  const counts = list.data?.counts ?? {};
  const d = detail.data;
  return (
    <div className="grid gap-4 lg:grid-cols-[22rem_minmax(0,1fr)]">
      <Card title="Conversations">
        <div className="flex flex-wrap gap-2" role="group" aria-label="Filter by status">
          <button type="button" aria-pressed={!status} className={`min-h-9 rounded-full border px-3 text-sm font-semibold ${!status ? "border-ink bg-ink text-white" : "border-line"}`} onClick={() => setStatus("")}>All</button>
          {Object.entries(STATUS).map(([k, label]) => (
            <button key={k} type="button" aria-pressed={status === k} className={`min-h-9 rounded-full border px-3 text-sm ${status === k ? "border-ink bg-ink text-white" : "border-line"}`} onClick={() => setStatus(status === k ? "" : k)}>{label} ({counts[k] ?? 0})</button>
          ))}
        </div>
        <label className="mt-3 block text-sm font-semibold">Search outlet, email or request<input className={inputCls} value={q} onChange={(e) => setQ(e.target.value)} /></label>
        <ErrorBox error={list.error} />
        <ul className="mt-3 max-h-[32rem] space-y-2 overflow-y-auto">
          {list.data?.threads.map((t) => (
            <li key={t.id}>
              <button type="button" aria-current={openId === t.id} onClick={() => setOpenId(t.id)} className={`block w-full rounded-lg border p-3 text-left ${openId === t.id ? "border-ink bg-lime-tint" : "border-line bg-white hover:border-ink"}`}>
                <span className="flex items-baseline justify-between gap-2"><strong className="truncate">{t.outlet_name}</strong><span className={`shrink-0 rounded-full border px-2 py-0.5 text-xs ${tone(t.status)}`}>{STATUS[t.status] ?? t.status}</span></span>
                <span className="block truncate text-xs text-muted">{t.contact_name ? `${t.contact_name} · ` : ""}{t.contact_email}</span>
                {t.last && <span className="mt-1 block truncate text-sm">{t.last.direction === "in" ? "They: " : "We: "}{t.last.snippet}</span>}
              </button>
            </li>
          ))}
          {list.data?.threads.length === 0 && <li className="text-sm text-muted">No conversations yet. They start when a paid request names an outlet that has a contact and automatic outreach.</li>}
        </ul>
      </Card>
      <Card title={d ? `${d.thread.outlet_name}` : "Conversation"}>
        {!d && <p className="text-sm text-muted">{detail.isLoading ? "Loading…" : "Pick a conversation to read it."}</p>}
        <ErrorBox error={detail.error ?? send.error ?? mark.error ?? approve.error ?? discard.error ?? askAi.error ?? reveal.error ?? verify.error} />
        {d && (
          <div className="space-y-4">
            <p className="text-sm text-muted">{d.thread.contact_name || "Contact"} &lt;{d.thread.contact_email}&gt; · <span className={`rounded-full border px-2 py-0.5 ${tone(d.thread.status)}`}>{STATUS[d.thread.status] ?? d.thread.status}</span>{d.request && <> · Request: {d.request.headline || d.request.id}</>}</p>
            {d.thread.status === "do_not_contact" && <Notice tone="warn">This contact asked us to stop. They will not be emailed again.</Notice>}
            <Facts facts={d.facts} canManage={canManage} revealed={revealed} onReveal={() => reveal.mutate()} onVerify={() => verify.mutate()} busy={reveal.isPending || verify.isPending} />
            {d.messages.filter((m) => m.status === "pending_approval").map((m) => (
                <li key={m.id} className="rounded-lg border-2 border-brand-red bg-red-tint p-3 text-sm">
                  <p className="font-semibold">The agent wrote this reply and is waiting for you</p>
                  {!!m.ai.reasons?.length && <ul className="mt-1 list-disc pl-5 text-xs">{m.ai.reasons.map((r) => <li key={r}>{r}</li>)}</ul>}
                  <label className="mt-2 block text-xs font-semibold">Subject: {m.subject}
                    <textarea className={inputCls} rows={6} value={edits[m.id] ?? m.body} onChange={(e) => setEdits({ ...edits, [m.id]: e.target.value })} disabled={!canManage} />
                  </label>
                  {canManage && <div className="mt-2 flex flex-wrap gap-2"><Button type="button" disabled={approve.isPending} onClick={() => approve.mutate({ mid: m.id, body: edits[m.id] ?? m.body })}>{approve.isPending ? "Sending…" : "Approve and send"}</Button><Button type="button" variant="secondary" disabled={discard.isPending} onClick={() => discard.mutate(m.id)}>Discard</Button></div>}
                </li>
            ))}
            <ol className="max-h-[26rem] space-y-3 overflow-y-auto" aria-label="Messages">
              {d.messages.filter((m) => m.status !== "pending_approval").map((m) => (
                <li key={m.id} className={`rounded-lg border p-3 text-sm ${m.direction === "in" ? "border-brand-purple bg-lilac" : "border-line bg-paper"}`}>
                  <p className="flex flex-wrap items-baseline justify-between gap-2 text-xs text-muted"><span>{m.direction === "in" ? `From ${m.sender || d.thread.contact_email}` : m.kind === "ai_auto" ? "The agent wrote (sent by itself)" : m.kind === "ai_draft" ? `The agent wrote, ${m.ai.approved_by ?? "a person"} approved${m.ai.edited ? " (edited)" : ""}` : `We wrote${m.actor && m.actor !== "system" ? ` (${m.actor})` : ""}`}</span><span>{m.status === "sent" || m.status === "received" ? when(m.sent_at ?? m.created_at) : m.status}</span></p>
                  <p className="mt-1 font-semibold">{m.subject}</p>
                  <p className="mt-1 whitespace-pre-wrap break-words">{m.body}</p>
                  {m.direction === "in" && (m.ai.sender_mismatch || m.ai.suspicious) && <p className="mt-2 rounded border border-brand-red bg-red-tint p-2 text-xs">{m.ai.sender_mismatch ? "This came from a different company than our contact. " : ""}{m.ai.suspicious ? "It looks like it is trying to instruct the agent, or looks suspicious. Be careful with anything it asks for." : ""}</p>}
                  {m.direction === "in" && m.ai.error && <p className="mt-2 text-xs text-muted">{m.ai.error}</p>}
                </li>
              ))}
            </ol>
            {canManage && d.thread.status !== "do_not_contact" && (
              <form className="space-y-2" onSubmit={(e) => { e.preventDefault(); if (text.trim() && !send.isPending) send.mutate(); }}>
                <label className="block text-sm font-semibold">Your reply<textarea className={inputCls} rows={5} value={text} onChange={(e) => setText(e.target.value)} placeholder="Write a reply. It is sent from our outreach address and the answer comes back here." /></label>
                <div className="flex flex-wrap gap-2">
                  <Button type="submit" disabled={!text.trim() || send.isPending}>{send.isPending ? "Sending…" : "Send reply"}</Button>
                  <Button type="button" variant="secondary" disabled={askAi.isPending} onClick={() => askAi.mutate()}>Ask the AI to draft</Button>
                  <Button type="button" variant="secondary" disabled={mark.isPending} onClick={() => mark.mutate({ ai_paused: !d.thread.ai_paused })}>{d.thread.ai_paused ? "Let the AI help again" : "Take over (stop the AI)"}</Button>
                  <Button type="button" variant="secondary" disabled={mark.isPending} onClick={() => mark.mutate({ status: "agreed" })}>Mark agreed</Button>
                  <Button type="button" variant="secondary" disabled={mark.isPending} onClick={() => mark.mutate({ status: "closed" })}>Close</Button>
                  <Button type="button" variant="danger" disabled={mark.isPending} onClick={() => { if (confirm("Never email this contact again?")) mark.mutate({ status: "do_not_contact" }); }}>Stop contacting</Button>
                </div>
              </form>
            )}
          </div>
        )}
      </Card>
    </div>
  );
}

function Settings({ data }: { data: ConfigOut }) {
  const qc = useQueryClient();
  const canManage = useCan()("operations.manage");
  const [cfg, setCfg] = useState<Config>(data.config);
  const [preview, setPreview] = useState<{ subject: string; body: string } | null>(null);
  useEffect(() => setCfg(data.config), [data.config]);
  const save = useMutation({ mutationFn: () => request("admin/outreach/config", "PUT", cfg), onSuccess: () => qc.invalidateQueries({ queryKey: ["outreach-config"] }) });
  const show = useMutation({ mutationFn: (t: Template) => request<{ subject: string; body: string }>("admin/outreach/preview", "POST", { subject: t.subject, body: t.body }), onSuccess: setPreview });
  const setT = (i: number, patch: Partial<Template>) => setCfg({ ...cfg, templates: cfg.templates.map((t, j) => (j === i ? { ...t, ...patch } : t)) });
  return (
    <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); save.mutate(); }}>
      <Card title="Who the emails come from">
        <fieldset disabled={!canManage || save.isPending} className="grid gap-4 sm:grid-cols-2">
          <label className="block text-sm font-semibold">Sender name<input className={inputCls} maxLength={120} value={cfg.sender_name} onChange={(e) => setCfg({ ...cfg, sender_name: e.target.value })} /></label>
          <label className="block text-sm font-semibold">Sender title<input className={inputCls} maxLength={120} value={cfg.sender_title} onChange={(e) => setCfg({ ...cfg, sender_title: e.target.value })} /></label>
          <label className="block text-sm font-semibold sm:col-span-2">Company postal address (shown under every email)<input className={inputCls} maxLength={300} value={cfg.footer_address} onChange={(e) => setCfg({ ...cfg, footer_address: e.target.value })} /></label>
        </fieldset>
        <p className="mt-2 text-sm text-muted">Every email also says the contact can reply STOP to be left alone, and we honour it.</p>
      </Card>
      <Card title="What the AI agent may do">
        <fieldset disabled={!canManage || save.isPending} className="space-y-4">
          <label className="block text-sm font-semibold">Mode
            <select className={inputCls} value={cfg.mode} onChange={(e) => setCfg({ ...cfg, mode: e.target.value })}>
              <option value="draft">Drafts only: a person approves every reply</option>
              <option value="policy">By step: automatic for the steps marked Automatic, approval for the rest</option>
            </select>
          </label>
          <table className="w-full text-left text-sm">
            <thead className="text-xs text-muted"><tr><th className="py-1 pr-3">When the outlet's reply needs this</th><th>Reply</th></tr></thead>
            <tbody>
              {data.steps.map((st) => (
                <tr key={st.id} className="border-t border-line">
                  <td className="py-1.5 pr-3">{st.label}{st.never_auto && <span className="ml-2 text-xs text-muted">(payment or account details: always a person)</span>}</td>
                  <td>
                    <select aria-label={`${st.label}: automatic or approval`} className={inputCls} disabled={st.never_auto || cfg.mode === "draft"} value={st.never_auto ? "approve" : cfg.policy[st.id] ?? st.default} onChange={(e) => setCfg({ ...cfg, policy: { ...cfg.policy, [st.id]: e.target.value } })}>
                      <option value="auto">Automatic</option><option value="approve">Needs my approval</option>
                    </select>
                  </td>
                </tr>
              ))}
            </tbody>
          </table>
          <div className="grid gap-4 sm:grid-cols-2">
            <label className="block text-sm font-semibold">Most automatic replies per day<input className={inputCls} type="number" min={0} max={5000} value={cfg.daily_cap} onChange={(e) => setCfg({ ...cfg, daily_cap: Number(e.target.value) })} /></label>
            <label className="block text-sm font-semibold">Replies the agent may write in one conversation<input className={inputCls} type="number" min={1} max={30} value={cfg.ai_turn_limit} onChange={(e) => setCfg({ ...cfg, ai_turn_limit: Number(e.target.value) })} /></label>
          </div>
          <label className="flex items-center gap-2 text-sm"><input type="checkbox" checked={cfg.paused} onChange={(e) => setCfg({ ...cfg, paused: e.target.checked })} /> Pause the agent everywhere (replies still arrive; nobody drafts or sends)</label>
        </fieldset>
        <p className="mt-2 text-sm text-muted">Whatever you choose, the agent never pays anyone, never marks a request paid or published, and holds anything that mentions an amount, bank details, a date, a link, an unexpected sender or an email that looks like it is instructing it.</p>
      </Card>
      <Card title="Email templates">
        <p className="mb-3 text-sm text-muted">Placeholders you can use: {data.variables.map((v) => `{${v}}`).join(", ")}.</p>
        <fieldset disabled={!canManage || save.isPending} className="space-y-4">
          {cfg.templates.map((t, i) => (
            <div key={t.id} className="space-y-2 rounded-lg border border-line p-3">
              <div className="flex flex-wrap items-center justify-between gap-2">
                <label className="block text-sm font-semibold">Name<input className={inputCls} maxLength={80} value={t.name} onChange={(e) => setT(i, { name: e.target.value })} /></label>
                <label className="flex items-center gap-2 text-sm"><input type="radio" name="default-template" checked={cfg.default_template === t.id} onChange={() => setCfg({ ...cfg, default_template: t.id })} /> Used by default</label>
              </div>
              <label className="block text-sm font-semibold">Subject<input className={inputCls} maxLength={250} value={t.subject} onChange={(e) => setT(i, { subject: e.target.value })} /></label>
              <label className="block text-sm font-semibold">Message<textarea className={inputCls} rows={10} value={t.body} onChange={(e) => setT(i, { body: e.target.value })} /></label>
              <Button type="button" variant="secondary" onClick={() => show.mutate(t)}>Preview with sample details</Button>
            </div>
          ))}
        </fieldset>
        <ErrorBox error={show.error ?? save.error} />
        {preview && <div className="mt-3 rounded-lg border border-ink bg-paper p-3 text-sm"><p className="font-semibold">{preview.subject}</p><p className="mt-2 whitespace-pre-wrap">{preview.body}</p></div>}
      </Card>
      {canManage && <Button type="submit" disabled={save.isPending}>{save.isPending ? "Saving…" : "Save outreach settings"}</Button>}
      {save.isSuccess && <Notice tone="ok">Saved.</Notice>}
    </form>
  );
}

function Contacts() {
  const canManage = useCan()("operations.manage");
  const [text, setText] = useState("");
  const [auto, setAuto] = useState(true);
  const check = useMutation({ mutationFn: () => request<{ rows: ContactRow[]; will_change: number }>("admin/outreach/contacts/preview", "POST", { text }) });
  const apply = useMutation({ mutationFn: () => request<{ applied: number }>("admin/outreach/contacts/apply", "POST", { text, enable_automatic: auto }), onSuccess: () => check.reset() });
  return (
    <Card title="Import outlet contacts">
      <p className="mb-3 text-sm text-muted">Paste one outlet per line as <code>outlet, contact name, contact email, template</code> (the template is optional: intro, rates or formal), with or without a header row. CSV, tab-separated or JSON all work. Nothing is saved until you check the list and confirm.</p>
      <label className="block text-sm font-semibold">Contacts<textarea className={inputCls} rows={8} value={text} onChange={(e) => { setText(e.target.value); check.reset(); }} placeholder={"Techpoint Africa, Bayo Ade, bayo@example.com, rates\nPunch, Ada Obi, ada@example.com"} /></label>
      <label className="mt-3 flex items-center gap-2 text-sm"><input type="checkbox" checked={auto} onChange={(e) => setAuto(e.target.checked)} /> Switch on automatic outreach for these outlets, so a request for one contacts it by itself</label>
      <div className="mt-3 flex flex-wrap gap-2">
        <Button type="button" variant="secondary" disabled={!text.trim() || check.isPending} onClick={() => check.mutate()}>Check the list</Button>
        {canManage && <Button type="button" disabled={!check.data || check.data.will_change === 0 || apply.isPending} onClick={() => apply.mutate()}>{apply.isPending ? "Saving…" : `Save ${check.data?.will_change ?? 0} contacts`}</Button>}
      </div>
      <ErrorBox error={check.error ?? apply.error} />
      {apply.isSuccess && <div className="mt-3"><Notice tone="ok">Saved {apply.data.applied} contacts.</Notice></div>}
      {check.data && (
        <div className="mt-4 overflow-x-auto">
          <table className="w-full text-left text-sm">
            <thead className="text-xs text-muted"><tr><th className="py-1 pr-3">Outlet</th><th className="pr-3">Contact</th><th className="pr-3">Email</th><th className="pr-3">Template</th><th>Result</th></tr></thead>
            <tbody>
              {check.data.rows.map((r) => (
                <tr key={r.row} className="border-t border-line">
                  <td className="py-1.5 pr-3">{r.outlet_name ?? r.outlet}</td><td className="pr-3">{r.contact_name}</td><td className="pr-3">{r.contact_email}</td><td className="pr-3">{r.template ?? "default"}</td>
                  <td className={r.status === "ok" ? "font-semibold" : "text-muted"}>{ROW_STATUS[r.status] ?? r.status}</td>
                </tr>
              ))}
            </tbody>
          </table>
        </div>
      )}
    </Card>
  );
}

export function OutreachAdmin() {
  const [tab, setTab] = useState<"inbox" | "settings" | "contacts">("inbox");
  const cfg = useQuery({ queryKey: ["outreach-config"], queryFn: () => request<ConfigOut>("admin/outreach/config"), refetchOnWindowFocus: false });
  const tabBtn = (k: typeof tab, label: string) => <button type="button" aria-pressed={tab === k} className={`min-h-11 rounded border px-4 py-2 text-sm font-semibold ${tab === k ? "border-ink bg-ink text-white" : "border-ink"}`} onClick={() => setTab(k)}>{label}</button>;
  return (
    <div className="space-y-4">
      <div><h1 className="text-2xl font-bold">Outreach to outlets</h1><p className="mt-1 text-sm text-muted">Contact the outlets a paid request names, read their replies and answer them, all in one place.</p></div>
      {cfg.data && !cfg.data.engine_on && <Notice tone="warn">Outreach conversations are switched off (<code>OUTREACH_AI=off</code>), so paid requests still send the original one-way email. You can set up templates and contacts now.</Notice>}
      {cfg.data?.engine_on && !cfg.data.reply_domain && <Notice tone="warn">No reply domain is set (<code>OUTREACH_REPLY_DOMAIN</code>), so replies cannot come back into this inbox yet.</Notice>}
      <ErrorBox error={cfg.error} />
      <div className="flex flex-wrap gap-2" role="group" aria-label="Outreach sections">{tabBtn("inbox", "Conversations")}{tabBtn("settings", "Templates and settings")}{tabBtn("contacts", "Contacts")}</div>
      {tab === "inbox" && <Conversations />}
      {tab === "settings" && cfg.data && <Settings data={cfg.data} />}
      {tab === "contacts" && <Contacts />}
    </div>
  );
}
