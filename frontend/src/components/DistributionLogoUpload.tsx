import { useId, useState } from "react";

export function DistributionLogoUpload({ value, url, busy, uploading, error, onUpload, onRemove }: {
  value: string; url?: string; busy: boolean; uploading: boolean; error?: string;
  onUpload: (file: File) => void; onRemove: () => void;
}) {
  const id = useId();
  const [dragging, setDragging] = useState(false);
  return <section aria-labelledby={`${id}-title`} className="mt-6">
    <h3 id={`${id}-title`} className="font-bold">Company logo <span className="text-sm font-normal text-muted">Required</span></h3>
    <div onDragOver={e => { e.preventDefault(); if (!busy) setDragging(true); }} onDragLeave={() => setDragging(false)} onDrop={e => { e.preventDefault(); setDragging(false); const file = e.dataTransfer.files[0]; if (file && !busy) onUpload(file); }} className={`mt-3 rounded-xl border-2 border-dashed p-5 transition-colors focus-within:ring-2 focus-within:ring-brand-purple focus-within:ring-offset-2 ${error ? "border-brand-red bg-red-tint" : dragging ? "border-ink bg-brand-green/20" : "border-line bg-paper"}`}>
      <div className="flex flex-col items-center gap-4 text-center sm:flex-row sm:text-left">
        <div className="flex h-24 w-24 shrink-0 items-center justify-center overflow-hidden rounded-lg border border-line bg-white p-2">
          {value && url ? <img alt="Company logo preview" src={url} className="max-h-full max-w-full object-contain" /> : <svg aria-hidden="true" className="h-10 w-10 text-muted" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><rect x="3" y="3" width="18" height="18" rx="3" /><circle cx="8" cy="8" r="1.5" /><path d="m3 17 6-6 4 4 3-3 5 5" /></svg>}
        </div>
        <div className="min-w-0 flex-1"><p className="font-semibold">{uploading ? "Uploading and checking your logo…" : value ? "Company logo uploaded ✓" : "Drop your logo here, or choose a file"}</p><p id={`${id}-hint`} className="mt-1 text-sm text-muted">PNG or JPEG · Up to 5 MB. A clear, high-resolution logo works best.</p><div className="mt-3 flex flex-wrap justify-center gap-3 sm:justify-start">
          <input id={id} aria-label="Company logo (required, PNG/JPEG, up to 5 MB)" aria-invalid={!!error} aria-describedby={`${id}-hint${error ? ` ${id}-error` : ""}`} type="file" accept="image/png,image/jpeg" disabled={busy} className="sr-only" onChange={e => { const file = e.target.files?.[0]; if (file) onUpload(file); e.target.value = ""; }} />
          <label htmlFor={id} className={`inline-flex min-h-11 items-center rounded-lg border-2 border-ink px-4 py-2 text-sm font-bold ${busy ? "cursor-wait opacity-50" : "cursor-pointer bg-white hover:bg-brand-green"}`}>{uploading ? "Please wait…" : value ? "Replace logo" : "Choose logo"}</label>
          {value && <button type="button" disabled={busy} onClick={onRemove} className="min-h-11 rounded-lg px-3 text-sm font-bold underline disabled:opacity-50">Remove logo</button>}
        </div></div>
      </div>
    </div>
    {error && <p id={`${id}-error`} role="alert" className="mt-2 text-sm font-semibold text-red-800">{error}</p>}
  </section>;
}
