import { useEffect, useRef, useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { distributionApi, distributionStatus, type Distribution, type Outlet, type Placement } from "../../lib/distribution";
import { getToken } from "../lib/auth";
import { useCan } from "../lib/can";

const request = <T,>(path: string, method = "GET", body?: unknown) => distributionApi<T>(path, getToken(), method, body);
const input = "mt-1 block min-h-11 w-full min-w-0 rounded border border-line bg-white p-2";
const button = "min-h-11 rounded border border-ink px-3 py-2 text-sm font-semibold disabled:opacity-50";
type ConfigOutlet = Outlet & { direct_access: boolean; contact_name: string; contact_email: string | null; email_subject: string; email_body: string };
type Config = { team_emails: string[]; outlets: ConfigOutlet[]; template_variables: string[] };

function DistributionSettings() {
  const canManage = useCan()("operations.manage");
  const q = useQuery({ queryKey: ["distribution-config"], queryFn: () => request<Config>("admin/distribution/config"), refetchOnWindowFocus: false });
  const [emails, setEmails] = useState("");
  const [outletId, setOutletId] = useState("1");
  const [outlet, setOutlet] = useState<ConfigOutlet | null>(null);
  const [busy, setBusy] = useState(false);
  const [message, setMessage] = useState("");
  const [error, setError] = useState("");
  useEffect(() => { if (q.data) setEmails(q.data.team_emails.join("\n")); }, [q.data]);
  useEffect(() => { setOutlet(q.data?.outlets.find(o => o.id === outletId) ?? null); }, [outletId, q.data]);
  const run = async (fn: () => Promise<unknown>) => { setBusy(true); setError(""); setMessage(""); try { await fn(); await q.refetch(); setMessage("Distribution settings saved."); } catch (e) { setError(String(e)); } finally { setBusy(false); } };
  return <div className="space-y-5 rounded-lg border bg-white p-4 sm:p-6">
    <h2 className="text-xl font-bold">Distribution settings</h2><p className="text-sm text-muted">Recipients, publisher contacts and email templates apply to new submissions. Existing payment breakdowns and sent emails are kept unchanged.</p>
    {(error || q.error) && <p role="alert">{error || String(q.error)}</p>}{message && <p role="status">{message}</p>}
    <form className="space-y-3 border-b pb-5" onSubmit={e => { e.preventDefault(); void run(() => request("admin/distribution/config", "PUT", { team_emails: emails.split(/[\n,;]+/).map(x => x.trim()).filter(Boolean) })); }}>
      <label className="block font-semibold">Team sale notification emails<textarea className={input} rows={3} placeholder="sales@example.com&#10;operations@example.com" value={emails} disabled={!canManage || busy} onChange={e => setEmails(e.target.value)} /></label><p className="text-sm text-muted">One address per line, or separated by commas. Each recipient receives the payment breakdown, customer contact details and announcement. Leave empty to disable team alerts.</p><button className={button} disabled={!canManage || busy}>Save team recipients</button>
    </form>
    <label className="block font-semibold">Configure outlet<select className={input} value={outletId} onChange={e => { setOutletId(e.target.value); setMessage(""); }}>{q.data?.outlets.map(o => <option key={o.id} value={o.id}>{o.name}</option>)}</select></label>
    {outlet && <form className="space-y-4" onSubmit={e => { e.preventDefault(); void run(() => request(`admin/distribution/outlets/${outlet.id}`, "PUT", { ...outlet, contact_email: outlet.contact_email || null })); }}>
      <fieldset disabled={!canManage || busy} className="space-y-4"><legend className="mb-3 font-bold">{outlet.name}: pricing and image policy</legend>
        <div className="grid gap-4 sm:grid-cols-3">{([['credits', 'Placement credits'], ['logo_credits', 'Logo add-on credits'], ['picture_credits', 'Credits per additional picture']] as const).map(([key, label]) => <label key={key} className="block text-sm font-semibold">{label}<input className={input} type="number" min="0" max="1000000" step="0.0001" value={outlet[key] ?? "0"} onChange={e => setOutlet({ ...outlet, [key]: e.target.value })} /></label>)}</div>
        <div className="flex flex-wrap gap-5"><label><input type="checkbox" checked={outlet.accepts_logo !== false} onChange={e => setOutlet({ ...outlet, accepts_logo: e.target.checked })} /> Accepts logos</label><label><input type="checkbox" checked={outlet.accepts_images !== false} onChange={e => setOutlet({ ...outlet, accepts_images: e.target.checked })} /> Accepts additional pictures</label></div>
        <h3 className="font-bold">Publisher contact and automatic outreach</h3><div className="grid gap-4 sm:grid-cols-2"><label className="block text-sm font-semibold">Publisher contact name<input className={input} value={outlet.contact_name} onChange={e => setOutlet({ ...outlet, contact_name: e.target.value })} /></label><label className="block text-sm font-semibold">Publisher contact email<input className={input} type="email" required={outlet.direct_access} value={outlet.contact_email ?? ""} onChange={e => setOutlet({ ...outlet, contact_email: e.target.value })} /></label></div>
        <label className="block"><input type="checkbox" checked={outlet.direct_access} onChange={e => setOutlet({ ...outlet, direct_access: e.target.checked })} /> Automatically email this publisher after a paid submission</label>
        <label className="block text-sm font-semibold">Outreach email subject<input className={input} required maxLength={250} value={outlet.email_subject} onChange={e => setOutlet({ ...outlet, email_subject: e.target.value })} /></label>
        <label className="block text-sm font-semibold">Outreach email body<textarea className={input} required rows={14} value={outlet.email_body} onChange={e => setOutlet({ ...outlet, email_body: e.target.value })} /></label>
        <p className="break-words text-xs text-muted">Supported placeholders: {q.data?.template_variables.map(v => `{${v}}`).join(", ")}. Publisher replies and bank details are handled manually by email. No publisher payment is initiated by this system.</p>
        <button className={button} type="submit">Save outlet settings</button>
      </fieldset>
    </form>}
  </div>;
}

function PlacementEditor({ placement, requestId, refresh }: { placement: Placement; requestId: string; refresh: () => Promise<unknown> }) {
  const canManage = useCan()("operations.manage");
  const [form, setForm] = useState(placement);
  const [dirty, setDirty] = useState(false);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [message, setMessage] = useState("");
  const nonce = useRef(crypto.randomUUID());
  const change = (patch: Partial<Placement>) => { setForm(f => ({ ...f, ...patch })); setDirty(true); setMessage(""); };
  const run = async (fn: () => Promise<void>) => { setBusy(true); setError(""); try { await fn(); await refresh(); } catch (e) { setError(String(e)); } finally { setBusy(false); } };
  return <section className="min-w-0 space-y-4 rounded-lg border-2 border-line p-4" aria-label={`Placement for ${placement.name}`}><h3 className="font-bold">{placement.name} · {placement.credits} credits</h3>
    <div className="grid gap-4 sm:grid-cols-2"><label className="block text-sm font-semibold">Customer-visible status<select className={input} disabled={!canManage || busy} value={form.status} onChange={e => change({ status: e.target.value as Placement["status"] })}><option value="pending">Pending</option><option value="in_progress">In progress</option><option value="published">Published</option></select></label><label className="block text-sm font-semibold">Internal progress (admin only)<select className={input} disabled={!canManage || busy} value={form.internal_status} onChange={e => change({ internal_status: e.target.value })}><option value="not_started">Not started</option><option value="follow_up">Follow-up done</option><option value="payment_made">Publisher payment made</option></select></label></div>
    <label className="block text-sm font-semibold">Published post URL<input className={input} type="url" disabled={!canManage || busy} placeholder="https://publication.com/your-announcement" value={form.published_url} onChange={e => change({ published_url: e.target.value })} /></label><p className="text-xs text-muted">Saving a new URL marks this outlet Published and queues a customer email with the link.</p>
    <label className="block text-sm font-semibold">Internal notes (admin only)<textarea className={input} disabled={!canManage || busy} value={form.internal_notes} onChange={e => change({ internal_notes: e.target.value })} /></label>
    <details className="rounded border border-line p-3"><summary className="cursor-pointer font-semibold">Publisher outreach — edit and preview</summary><div className="mt-3 space-y-3"><label className="block text-sm font-semibold">Recipient email<input className={input} disabled={!canManage || busy} type="email" value={form.contact_email} onChange={e => change({ contact_email: e.target.value })} /></label><label className="block text-sm font-semibold">Message subject<input className={input} disabled={!canManage || busy} value={form.outreach_subject} onChange={e => change({ outreach_subject: e.target.value })} /></label><label className="block text-sm font-semibold">Message body<textarea className={input} rows={10} disabled={!canManage || busy} value={form.outreach_body} onChange={e => change({ outreach_body: e.target.value })} /></label><p className="text-xs text-muted">This is the actual message content. Save edits before sending. Replies are handled outside the platform.</p><button className={button} disabled={!canManage || busy || dirty || !form.contact_email} onClick={() => void run(async () => { await request(`admin/distribution/${requestId}/placements/${placement.id}/outreach`, "POST", { idempotency_key: nonce.current }); nonce.current = crypto.randomUUID(); setMessage("Publisher email queued."); })}>Send publisher email / follow-up</button></div></details>
    <button className={button} disabled={!canManage || busy} onClick={() => void run(async () => { const response = await request<Distribution>(`admin/distribution/${requestId}/placements/${placement.id}`, "PATCH", { status: form.status, internal_status: form.internal_status, internal_notes: form.internal_notes, published_url: form.published_url, contact_email: form.contact_email, outreach_subject: form.outreach_subject, outreach_body: form.outreach_body }); setForm(response.placements!.find(p => p.id === placement.id)!); setDirty(false); setMessage("Outlet progress saved."); })}>Save outlet progress</button>
    {error && <p role="alert">{error}</p>}{message && <p role="status">{message}</p>}
  </section>;
}

function DistributionRecord({ summary }: { summary: Distribution }) {
  const canManage = useCan()("operations.manage");
  const [open, setOpen] = useState(false);
  const [error, setError] = useState("");
  const [assets, setAssets] = useState<{ video_url: string | null; images: { key: string; url: string }[] } | null>(null);
  const q = useQuery({ queryKey: ["admin-distribution", summary.id], queryFn: () => request<Distribution>(`admin/distribution/${summary.id}`), enabled: open, refetchInterval: open ? 15000 : false });
  const r = q.data ?? summary;
  return <details className="min-w-0 rounded border bg-white p-4" onToggle={e => setOpen(e.currentTarget.open)}><summary className="cursor-pointer"><strong>{r.data.headline || "Untitled distribution"}</strong> · {r.created_by} · {distributionStatus(r.status)} · {r.paid ? `Paid ${r.total_credits} credits` : "Unpaid"} · Step: {r.stage}</summary>{open && <div className="mt-4 min-w-0 space-y-4">
    {(error || q.error) && <p role="alert">{error || String(q.error)}</p>}<p className="break-all text-sm">Request {r.id} · Workspace {r.workspace_id}</p><p className="text-sm">Started {new Date(r.created_at).toLocaleString()} · Last activity {new Date(r.updated_at).toLocaleString()}</p><p>Primary contact: {r.data.contact_name || "Not provided"} · {r.data.contact_email} · Phone {r.data.phone}</p><p>Video: {r.data.project_id || "Not selected"}</p>
    <p>Confirmation email: {r.email_sent ? "Sent" : "Queued / not sent"}</p>{r.paid && !r.email_sent && canManage && <button className={button} onClick={() => { void request(`admin/distribution/${r.id}/confirmation`, "POST").then(() => q.refetch()).catch(e => setError(String(e))); }}>Retry confirmation email</button>}
    <p className="max-h-80 overflow-y-auto whitespace-pre-wrap break-words rounded bg-paper p-3">{r.data.announcement || "Announcement not provided"}</p><ul className="space-y-1 text-sm">{r.data.outlets?.map(o => <li key={o.id}>{o.name} — {o.credits} credits (placement {o.base_credits ?? o.credits}; logo {o.logo_fee ?? 0}; pictures {o.picture_fee ?? 0})</li>)}</ul>
    {r.invoice && <p className="break-all text-sm">Receipt / credit invoice: <strong>{r.invoice.number}</strong> · {r.invoice.total_credits} credits · {r.invoice.payment_method}</p>}
    {!r.paid && <p>{r.data.outlet_ids.length} outlets selected. Estimated total: {r.total_credits} credits.</p>}
    <button className={button} onClick={() => { void request<{ video_url: string | null; images: { key: string; url: string }[] }>(`admin/distribution/${r.id}/assets`).then(setAssets).catch(e => setError(String(e))); }}>Load video, logo and pictures</button>{assets && <div>{assets.video_url && <a className="block underline" href={assets.video_url} target="_blank" rel="noreferrer">Download selected video</a>}{assets.images.map((a, i) => <a className="mr-3 inline-block underline" href={a.url} key={a.key} target="_blank" rel="noreferrer">{i === 0 && r.data.logo_key ? "Company logo" : `Picture ${i}`}</a>)}</div>}
    {r.paid && canManage && <label className="block text-sm">Overall status<select aria-label="Distribution status" className={input} value={r.status} onChange={e => { void request(`admin/distribution/${r.id}`, "PATCH", { status: e.target.value }).then(() => q.refetch()).catch(e => setError(String(e))); }}><option value="submitted">Pending</option><option value="in_progress">In progress</option><option value="completed">Published (requires every outlet link)</option></select></label>}
    {r.placements?.map(p => <PlacementEditor key={p.id} placement={p} requestId={r.id} refresh={() => q.refetch()} />)}
    {r.paid && <section className="space-y-3"><h3 className="font-bold">Email delivery log</h3>{!r.emails?.length && <p className="text-sm text-muted">No email records yet.</p>}{r.emails?.map(m => <details key={m.id} className="rounded border border-line p-3"><summary className="cursor-pointer break-words text-sm">{m.kind.replaceAll("_", " ")} · {m.recipient} · {m.status.replaceAll("_", " ")} · {m.attempts} attempts</summary><p className="mt-3 font-semibold">{m.subject}</p><p className="text-xs text-muted">Created {new Date(m.created_at).toLocaleString()}{m.sent_at ? ` · Sent ${new Date(m.sent_at).toLocaleString()}` : ""}</p><pre className="my-3 max-h-80 overflow-y-auto whitespace-pre-wrap break-words text-sm">{m.body}</pre>{m.error && <p role="alert">{m.error}</p>}{canManage && ["failed", "pending"].includes(m.status) && <button className={button} onClick={() => { void request(`admin/distribution/${r.id}/emails/${m.id}/retry`, "POST").then(() => q.refetch()).catch(e => setError(String(e))); }}>Retry this email</button>}</details>)}</section>}
    {!!r.activity?.length && <details className="rounded border border-line p-3"><summary className="cursor-pointer font-semibold">Activity history</summary><ol className="mt-3 max-h-80 space-y-3 overflow-y-auto text-sm">{r.activity.map(a => <li key={a.id}><p>{a.kind.replaceAll("_", " ")} · {a.actor} · {new Date(a.created_at).toLocaleString()}</p><pre className="whitespace-pre-wrap break-words text-xs text-muted">{JSON.stringify(a.detail)}</pre></li>)}</ol></details>}
  </div>}</details>;
}

export function DistributionAdmin() {
  const [filter, setFilter] = useState("all");
  const [tab, setTab] = useState("requests");
  const q = useQuery({ queryKey: ["admin-distribution"], queryFn: () => request<Distribution[]>("admin/distribution"), refetchInterval: 15000 });
  const rows = (q.data ?? []).filter(r => filter === "all" || (filter === "draft" ? !r.paid : r.paid));
  return <div className="space-y-5"><h1 className="text-2xl font-bold">Distribution requests</h1><p>Review drafts, payments, per-outlet progress and publisher communications.</p><nav className="flex gap-3" aria-label="Distribution admin sections"><button className={button} aria-pressed={tab === "requests"} onClick={() => setTab("requests")}>Requests</button><button className={button} aria-pressed={tab === "settings"} onClick={() => setTab("settings")}>Notification and outlet settings</button></nav>
    {tab === "settings" ? <DistributionSettings /> : <><label>Show <select className="rounded border p-2" value={filter} onChange={e => setFilter(e.target.value)}><option value="all">All requests</option><option value="draft">Unpaid drafts</option><option value="paid">Paid submissions</option></select></label>{q.error && <p role="alert">{String(q.error)}</p>}{!rows.length && <p>No matching requests.</p>}{rows.map(r => <DistributionRecord key={r.id} summary={r} />)}</>}
  </div>;
}
