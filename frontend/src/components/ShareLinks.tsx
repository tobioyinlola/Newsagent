import { useState } from "react";

// Share a story's link: WhatsApp, LinkedIn, X (Twitter), Facebook, email, a copied link, and the phone's own share sheet where there is one.
export function ShareLinks({ url, title, text, tone = "light", label = "Share this story" }: { url: string; title: string; text: string; tone?: "light" | "dark"; label?: string }) {
  const [copied, setCopied] = useState(false);
  const btn = tone === "dark"
    ? "rounded-sm border border-white/40 px-3 py-1.5 text-xs font-bold text-white hover:border-brand-green hover:text-brand-green"
    : "rounded-md border border-ink px-3 py-1.5 text-xs font-bold text-ink hover:bg-paper";
  const u = encodeURIComponent(url), t = encodeURIComponent(text);
  const targets: [string, string][] = [
    ["WhatsApp", `https://wa.me/?text=${encodeURIComponent(`${text} ${url}`)}`],
    ["LinkedIn", `https://www.linkedin.com/sharing/share-offsite/?url=${u}`],
    ["X (Twitter)", `https://twitter.com/intent/tweet?text=${t}&url=${u}`],
    ["Facebook", `https://www.facebook.com/sharer/sharer.php?u=${u}`],
    ["Email", `mailto:?subject=${t}&body=${u}`],
  ];
  const canNativeShare = typeof navigator !== "undefined" && typeof navigator.share === "function";
  return (
    <div className="flex flex-wrap items-center gap-2" role="group" aria-label={label}>
      <span className={`mr-1 text-sm font-semibold ${tone === "dark" ? "text-white" : "text-ink"}`}>{label}</span>
      {targets.map(([name, href]) => (
        <a key={name} href={href} target={name === "Email" ? undefined : "_blank"} rel="noopener noreferrer" className={btn} aria-label={`Share on ${name}`}>{name}</a>
      ))}
      <button type="button" className={btn} onClick={async () => { try { await navigator.clipboard.writeText(url); setCopied(true); setTimeout(() => setCopied(false), 1500); } catch { setCopied(false); } }}>{copied ? "Link copied" : "Copy link"}</button>
      {canNativeShare && <button type="button" className={btn} onClick={() => { void navigator.share({ title, text, url }).catch(() => undefined); }}>More…</button>}
    </div>
  );
}
