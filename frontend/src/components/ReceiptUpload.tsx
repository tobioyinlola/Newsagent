import { useEffect, useRef, useState } from "react";

export function ReceiptUpload({ busy, filename, onUpload, onRemove }: { busy: boolean; filename: string; onUpload: (file: File) => Promise<boolean>; onRemove: () => void }) {
  const input = useRef<HTMLInputElement>(null);
  const [file, setFile] = useState<File | null>(null);
  const [preview, setPreview] = useState("");
  const [dragging, setDragging] = useState(false);
  const [uploading, setUploading] = useState(false);
  const [error, setError] = useState("");
  useEffect(() => {
    if (!file || !file.type.startsWith("image/")) { setPreview(""); return; }
    const url = URL.createObjectURL(file); setPreview(url);
    return () => URL.revokeObjectURL(url);
  }, [file]);
  const choose = async (files: File[]) => {
    if (busy || uploading) return;
    setDragging(false); setError("");
    if (files.length !== 1) { setError("Please select one receipt at a time."); return; }
    const next = files[0];
    if (!["image/png", "image/jpeg", "application/pdf"].includes(next.type) || !next.size || next.size > 5 * 1024 * 1024) { setError("Choose a PNG, JPEG or PDF receipt up to 5 MB."); return; }
    setUploading(true);
    try { if (await onUpload(next)) setFile(next); else setFile(null); } finally { setUploading(false); }
  };
  return <div className="space-y-3">
    <div><p className="text-sm font-bold">Payment receipt</p><p id="receipt-upload-help" className="mt-1 text-xs leading-relaxed text-muted">Upload a clear receipt showing the amount, date and transaction reference. PNG, JPEG or PDF · maximum 5 MB.</p></div>
    <div className={`rounded-xl border-2 border-dashed p-5 transition-colors sm:p-7 ${dragging ? "border-ink bg-lime-tint" : "border-line bg-paper"}`} onDragOver={e => { e.preventDefault(); if (!busy) setDragging(true); }} onDragLeave={e => { if (!e.currentTarget.contains(e.relatedTarget as Node)) setDragging(false); }} onDrop={e => { e.preventDefault(); setDragging(false); if (!busy) void choose(Array.from(e.dataTransfer.files)); }} aria-busy={uploading}>
      <input ref={input} type="file" className="sr-only" tabIndex={-1} aria-label="Payment receipt" aria-describedby="receipt-upload-help" accept="image/png,image/jpeg,application/pdf" disabled={busy || uploading} onChange={e => { const files = Array.from(e.target.files || []); e.target.value = ""; if (files.length) void choose(files); }} />
      {filename && !uploading ? <div className="flex flex-wrap items-center gap-4">{preview ? <img src={preview} alt="Selected payment receipt preview" className="h-24 w-20 rounded-lg border border-line bg-white object-contain" /> : <span aria-hidden="true" className="flex h-20 w-16 items-center justify-center rounded-lg border border-line bg-white text-sm font-bold">PDF</span>}<div className="min-w-0 flex-1"><p className="break-all text-sm font-bold">{filename}</p><p role="status" className="mt-1 text-xs text-muted">Uploaded securely · ready to submit{file ? ` · ${(file.size / 1024).toFixed(0)} KB` : ""}</p><div className="mt-3 flex flex-wrap gap-4"><button type="button" className="min-h-10 text-sm font-bold underline" disabled={busy} onClick={() => input.current?.click()}>Replace receipt</button><button type="button" className="min-h-10 text-sm text-muted underline" disabled={busy} onClick={() => { setFile(null); setError(""); onRemove(); }}>Remove</button></div></div></div> : <div className="text-center"><span aria-hidden="true" className="mx-auto mb-3 flex h-12 w-12 items-center justify-center rounded-full border border-line bg-white"><svg width="24" height="24" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.5"><path d="M12 16V3m-5 5 5-5 5 5M4 15v6h16v-6" /></svg></span><p className="text-sm font-bold" role={uploading ? "status" : undefined}>{uploading ? "Uploading and verifying your receipt…" : "Drag your receipt here"}</p><p className="mt-1 text-xs text-muted">{uploading ? "Please keep this page open." : "or select a file from your phone or computer"}</p><button type="button" className="mt-4 min-h-11 rounded-lg border border-ink bg-brand-green px-5 py-2 text-sm font-bold disabled:opacity-50" disabled={busy || uploading} onClick={() => input.current?.click()}>{uploading ? "Uploading…" : "Choose receipt"}</button></div>}
    </div>
    {error && <p role="alert" className="text-sm text-brand-red">{error}</p>}
    <p className="text-xs text-muted">Your receipt is shared securely with the payment review team. Uploading it does not submit it for approval yet.</p>
  </div>;
}
