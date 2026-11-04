import { type ReactNode, useRef, useState } from "react";
import { api, ApiError, unwrap } from "../api/client";
import { getToken } from "../lib/auth";
import { DETAILS_MAX_WORDS, KINDS } from "../lib/announcement";
import { distributionApi, type Distribution } from "../lib/distribution";
import { countWords, limitWords } from "../lib/words";
import { Button, Card, ErrorBox, Field, inputCls, Notice } from "./ui";

// Distribution without a video: how the request begins when someone only wants to send a press release.
// 1. Write it from the same details a video starts with, or upload the one they already have.
// 2. Edit it. 3. Add pictures. Then the usual steps take over: outlets, contact, review and payment.

type Release = { headline: string; announcement: string; unverified: string[] };
type Picture = { key: string; url: string };
type Step = "choose" | "write" | "upload" | "edit" | "pictures";

const request = <T,>(path: string, method = "GET", body?: unknown) => distributionApi<T>(path, getToken(), method, body);

async function readFile(file: File): Promise<{ headline: string; announcement: string }> {
  const r = await fetch(`${import.meta.env.VITE_API_URL ?? ""}/v1/distribution/press-release/read?filename=${encodeURIComponent(file.name)}`, { method: "POST", headers: { Authorization: `Bearer ${getToken() ?? ""}`, "Content-Type": "application/octet-stream" }, body: file });
  const data = await r.json().catch(() => ({}));
  if (!r.ok) throw new ApiError(r.status, typeof data.detail === "string" ? data.detail : "We couldn't read that file. Paste the text instead.");
  return data;
}

export function DistributionStart({ videoPath, onCreated }: { videoPath: ReactNode; onCreated: (id: string) => void }) {
  const [step, setStep] = useState<Step>("choose");
  const [error, setError] = useState<unknown>(null);
  const [busy, setBusy] = useState(false);
  const [kind, setKind] = useState("product_launch");
  const [details, setDetails] = useState("");
  const [first, setFirst] = useState("");
  const [last, setLast] = useState("");
  const [role, setRole] = useState("");
  const [company, setCompany] = useState("");
  const [city, setCity] = useState("");
  const [country, setCountry] = useState("");
  const [website, setWebsite] = useState("");
  const [release, setRelease] = useState<Release>({ headline: "", announcement: "", unverified: [] });
  const [fromAi, setFromAi] = useState(false);
  const [pictures, setPictures] = useState<Picture[]>([]);
  const file = useRef<HTMLInputElement>(null);

  const run = async (work: () => Promise<void>) => { setBusy(true); setError(null); try { await work(); } catch (e) { setError(e); } finally { setBusy(false); } };

  const write = () => run(async () => {
    const r = await request<Release & { kind: string }>("distribution/press-release", "POST", { kind, details: details.trim(), first_name: first.trim(), last_name: last.trim(), role: role.trim(), company: company.trim(), city: city.trim(), country: country.trim(), website: website.trim() });
    setRelease({ headline: r.headline, announcement: r.announcement, unverified: r.unverified ?? [] });
    setFromAi(true);
    setStep("edit");
  });

  const upload = (f: File | undefined) => { if (f) void run(async () => { const r = await readFile(f); setRelease({ headline: r.headline, announcement: r.announcement, unverified: [] }); setFromAi(false); setStep("edit"); }); };

  const addPicture = (f: File | undefined) => {
    if (!f) return;
    const invalid = !["image/png", "image/jpeg"].includes(f.type) ? "Choose a PNG or JPEG image." : f.size > 5 * 1024 * 1024 ? "Choose an image smaller than 5 MB." : f.size === 0 ? "That file is empty. Choose another image." : pictures.length >= 10 ? "You can add up to 10 pictures." : "";
    if (invalid) { setError(new Error(invalid)); return; }
    void run(async () => {
      const signed = await unwrap(api.POST("/v1/brand-kit/uploads", { body: { kind: "product_image", content_type: f.type, size_bytes: f.size } }));
      const put = await fetch(signed.upload_url, { method: "PUT", body: f, headers: { "Content-Type": f.type } });
      if (!put.ok) throw new Error("Upload failed. Please try again.");
      const asset = await unwrap(api.POST("/v1/brand-kit/uploads/confirm", { body: { key: signed.key } }));
      setPictures(p => [...p, { key: signed.key, url: asset.url ?? "" }]);
    });
  };

  // The draft is only made now, with the press release and the pictures in it; the usual steps carry on from the outlets.
  const toOutlets = () => run(async () => {
    const created = await request<Distribution>("distribution", "POST");
    await request(`distribution/${created.id}`, "PUT", { ...created.data, headline: release.headline.trim(), announcement: release.announcement.trim(), announcement_source: "custom", project_id: null, story_project_id: null, picture_keys: pictures.map(p => p.key), stage: "outlets" });
    onCreated(created.id);
  });

  const writeReady = details.trim().length >= 20 && first.trim() && last.trim() && role.trim() && company.trim() && city.trim() && country.trim();
  const words = countWords(details);
  const editReady = release.headline.trim().length > 0 && release.announcement.trim().length > 0;

  if (step === "choose") return (
    <div className="space-y-4">
      <h2 className="text-xl font-bold">How do you want to start?</h2>
      <div className="grid gap-4 md:grid-cols-3">
        <Card title="Use a video or story">
          <p className="text-sm text-muted">Send a video and announcement you made on Cover Founder, or the most recent story, to the outlets you choose.</p>
          <div className="mt-4">{videoPath}</div>
        </Card>
        <Card title="Write my press release">
          <p className="text-sm text-muted">No video needed. Give us the same details you would for a video and we write the press release. You can edit it.</p>
          <div className="mt-4"><Button onClick={() => setStep("write")}>Write my press release</Button></div>
        </Card>
        <Card title="Upload my own">
          <p className="text-sm text-muted">Already have a press release? Upload it (Word, PDF or text) and edit it here if you need to.</p>
          <div className="mt-4"><Button variant="secondary" onClick={() => setStep("upload")}>Upload my press release</Button></div>
        </Card>
      </div>
    </div>
  );

  return (
    <div className="space-y-4">
      <p className="text-sm font-semibold" aria-label="Progress">
        {["write", "upload"].includes(step) ? "Step 1 of 3: Your press release" : step === "edit" ? "Step 2 of 3: Check and edit your press release" : "Step 3 of 3: Add pictures"}
      </p>
      <ErrorBox error={error} />

      {step === "write" && (
        <Card title="Tell us about your announcement">
          <form className="space-y-5" onSubmit={(e) => { e.preventDefault(); if (writeReady && !busy) void write(); }}>
            <fieldset className="space-y-2">
              <legend className="text-sm font-semibold">What are you announcing?</legend>
              <div role="radiogroup" aria-label="Announcement type" className="grid gap-2 sm:grid-cols-3">
                {KINDS.map(([id, label, hint]) => (
                  <button key={id} type="button" role="radio" aria-checked={kind === id} onClick={() => setKind(id)} className={`rounded-sm border-2 p-3 text-left text-sm ${kind === id ? "border-brand-purple bg-lilac" : "border-ink bg-white"}`}>
                    <span className="block font-bold">{label}</span><span className="text-muted">{hint}</span>
                  </button>
                ))}
              </div>
            </fieldset>
            <Field label="Tell us the key details" hint={`Who you are, what is happening, who it is for, and any facts you want featured (amounts, dates, names). A few sentences is enough, and the most we take is ${DETAILS_MAX_WORDS} words. At least 20 characters.`}>
              {(id) => <>
                <textarea id={id} required minLength={20} maxLength={4000} rows={6} className={inputCls} value={details} onChange={(e) => setDetails(limitWords(e.target.value, DETAILS_MAX_WORDS))} />
                <p aria-live="polite" className={`mt-1 text-right text-xs ${words >= DETAILS_MAX_WORDS ? "font-semibold text-ink" : "text-muted"}`}>{words} / {DETAILS_MAX_WORDS} words{words >= DETAILS_MAX_WORDS ? " (limit reached)" : ""}</p>
              </>}
            </Field>
            <div className="grid gap-3 sm:grid-cols-2">
              <Field label="First name" hint="Quoted in the press release.">{(id) => <input id={id} required maxLength={100} autoComplete="given-name" className={inputCls} value={first} onChange={(e) => setFirst(e.target.value)} />}</Field>
              <Field label="Last name">{(id) => <input id={id} required maxLength={100} autoComplete="family-name" className={inputCls} value={last} onChange={(e) => setLast(e.target.value)} />}</Field>
              <Field label="Role" hint="For example CEO.">{(id) => <input id={id} required maxLength={100} placeholder="CEO" className={`${inputCls} uppercase`} value={role} onChange={(e) => setRole(e.target.value.toUpperCase())} />}</Field>
              <Field label="Company name">{(id) => <input id={id} required maxLength={100} autoComplete="organization" placeholder="BYBIT" className={`${inputCls} uppercase`} value={company} onChange={(e) => setCompany(e.target.value.toUpperCase())} />}</Field>
              <Field label="City" hint="City and country start the press release as its dateline.">{(id) => <input id={id} required maxLength={100} autoComplete="address-level2" placeholder="LAGOS" className={`${inputCls} uppercase`} value={city} onChange={(e) => setCity(e.target.value.toUpperCase())} />}</Field>
              <Field label="Country">{(id) => <input id={id} required maxLength={100} autoComplete="country-name" placeholder="NIGERIA" className={`${inputCls} uppercase`} value={country} onChange={(e) => setCountry(e.target.value.toUpperCase())} />}</Field>
            </div>
            <Field label="Website (optional)">{(id) => <input id={id} type="text" inputMode="url" autoComplete="url" className={inputCls} value={website} onChange={(e) => setWebsite(e.target.value)} placeholder="yourbusiness.com" />}</Field>
            <p className="text-sm text-muted">Writing it is free and nothing is sent to anyone yet. You will check and edit it next.</p>
            <div className="flex flex-wrap gap-3">
              <Button type="button" variant="secondary" disabled={busy} onClick={() => setStep("choose")}>Back</Button>
              <Button type="submit" disabled={busy || !writeReady}>{busy ? "Writing your press release…" : "Write my press release"}</Button>
            </div>
          </form>
        </Card>
      )}

      {step === "upload" && (
        <Card title="Upload your press release">
          <p className="text-sm text-muted">Choose a Word (.docx), PDF, text (.txt) or Markdown (.md) file, up to 2 MB. We read the text so you can check and edit it here. The file itself is not kept.</p>
          <input ref={file} aria-label="Press release file" type="file" accept=".docx,.pdf,.txt,.md" disabled={busy} className="mt-4 block w-full rounded-lg border border-line p-3 text-sm file:mr-3 file:rounded file:border-0 file:bg-paper file:px-3 file:py-2 file:font-semibold" onChange={(e) => { upload(e.target.files?.[0]); e.target.value = ""; }} />
          {busy && <p role="status" className="mt-3 text-sm">Reading your file…</p>}
          <div className="mt-5 flex flex-wrap gap-3">
            <Button type="button" variant="secondary" disabled={busy} onClick={() => setStep("choose")}>Back</Button>
            <Button type="button" variant="secondary" disabled={busy} onClick={() => { setRelease({ headline: "", announcement: "", unverified: [] }); setFromAi(false); setStep("edit"); }}>Paste the text instead</Button>
          </div>
        </Card>
      )}

      {step === "edit" && (
        <Card title="Your press release">
          <p className="text-sm text-muted">{fromAi ? "Here is the press release we wrote. Change anything you like: it is sent exactly as it appears here." : "Check your press release and change anything you like: it is sent exactly as it appears here."}</p>
          {release.unverified.length > 0 && <div className="mt-3"><Notice tone="warn">We hedged these because we couldn&apos;t check them: {release.unverified.join("; ")}.</Notice></div>}
          <div className="mt-4 space-y-4">
            <Field label="Headline">{(id) => <input id={id} required maxLength={300} className={inputCls} value={release.headline} onChange={(e) => setRelease(r => ({ ...r, headline: e.target.value }))} />}</Field>
            <Field label="Press release" hint="Leave a blank line between paragraphs.">{(id) => <textarea id={id} required rows={16} maxLength={50000} className={inputCls} value={release.announcement} onChange={(e) => setRelease(r => ({ ...r, announcement: e.target.value }))} />}</Field>
          </div>
          <div className="mt-5 flex flex-wrap gap-3">
            <Button type="button" variant="secondary" disabled={busy} onClick={() => setStep(fromAi ? "write" : "upload")}>Back</Button>
            {fromAi && <Button type="button" variant="secondary" disabled={busy || !writeReady} onClick={() => { if (confirm("Write it again? What you have now will be replaced.")) void write(); }}>{busy ? "Writing…" : "Write it again"}</Button>}
            <Button type="button" disabled={busy || !editReady} onClick={() => setStep("pictures")}>Continue</Button>
          </div>
        </Card>
      )}

      {step === "pictures" && (
        <Card title="Add pictures for your press release">
          <p className="text-sm">Outlets publish more stories that come with good pictures, so we recommend adding some: your product, your team, the launch. You can add up to 10 PNG or JPEG pictures of up to 5 MB each. Some outlets accept extra pictures for a small fee, and you will see the price before you pay.</p>
          <input aria-label="Add a picture" type="file" accept="image/png,image/jpeg" disabled={busy || pictures.length >= 10} className="mt-4 block w-full rounded-lg border border-line p-3 text-sm file:mr-3 file:rounded file:border-0 file:bg-paper file:px-3 file:py-2 file:font-semibold" onChange={(e) => { addPicture(e.target.files?.[0]); e.target.value = ""; }} />
          {pictures.length > 0 && (
            <ul className="mt-4 grid grid-cols-2 gap-3 sm:grid-cols-4" aria-label="Your pictures">
              {pictures.map((p, i) => (
                <li key={p.key} className="rounded-lg border border-line p-2">
                  {p.url ? <img src={p.url} alt={`Picture ${i + 1}`} className="aspect-video w-full rounded object-cover" /> : <div className="flex aspect-video items-center justify-center rounded bg-paper text-sm">Picture {i + 1}</div>}
                  <button type="button" className="mt-2 text-sm font-semibold underline" onClick={() => setPictures(list => list.filter(x => x.key !== p.key))}>Remove</button>
                </li>
              ))}
            </ul>
          )}
          <p role="status" className="mt-3 text-sm text-muted">{busy ? "Uploading…" : pictures.length ? `${pictures.length} picture${pictures.length === 1 ? "" : "s"} added.` : "No pictures yet. You can also add them later, in the contact step."}</p>
          <div className="mt-5 flex flex-wrap gap-3">
            <Button type="button" variant="secondary" disabled={busy} onClick={() => setStep("edit")}>Back</Button>
            <Button type="button" disabled={busy} onClick={() => void toOutlets()}>{busy ? "Please wait…" : pictures.length ? "Continue to choose outlets" : "Skip pictures and choose outlets"}</Button>
          </div>
        </Card>
      )}
    </div>
  );
}

