import { useEffect, useRef, useState } from "react";
import { Link, useNavigate, useSearchParams } from "react-router-dom";
import { useQuery, useQueryClient } from "@tanstack/react-query";
import { api, ApiError, unwrap } from "../api/client";
import { getToken } from "../lib/auth";
import { distributionApi, distributionStatus, priceOutlets, type Distribution, type Draft, type Outlet } from "../lib/distribution";
import { CountryPhoneInput } from "../components/CountryPhoneInput";
import { DistributionLogoUpload } from "../components/DistributionLogoUpload";
import { validateDistributionStep, type DistributionErrors } from "../lib/distributionValidation";
import { DistributionOutlets, DistributionSelection } from "../components/DistributionOutlets";
import { DistributionProgress } from "../components/DistributionProgress";
import { DistributionMediaOptions } from "../components/DistributionMediaOptions";
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
  const [fieldErrors, setFieldErrors] = useState<DistributionErrors>({});
  const [uploadKind, setUploadKind] = useState<"logo" | "picture" | null>(null);
  const [logoPreview, setLogoPreview] = useState("");
  const validationSummary = useRef<HTMLDivElement>(null);
  const [saved, setSaved] = useState("");
  const [view, setView] = useState(false);
  const [success, setSuccess] = useState(false);
  const [topup, setTopup] = useState(false);
  const queue = useRef<Promise<unknown>>(Promise.resolve());
  const submitting = useRef(false);
  const list = useQuery({ queryKey: ["distributions"], queryFn: () => request<Distribution[]>("distribution"), refetchInterval: 15000 });
  const outlets = useQuery({ queryKey: ["distribution-outlets"], queryFn: () => request<{ outlets: Outlet[]; coming_soon: string[]; quote_version: string }>("distribution/outlets") });
  const videos = useQuery({ queryKey: ["distribution-videos"], queryFn: () => request<Video[]>("distribution/videos") });
  const stories = useQuery({ queryKey: ["distribution-stories"], queryFn: () => request<{ project_id: string; headline: string; announcement: string }[]>("distribution/stories") });
  const images = useQuery({ queryKey: ["distribution-images", draft?.logo_key], queryFn: () => unwrap(api.GET("/v1/brand-kit/assets")), enabled: !!draft?.logo_key });
  useEffect(() => {
    let active = true;
    setRow(null); setDraft(null); setError(null); setTopup(false); setSuccess(false); setFieldErrors({}); setLogoPreview("");
    if (id) void request<Distribution>(`distribution/${id}`).then(r => { if (active) { setRow(r); setDraft(r.data); } }).catch(e => { if (active) setError(e); });
    return () => { active = false; };
  }, [id]);
  useEffect(() => {
    if (!id || !row?.paid) return;
    const timer = setInterval(() => { void request<Distribution>(`distribution/${id}`).then(r => { setRow(r); setDraft(r.data); }).catch(() => undefined); }, row.email_sent ? 15000 : 2000);
    return () => clearInterval(timer);
  }, [id, row?.paid, row?.email_sent]);
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
  const patch = (p: Partial<Draft>) => {
    setDraft(d => d ? { ...d, ...p } : d);
    setFieldErrors(previous => { const next = { ...previous }; for (const key of Object.keys(p)) delete next[key as keyof Draft]; return next; });
  };
  const showValidation = (errors: DistributionErrors, stage: string) => {
    setFieldErrors(errors);
    setDraft(d => d ? { ...d, stage } : d);
    requestAnimationFrame(() => { validationSummary.current?.focus(); validationSummary.current?.scrollIntoView({ behavior: "auto", block: "center" }); });
  };
  const fieldError = (key: keyof Draft) => fieldErrors[key] ? <p id={`distribution-error-${key}`} className="mt-1 text-sm font-semibold text-red-800">{fieldErrors[key]}</p> : null;
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
  const selected = priceOutlets(all, draft);
  const total = Number(selected.reduce((n, o) => n + Number(o.credits), 0).toFixed(4));
  const next = async (step: string) => {
    if (!draft) return;
    if (steps.indexOf(step) > steps.indexOf(draft.stage)) {
      for (const earlier of steps.slice(0, steps.indexOf(step))) {
        const errors = validateDistributionStep(draft, earlier);
        if (Object.keys(errors).length) { showValidation(errors, earlier); return; }
      }
    }
    setFieldErrors({});
    const value = { ...draft, stage: step }; setDraft(value); setBusy(true); setError(null);
    try { await save(value); } catch { /* error shown */ } finally { setBusy(false); }
  };
  const upload = async (file: File, logo: boolean) => {
    const invalid = !["image/png", "image/jpeg"].includes(file.type) ? "Choose a PNG or JPEG image." : file.size > 5 * 1024 * 1024 ? "Choose an image smaller than 5 MB." : file.size === 0 ? "That file is empty. Choose another image." : "";
    if (invalid) { if (logo) setFieldErrors(e => ({ ...e, logo_key: invalid })); else setError(new Error(invalid)); return; }
    setBusy(true); setError(null); setUploadKind(logo ? "logo" : "picture");
    try {
      const signed = await unwrap(api.POST("/v1/brand-kit/uploads", { body: { kind: "product_image", content_type: file.type, size_bytes: file.size } }));
      const response = await fetch(signed.upload_url, { method: "PUT", body: file, headers: { "Content-Type": file.type } });
      if (!response.ok) throw new Error("Upload failed. Please try again.");
      const asset = await unwrap(api.POST("/v1/brand-kit/uploads/confirm", { body: { key: signed.key } }));
      if (logo) setLogoPreview(asset.url ?? "");
      patch(logo ? { logo_key: signed.key } : { picture_keys: [...(draft?.picture_keys ?? []), signed.key] });
    } catch (e) { if (logo) setFieldErrors(v => ({ ...v, logo_key: e instanceof Error ? e.message : "Logo upload failed. Please try again." })); else setError(e); } finally { setBusy(false); setUploadKind(null); }
  };
  const submit = async () => {
    if (!draft || !row) return;
    for (const step of steps.slice(0, 3)) {
      const errors = validateDistributionStep(draft, step);
      if (Object.keys(errors).length) { showValidation(errors, step); return; }
    }
    submitting.current = true;
    setBusy(true); setError(null); setTopup(false);
    try {
      await save(draft);
      const r = await request<Distribution>(`distribution/${row.id}/submit`, "POST", { expected_total: String(total), quote_version: outlets.data?.quote_version }); setRow(r); setSuccess(true);
      await cache.invalidateQueries({ queryKey: ["distributions"] });
      await cache.invalidateQueries({ queryKey: ["me"] });
    } catch (e) { setError(e); if (e instanceof ApiError && e.status === 402) setTopup(true); if (e instanceof ApiError && e.status === 409) { await outlets.refetch(); } } finally { submitting.current = false; setBusy(false); }
  };
  return <div className="space-y-6 pb-28">
    <div><h1 className="text-3xl font-bold">Distribute your story</h1><p className="mt-2">Want to distribute your video and announcement to over 20,000 media outlets?</p><p className="text-sm text-muted">Choose from the available outlets below. Our team coordinates your request; submission is not a guarantee of publication.</p></div>
    <ErrorBox error={error ?? list.error ?? outlets.error ?? videos.error} />
    {!id && <><Button onClick={() => void create()} disabled={busy || !videos.data || !outlets.data}>Start a distribution request</Button><Card title="Your distribution requests"><ul className="space-y-3">{list.data?.map(r => <li key={r.id}><Link className="underline" to={`/distribution/request?draft=${r.id}`}>{r.data.headline || "Untitled distribution"}</Link> — {distributionStatus(r.status)} · {r.stage} · {r.paid ? `Paid (${r.total_credits} credits)` : "Unpaid draft"}</li>)}</ul>{list.data?.length === 0 && <p>No requests yet. Your drafts will appear here.</p>}</Card></>}
    {id && !draft && !error && <p>Loading your saved request…</p>}
    {draft && row && <>
      {row.status !== "draft" ? <DistributionProgress request={row} /> : <>
      <nav aria-label="Distribution steps" className="flex flex-wrap gap-2">{steps.map((s, i) => <Button key={s} variant={draft.stage === s ? "primary" : "secondary"} disabled={busy} onClick={() => void next(s)}>{i + 1}. {labels[i]}</Button>)}</nav>
      {Object.keys(fieldErrors).length > 0 && <div ref={validationSummary} tabIndex={-1} role="alert" className="rounded-lg border-2 border-brand-red bg-red-tint p-4 focus-visible:outline-2 focus-visible:outline-brand-purple"><p className="font-bold">Complete the required details before continuing.</p><ul className="mt-2 list-inside list-disc text-sm">{Object.values(fieldErrors).map(message => <li key={message}>{message}</li>)}</ul></div>}
      <p role="status" className="text-sm">{saved || "Your progress is saved automatically."}</p>
      {draft.stage === "outlets" && fieldError("outlet_ids")}
      {draft.stage === "outlets" && <DistributionOutlets outlets={all.map(o => selected.find(s => s.id === o.id) ?? o)} selectedIds={draft.outlet_ids} onChange={outlet_ids => patch({ outlet_ids })} comingSoon={outlets.data?.coming_soon ?? []} />}
      {draft.stage === "content" && <Card title="Choose your video and announcement">
        <label className="block font-semibold">Completed video<select aria-label="Completed video" aria-invalid={!!fieldErrors.project_id} aria-describedby={fieldErrors.project_id ? "distribution-error-project_id" : undefined} className="mt-2 block min-h-12 w-full rounded-lg border border-ink p-3 font-normal" value={draft.project_id ?? ""} onChange={e => patch({ project_id: e.target.value || null })}><option value="">Select a completed video</option>{videos.data?.map(v => <option key={v.id} value={v.id}>{v.headline || `Video ${v.id.slice(0, 8)}`}</option>)}</select></label>{fieldError("project_id")}
        {videos.data?.length === 0 && <p>Finish a video first. <Link className="underline" to="/ai-newsroom/new">Create a video</Link></p>}
        {videos.data?.find(v => v.id === draft.project_id)?.video_url && <video aria-label="Selected distribution video" controls preload="metadata" className="mt-4 max-h-72 w-full rounded-lg bg-black" src={videos.data.find(v => v.id === draft.project_id)!.video_url!} />}
        <fieldset className="mt-6"><legend className="font-bold">Where should your announcement come from?</legend><div className="mt-3 grid gap-3 sm:grid-cols-2">{([['platform', 'Choose a Cover Founder story', 'Use a story you have already written on the platform.'], ['custom', 'Write or paste my own', 'Provide your own announcement, or edit the text below.']] as const).map(([value, title, hint]) => <label key={value} className={`flex cursor-pointer items-start gap-3 rounded-lg border-2 p-4 ${(draft.announcement_source ?? "custom") === value ? "border-ink bg-brand-green/15" : "border-line"}`}><input type="radio" name="announcement-source" value={value} checked={(draft.announcement_source ?? "custom") === value} onChange={() => patch({ announcement_source: value, ...(value === "custom" ? { story_project_id: null } : {}) })} className="mt-1 h-5 w-5 accent-ink" /><span><strong className="block text-sm">{title}</strong><span className="mt-1 block text-sm text-muted">{hint}</span></span></label>)}</div></fieldset>
        {draft.announcement_source === "platform" && <div className="mt-4 rounded-lg border border-line bg-paper p-4"><label className="block font-semibold">Platform story<select aria-label="Platform story" aria-invalid={!!fieldErrors.story_project_id} aria-describedby={fieldErrors.story_project_id ? "distribution-error-story_project_id" : undefined} disabled={stories.isLoading} className="mt-2 block min-h-12 w-full rounded-lg border border-ink bg-white p-3 font-normal" value={draft.story_project_id ?? ""} onChange={e => { const story = stories.data?.find(x => x.project_id === e.target.value); patch({ story_project_id: story?.project_id ?? null, headline: story?.headline ?? "", announcement: story?.announcement ?? "" }); }}><option value="">Select a story written on Cover Founder</option>{stories.data?.map(story => <option key={story.project_id} value={story.project_id}>{story.headline || "Untitled story"}</option>)}</select></label>{fieldError("story_project_id")}<ErrorBox error={stories.error} />{stories.data?.length === 0 && <p className="mt-2 text-sm">You have no written stories yet. Choose “Write or paste my own” to provide your announcement.</p>}<p className="mt-2 text-sm text-muted">The story can be from a different project than your video. You can edit the selected text before submitting.</p></div>}
        <label className="mt-5 block font-semibold">Headline<input aria-label="Headline" aria-invalid={!!fieldErrors.headline} aria-describedby={fieldErrors.headline ? "distribution-error-headline" : undefined} className="mt-2 block w-full rounded-lg border border-ink p-3 font-normal" value={draft.headline} maxLength={300} onChange={e => patch({ headline: e.target.value })} /></label>{fieldError("headline")}
        <label className="mt-4 block font-semibold">Press announcement<textarea aria-label="Press announcement" aria-invalid={!!fieldErrors.announcement} aria-describedby={fieldErrors.announcement ? "distribution-error-announcement" : undefined} className="mt-2 block max-h-96 min-h-56 w-full resize-y rounded-lg border border-ink p-3 font-normal leading-relaxed" rows={9} value={draft.announcement} maxLength={50000} onChange={e => patch({ announcement: e.target.value })} /></label>{fieldError("announcement")}
      </Card>}
      {draft.stage === "contact" && <Card title="Primary contact and company images"><p className="mb-4 text-sm text-muted">These details help our team coordinate the release with you. All contact fields and your company logo are required.</p><div className="grid gap-4 sm:grid-cols-2">{([['contact_name', 'Contact name', 'text'], ['contact_email', 'Contact email', 'email']] as const).map(([key, label, type]) => <div key={key}><label className="block font-semibold">{label}<input type={type} aria-invalid={!!fieldErrors[key]} aria-describedby={fieldErrors[key] ? `distribution-error-${key}` : undefined} className="mt-2 block min-h-12 w-full rounded-lg border border-ink p-3 font-normal" value={draft[key]} onChange={e => patch({ [key]: e.target.value })} /></label>{fieldError(key)}</div>)}{([['phone', 'Primary phone number'], ['whatsapp', 'WhatsApp number']] as const).map(([key, label]) => <CountryPhoneInput key={key} id={key} label={label} value={draft[key]} country={draft[`${key}_country`]} error={fieldErrors[key]} onChange={(number, country) => patch({ [key]: number, [`${key}_country`]: country })} />)}</div>
        <DistributionLogoUpload value={draft.logo_key} url={logoPreview || images.data?.find(image => image.key === draft.logo_key)?.url || undefined} busy={busy} uploading={uploadKind === "logo"} error={fieldErrors.logo_key} onUpload={file => void upload(file, true)} onRemove={() => { patch({ logo_key: "" }); setLogoPreview(""); }} />
        <label className="mt-6 block font-semibold">Additional pictures (optional, up to 10, PNG/JPEG, 5 MB each)<input className="mt-3 block w-full rounded-lg border border-line p-3 text-sm file:mr-3 file:rounded file:border-0 file:bg-paper file:px-3 file:py-2 file:font-semibold" type="file" accept="image/png,image/jpeg" disabled={busy || draft.picture_keys.length >= 10} onChange={e => { const f = e.target.files?.[0]; if (f) void upload(f, false); e.target.value = ""; }} /></label><ul className="mt-3 space-y-2">{draft.picture_keys.map((k, i) => <li key={k} className="flex items-center justify-between rounded border border-line p-3 text-sm">Picture {i + 1} uploaded <button className="min-h-10 font-semibold underline" onClick={() => patch({ picture_keys: draft.picture_keys.filter(x => x !== k) })}>Remove picture {i + 1}</button></li>)}</ul>
      </Card>}
      {draft.stage === "contact" && <DistributionMediaOptions outlets={selected} draft={draft} onChange={media_options => patch({ media_options })} />}
      {draft.stage === "review" && <section aria-labelledby="distribution-review-title" className="space-y-4"><h2 id="distribution-review-title" className="text-xl font-bold">Review your distribution request</h2><div className="grid items-start gap-4 lg:grid-cols-[minmax(0,1.4fr)_minmax(0,1fr)]">
        <Card title="Announcement"><div role="region" aria-label="Announcement preview" tabIndex={0} className="max-h-96 overflow-y-auto overscroll-contain rounded-lg border border-line bg-paper p-4 [overflow-wrap:anywhere] [scrollbar-gutter:stable] focus-visible:outline-2 focus-visible:outline-brand-purple sm:p-5"><h3 className="text-lg font-bold leading-snug">{draft.headline}</h3><div className="mt-4 space-y-4 text-sm leading-7">{draft.announcement.split(/\n\s*\n/).filter(p => p.trim()).map((paragraph, i) => <p key={i} className="whitespace-pre-wrap">{paragraph}</p>)}</div></div><button className="mt-3 min-h-11 text-sm font-bold underline" onClick={() => void next("content")}>Edit announcement</button></Card>
        <div className="min-w-0 space-y-4"><Card title="Video and primary contact"><dl className="space-y-3 text-sm [overflow-wrap:anywhere]"><div><dt className="font-bold">Video</dt><dd>{videos.data?.find(v => v.id === draft.project_id)?.headline || draft.project_id}</dd></div><div><dt className="font-bold">Contact</dt><dd>{draft.contact_name}</dd><dd>{draft.contact_email}</dd></div><div><dt className="font-bold">Phone / WhatsApp</dt><dd>{draft.phone} / {draft.whatsapp}</dd></div><div><dt className="font-bold">Company images</dt><dd>{draft.logo_key ? "Logo uploaded" : "Logo required"} · {draft.picture_keys.length} additional pictures</dd></div></dl><button className="mt-3 min-h-11 text-sm font-bold underline" onClick={() => void next("contact")}>Edit contact and images</button></Card><Card title="Outlets and payment"><ul aria-label="Distribution cost breakdown" className="max-h-48 space-y-2 overflow-y-auto overscroll-contain pr-1 text-sm [scrollbar-gutter:stable]">{selected.map(o => <li key={o.id} className="flex justify-between gap-3 border-b border-line pb-2"><span className="min-w-0 break-words">{o.name}<span className="mt-1 block text-xs text-muted">Placement {o.base_credits} · Logo {o.logo_fee} · Pictures {o.picture_fee} credits</span></span><span className="shrink-0">{o.credits} credits</span></li>)}</ul><p className="my-4 flex justify-between border-t-2 border-ink pt-3 font-bold"><span>Total</span><span>{total} credits</span></p><p className="mb-4 text-sm text-muted">Confirming deducts this total from your wallet. Our team will contact you within 24 hours.</p><Button className="w-full" disabled={busy} onClick={() => void submit()}>Pay and submit</Button>{topup && <p role="alert" className="mt-4">Your draft is saved. <Link className="underline" to={`/billing?returnTo=${encodeURIComponent(`/distribution/request?draft=${row.id}`)}`}>Top up your wallet</Link>, then return to this request.</p>}</Card></div>
      </div></section>}
      <div className="flex gap-3"><Button disabled={busy} variant="secondary" onClick={() => { setBusy(true); void save(draft).catch(() => undefined).finally(() => setBusy(false)); }}>Save draft</Button>{draft.stage !== "review" && draft.stage !== "outlets" && <Button disabled={busy} onClick={() => void next(steps[Math.min(3, steps.indexOf(draft.stage) + 1)])}>Continue</Button>}<Link to="/distribution/request" className="self-center underline">All requests</Link></div>
      <aside aria-label="Selected outlets" className="fixed bottom-[max(0.75rem,env(safe-area-inset-bottom))] left-3 right-3 z-20 mx-auto flex max-w-2xl md:left-[17rem] flex-wrap items-center justify-between gap-3 rounded-xl border-2 border-ink bg-white/95 p-3 shadow-xl backdrop-blur-sm sm:px-5"><span className="text-sm"><strong className="tabular-nums">{selected.length} selected</strong><span className="ml-2 text-muted">· {total} credits</span></span><div className="flex gap-2"><Button variant="secondary" onClick={() => setView(true)}>View selection</Button>{draft.stage === "outlets" && <Button disabled={busy} onClick={() => void next("content")}>Continue</Button>}</div></aside>
      </>}
    </>}
    {view && <DistributionSelection selected={selected} onRemove={id => patch({ outlet_ids: draft?.outlet_ids.filter(x => x !== id) ?? [] })} onClose={() => setView(false)} />}
    {success && <div role="dialog" aria-modal="true" aria-label="Distribution submitted" className="fixed inset-0 z-50 flex items-center justify-center bg-black/50 p-4"><div className="max-w-lg rounded bg-white p-6"><h2 className="text-2xl font-bold">Your distribution request is confirmed</h2><p className="my-4">Someone from the Cover Founder team will reach out within the next 24 hours.</p><Button onClick={() => setSuccess(false)}>Done</Button></div></div>}
  </div>;
}
