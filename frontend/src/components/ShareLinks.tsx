import { useState } from "react";

// Instagram has no web share intent: copy the link and open Instagram for manual sharing.
export function ShareLinks({ url, title, text, tone = "light", label = "Share this story" }: { url: string; title: string; text: string; tone?: "light" | "dark"; label?: string }) {
  const [copied, setCopied] = useState(false);
  const [instagram, setInstagram] = useState<"copied" | "manual" | null>(null);
  const btn = tone === "dark"
    ? "rounded-sm border border-white/40 px-3 py-1.5 text-xs font-bold text-white hover:border-brand-green hover:text-brand-green"
    : "rounded-md border border-ink px-3 py-1.5 text-xs font-bold text-ink hover:bg-paper";
  const u = encodeURIComponent(url), t = encodeURIComponent(text);
  const targets: [string, string][] = [
    ["WhatsApp", `https://wa.me/?text=${encodeURIComponent(`${text} ${url}`)}`],
    ["LinkedIn", `https://www.linkedin.com/sharing/share-offsite/?url=${u}`],
    ["X (Twitter)", `https://twitter.com/intent/tweet?text=${t}&url=${u}`],
    ["Facebook", `https://www.facebook.com/sharer/sharer.php?u=${u}`],
    ["Instagram", "https://www.instagram.com/"],
    ["Email", `mailto:?subject=${t}&body=${u}`],
  ];
  const canNativeShare = typeof navigator !== "undefined" && typeof navigator.share === "function";
  return (
    <div className="flex flex-wrap items-center gap-2" role="group" aria-label={label}>
      <span className={`mr-1 text-sm font-semibold ${tone === "dark" ? "text-white" : "text-ink"}`}>{label}</span>
      {targets.map(([name, href]) => (
        <a key={name} href={href} target={name === "Email" ? undefined : "_blank"} rel="noopener noreferrer" className={btn} aria-label={`Share on ${name}`} onClick={name === "Instagram" ? () => {
          // Start copying during the click, then let the link open normally to avoid popup blocking.
          try { void navigator.clipboard.writeText(url).then(() => setInstagram("copied")).catch(() => setInstagram("manual")); }
          catch { setInstagram("manual"); }
        } : undefined}>{name}</a>
      ))}
      <button type="button" className={btn} onClick={async () => { try { await navigator.clipboard.writeText(url); setCopied(true); setTimeout(() => setCopied(false), 1500); } catch { setCopied(false); } }}>{copied ? "Link copied" : "Copy link"}</button>
      {canNativeShare && <button type="button" className={btn} onClick={() => { void navigator.share({ title, text, url }).catch(() => undefined); }}>More…</button>}
      {instagram && <div className={`w-full space-y-2 text-sm ${tone === "dark" ? "text-white/80" : "text-muted"}`}>
        <p role="status">{instagram === "copied" ? "Story link copied. Paste it into an Instagram Story link sticker, your bio or a message. Instagram opens in a new tab; posting is completed there." : "Copy the story link below, then paste it into an Instagram Story link sticker, your bio or a message."}</p>
        {instagram === "manual" && <input readOnly aria-label="Story link for Instagram" className={`w-full rounded border p-2 ${tone === "dark" ? "border-white/40 bg-ink text-white" : "border-ink bg-paper text-ink"}`} value={url} onFocus={e => e.currentTarget.select()} />}
      </div>}
    </div>
  );
}
