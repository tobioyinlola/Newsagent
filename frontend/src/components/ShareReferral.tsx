import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api, unwrap } from "../api/client";

const MESSAGE = "I’m using Cover Founder to turn my business story into news and get it in front of media outlets. Join me:";

/** Share your own referral link: the phone's share sheet where there is one (every app they have), plus WhatsApp, X, LinkedIn, Facebook, email and copy. */
export function ShareReferral({ onShared }: { onShared?: () => void }) {
  const q = useQuery({ queryKey: ["referrals", "summary"], queryFn: () => unwrap(api.GET("/v1/referrals", { params: { query: { limit: 1, offset: 0 } } })) as unknown as Promise<{ url: string }>, retry: false });
  const [note, setNote] = useState("");
  if (q.isLoading) return <p className="text-sm" aria-busy="true">Getting your link…</p>;
  if (q.error || !q.data?.url) return <p role="alert" className="text-sm font-semibold">We couldn’t get your referral link just now. You can find it any time on the Referral page.</p>;
  const url = q.data.url;
  const enc = encodeURIComponent;
  const open = (to: string) => { window.open(to, "_blank", "noopener,noreferrer"); onShared?.(); };
  const channels: [string, string][] = [
    ["WhatsApp", `https://wa.me/?text=${enc(`${MESSAGE} ${url}`)}`],
    ["X", `https://twitter.com/intent/tweet?text=${enc(MESSAGE)}&url=${enc(url)}`],
    ["LinkedIn", `https://www.linkedin.com/sharing/share-offsite/?url=${enc(url)}`],
    ["Facebook", `https://www.facebook.com/sharer/sharer.php?u=${enc(url)}`],
  ];
  const nativeShare = async () => {
    try { await navigator.share({ title: "Join me on Cover Founder", text: MESSAGE, url }); setNote("Shared. Thank you!"); onShared?.(); }
    catch (e) { if (!(e instanceof DOMException && e.name === "AbortError")) setNote("Sharing isn’t available here. Use one of the options below."); }
  };
  const copy = async () => { try { await navigator.clipboard.writeText(url); setNote("Your link is copied. Paste it anywhere."); onShared?.(); } catch { setNote("Select the link above and copy it."); } };
  const btn = "min-h-11 rounded-sm border-2 border-ink bg-white px-3 py-2 text-sm font-bold hover:bg-paper focus-visible:outline-3 focus-visible:outline-offset-2 focus-visible:outline-brand-purple";
  return (
    <div className="space-y-3">
      <p className="text-sm">Share your personal link. When a business you invite joins and buys credits, you earn credits too.</p>
      <input readOnly aria-label="Your referral link" value={url} onFocus={(e) => e.target.select()} className="w-full rounded-sm border-2 border-ink bg-paper px-3 py-2 text-sm" />
      {typeof navigator !== "undefined" && "share" in navigator && <button type="button" className={`${btn} w-full bg-brand-green hover:bg-ink hover:text-brand-green`} onClick={() => void nativeShare()}>Share…</button>}
      <div className="grid grid-cols-2 gap-2">
        {channels.map(([name, to]) => <button key={name} type="button" className={btn} onClick={() => open(to)}>{name}</button>)}
        <button type="button" className={btn} onClick={() => open(`mailto:?subject=${enc("Join me on Cover Founder")}&body=${enc(`${MESSAGE} ${url}`)}`)}>Email</button>
        <button type="button" className={btn} onClick={() => void copy()}>Copy link</button>
      </div>
      <p role="status" aria-live="polite" className="min-h-5 text-sm font-semibold">{note}</p>
    </div>
  );
}
