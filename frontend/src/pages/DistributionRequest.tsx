import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError, unwrap } from "../api/client";
import { getToken } from "../lib/auth";
import { distributionApi, type Distribution, type Draft, type Outlet } from "../lib/distribution";
import { DistributionOutlets, DistributionSelection } from "../components/DistributionOutlets";
import { Button, Card, ErrorBox } from "../components/ui";

const steps = ["outlets", "content", "contact", "review"];
const labels = ["Choose outlets", "Video & announcement", "Contact & images", "Review & pay"];
type Video = { id: string; headline: string; announcement: string; video_url: string | null };
const request = <T,>(path: string, method = "GET", body?: unknown) => distributionApi<T>(path, getToken(), method, body);

export function DistributionRequestPage() {
  const [params] = useSearchParams();
  const nav = useNavigate();
  const cache = useQueryClient();
  const id = params.get("draft");
  const project = params.get("project");
  const [row, setRow] = useState<Distribution | null>(null);
  const [draft, setDraft] = useState<Draft | null>(null);
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const [saved, setSaved] = useState("");
  const [view, setView] = useState(false);
  const [success, setSuccess] = useState(false);
  const [topup, setTopup] = useState(false);
  const queue = useRef<Promise<unknown>>(Promise.resolve());
  const submitting = useRef(false);
  const list = useQuery({ queryKey: ["distributions"], queryFn: () => request<Distribution[]>("distribution") });
  const outlets = useQuery({ queryKey: ["distribution-outlets"], queryFn: () => request<{ outlets: Outlet[]; coming_soon: string[] }>("distribution/outlets") });
  const videos = useQuery({ queryKey: ["distribution-videos"], queryFn: () => request<Video[]>("distribution/videos") });
  useEffect(() => {
    let active = true;
    setRow(null); setDraft(null); setError(null); setTopup(false); setSuccess(false);
    if (id) void request<Distribution>(`distribution/${id}`).then(r => { if (active) { setRow(r); setDraft(r.data); } }).catch(e => { if (active) setError(e); });
    return () => { active = false; };
  }, [id]);
  const save = (next: Draft) => {
    if (!row || row.status !== "draft") return Promise.resolve();
    setSaved("Saving…");
    const pending = queue.current.catch(() => undefined).then(() => request<Distribution>(`distribution/${row.id}`, "PUT", next));
    queue.current = pending;
    return pending.then(r => { setRow(r); setSaved("Draft saved"); return r; }).catch(e => { setSaved("Not saved — retry saving before leaving"); setError(e); throw e; });
  };
  // Debounced autosave persists partial steps so operators can see where a draft stopped.
  useEffect(() => {
    if (!draft || !row || row.status !== "draft" || submitting.current) return;
    const timer = setTimeout(() => { if (!submitting.current) void save(draft).catch(() => undefined); }, 650);
    return () => clearTimeout(timer);
    // Saving a response updates row but must not schedule a second save.
  }, [draft, row?.status]);
  const patch = (p: Partial<Draft>) => setDraft(d => d ? { ...d, ...p } : d);
  const create = async () => {
    setBusy(true); setError(null);
    try {
      const r = await request<Distribution>("distribution", "POST");
      const v = videos.data?.find(v => v.id === project);
      if (v) await request(`distribution/${r.id}`, "PUT", { ...r.data, project_id: v.id, headline: v.headline, announcement: v.announcement });
      await cache.invalidateQueries({ queryKey: ["distributions"] });
      nav(`/distribution/request?draft=${r.id}`);
    } catch (e) { setError(e); } finally { setBusy(false); }
  };
  const all = outlets.data?.outlets ?? [];
  const selected = all.filter(o => draft?.outlet_ids.includes(o.id));
  const total = selected.reduce((n, o) => n + Number(o.credits), 0);
  const next = async (step: string) => {
    if (!draft) return;
    const value = { ...draft, stage: step }; setDraft(value); setBusy(true); setError(null);
    try { await save(value); } catch { /* error shown */ } finally { setBusy(false); }
  };
  const upload = async (file: File, logo: boolean) => {
    setBusy(true); setError(null);
    try {
      const signed = await unwrap(api.POST("/v1/brand-kit/uploads", { body: { kind: "product_image", content_type: file.type, size_bytes: file.size } }));
      const response = await fetch(signed.upload_url, { method: "PUT", body: file, headers: { "Content-Type": file.type } });
      if (!response.ok) throw new Error("Upload failed. Please try again.");
      await unwrap(api.POST("/v1/brand-kit/uploads/confirm", { body: { key: signed.key } }));
      patch(logo ? { logo_key: signed.key } : { picture_keys: [...(draft?.picture_keys ?? []), signed.key] });
    } catch (e) { setError(e); } finally { setBusy(false); }
  };
  const submit = async () => {
    if (!draft || !row) return;
    submitting.current = true;
    setBusy(true); setError(null); setTopup(false);
    try {
      await save(draft);
      const r = await request<Distribution>(`distribution/${row.id}/submit`, "POST"); setRow(r); setSuccess(true);
      await cache.invalidateQueries({ queryKey: ["distributions"] });
      await cache.invalidateQueries({ queryKey: ["me"] });
    } catch (e) { setError(e); if (e instanceof ApiError && e.status === 402) setTopup(true); } finally { submitting.current = false; setBusy(false); }
  };
  return <div className="space-y-6 pb-28">
    <div><h1 className="text-3xl font-bold">Distribute your story</h1><p className="mt-2">Want to distribute your video and announcement to over 20,000 media outlets?</p><p className="text-sm text-muted">Choose from the available outlets below. Our team coordinates your request; submission is not a guarantee of publication.</p></div>
    <ErrorBox error={error ?? list.error ?? outlets.error ?? videos.error} />
    {!id && <><Button onClick={() => void create()} disabled={busy || !videos.data || !outlets.data}>Start a distribution request</Button><Card title="Your distribution requests"><ul className="space-y-3">{list.data?.map(r => <li key={r.id}><Link className="underline" to={`/distribution/request?draft=${r.id}`}>{r.data.headline || "Untitled distribution"}</Link> — {r.status} · {r.stage} · {r.paid ? `Paid (${r.total_credits} credits)` : "Unpaid draft"}</li>)}</ul>{list.data?.length === 0 && <p>No requests yet. Your drafts will appear here.</p>}</Card></>}
    {id && !draft && !error && <p>Loading your saved request…</p>}
    {draft && row && <>
      {row.status !== "draft" ? <Card title="Distribution request confirmed"><p>Your request is {row.status.replace("_", " ")}. Payment confirmed: {row.total_credits} credits.</p><p>Someone from the Cover Founder team will reach out within the next 24 hours.</p><p className="mt-2">{row.email_sent ? "Confirmation email sent." : "Your request is saved, but the confirmation email could not be sent. Our team can see your request."}</p><p className="mt-3 font-bold">{draft.headline}</p><p>{row.data.outlets?.map(o => o.name).join(", ")}</p><Link to="/distribution/request" className="underline">All requests</Link></Card> : <>
      <nav aria-label="Distribution steps" className="flex flex-wrap gap-2">{steps.map((s, i) => <Button key={s} variant={draft.stage === s ? "primary" : "secondary"} disabled={busy} onClick={() => void next(s)}>{i + 1}. {labels[i]}</Button>)}</nav>
      <p role="status" className="text-sm">{saved || "Your progress is saved automatically."}</p>
      {draft.stage === "outlets" && <DistributionOutlets outlets={all} selectedIds={draft.outlet_ids} onChange={outlet_ids => patch({ outlet_ids })} comingSoon={outlets.data?.coming_soon ?? []} />}
      {draft.stage === "content" && <Card title="Choose your video and announcement"><label className="block">Completed video<select aria-label="Completed video" className="mt-1 block w-full rounded border p-3" value={draft.project_id ?? ""} onChange={e => { const v = videos.data?.find(v => v.id === e.target.value); patch({ project_id: v?.id ?? null, headline: v?.headline ?? "", announcement: v?.announcement ?? "" }); }}><option value="">Select a completed video</option>{videos.data?.map(v => <option key={v.id} value={v.id}>{v.headline || `Video ${v.id.slice(0, 8)}`}</option>)}</select></label>{videos.data?.length === 0 && <p>Finish a video first. <Link className="underline" to="/ai-newsroom/new">Create a video</Link></p>}{videos.data?.find(v => v.id === draft.project_id)?.video_url && <video aria-label="Selected distribution video" controls preload="metadata" className="mt-4 max-h-80 w-full rounded bg-black" src={videos.data.find(v => v.id === draft.project_id)!.video_url!} />}<p className="my-3 text-sm text-muted">Use the generated announcement or replace it with your own text. Switching video loads that video's announcement.</p><label className="block">Headline<input className="mt-1 block w-full rounded border p-3" value={draft.headline} maxLength={300} onChange={e => patch({ headline: e.target.value })} /></label><label className="mt-4 block">Press announcement<textarea aria-label="Press announcement" className="mt-1 block w-full rounded border p-3" rows={14} value={draft.announcement} maxLength={50000} onChange={e => patch({ announcement: e.target.value })} /></label></Card>}
      {draft.stage === "contact" && <Card title="Primary contact and company images"><p className="mb-3 text-sm">These details help our team coordinate the release with you.</p>{([['contact_name', 'Contact name', 'text'], ['contact_email', 'Contact email', 'email'], ['phone', 'Primary phone number', 'tel'], ['whatsapp', 'WhatsApp number', 'tel']] as const).map(([key, label, type]) => <label key={key} className="mb-3 block">{label}<input type={type} className="mt-1 block w-full rounded border p-3" value={draft[key]} onChange={e => patch({ [key]: e.target.value })} /></label>)}<label className="mt-4 block">Company logo (required, PNG/JPEG, up to 5 MB)<input type="file" accept="image/png,image/jpeg" disabled={busy} onChange={e => { const f = e.target.files?.[0]; if (f) void upload(f, true); e.target.value = ""; }} /></label>{draft.logo_key && <p className="text-sm">Company logo uploaded ✓</p>}<label className="mt-4 block">Additional pictures (optional, up to 10, PNG/JPEG, 5 MB each)<input type="file" accept="image/png,image/jpeg" disabled={busy || draft.picture_keys.length >= 10} onChange={e => { const f = e.target.files?.[0]; if (f) void upload(f, false); e.target.value = ""; }} /></label><ul>{draft.picture_keys.map((k, i) => <li key={k}>Picture {i + 1} uploaded <button className="underline" onClick={() => patch({ picture_keys: draft.picture_keys.filter(x => x !== k) })}>Remove picture {i + 1}</button></li>)}</ul></Card>}
      {draft.stage === "review" && <Card title="Review your distribution request"><h3 className="font-bold">{draft.headline || "Add a headline"}</h3><p className="mt-3 whitespace-pre-wrap">{draft.announcement || "Add your announcement"}</p><p className="mt-4">Video: {videos.data?.find(v => v.id === draft.project_id)?.headline || draft.project_id || "Not selected"}</p><p>Contact: {draft.contact_name} · {draft.contact_email}</p><p>Phone: {draft.phone} · WhatsApp: {draft.whatsapp}</p><p>Logo: {draft.logo_key ? "Uploaded" : "Required"} · Additional pictures: {draft.picture_keys.length}</p><ul className="my-4">{selected.map(o => <li key={o.id}>{o.name} — {o.credits} credits</li>)}</ul><p className="font-bold">Total: {total} credits</p><p className="mb-4 text-sm">Confirming deducts this total from your wallet. Our team will contact you within 24 hours.</p><Button disabled={busy} onClick={() => void submit()}>Pay and submit</Button>{topup && <p role="alert" className="mt-4">Your draft is saved. <Link className="underline" to={`/billing?returnTo=${encodeURIComponent(`/distribution/request?draft=${row.id}`)}`}>Top up your wallet</Link>, then return to this request.</p>}</Card>}
      <div className="flex gap-3"><Button disabled={busy} variant="secondary" onClick={() => { setBusy(true); void save(draft).catch(() => undefined).finally(() => setBusy(false)); }}>Save draft</Button>{draft.stage !== "review" && draft.stage !== "outlets" && <Button disabled={busy} onClick={() => void next(steps[Math.min(3, steps.indexOf(draft.stage) + 1)])}>Continue</Button>}<Link to="/distribution/request" className="self-center underline">All requests</Link></div>
      <aside aria-label="Selected outlets" className="fixed bottom-[max(0.75rem,env(safe-area-inset-bottom))] left-3 right-3 z-20 mx-auto flex max-w-2xl md:left-[17rem] flex-wrap items-center justify-between gap-3 rounded-xl border-2 border-ink bg-white/95 p-3 shadow-xl backdrop-blur-sm sm:px-5"><span className="text-sm"><strong className="tabular-nums">{selected.length} selected</strong><span className="ml-2 text-muted">· {total} credits</span></span><div className="flex gap-2"><Button variant="secondary" onClick={() => setView(true)}>View selection</Button>{draft.stage === "outlets" && <Button disabled={busy || selected.length === 0} onClick={() => void next("content")}>Continue</Button>}</div></aside>
      </>}
    </>}
    {view && <DistributionSelection selected={selected} onRemove={id => patch({ outlet_ids: draft?.outlet_ids.filter(x => x !== id) ?? [] })} onClose={() => setView(false)} />}
    {success && <div role="dialog" aria-modal="true" aria-label="Distribution submitted" className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"><div className="max-w-lg rounded bg-white p-6"><h2 className="text-2xl font-bold">Your distribution request is confirmed</h2><p className="my-4">Someone from the Cover Founder team will reach out within the next 24 hours.</p><Button onClick={() => setSuccess(false)}>Done</Button></div></div>}
  </div>;
}
