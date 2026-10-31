import { useState } from "react";
import logoData from "../lib/distributionLogos.json";

const logos: Record<string, { src: string; tone?: string }> = logoData;

// Names stay visible beside the image; an unavailable/unverified logo uses an honest initials badge.
export function DistributionOutletLogo({ name, small = false }: { name: string; small?: boolean }) {
  const [failed, setFailed] = useState(false);
  const src = logos[name]?.src;
  const dark = !failed && !!src && logos[name]?.tone === "dark";
  const words = name.replace(/[^\p{L}\p{N} ]/gu, " ").trim().split(/\s+/);
  const initials = words.length > 1 ? words.slice(0, 2).map(w => w[0]).join("") : name.slice(0, 2);
  return <span aria-hidden="true" className={`flex shrink-0 items-center justify-center overflow-hidden rounded-lg border border-line ${dark ? "bg-ink" : "bg-white"} ${small ? "h-10 w-12 p-1.5" : "h-14 w-16 p-2 sm:w-20"}`}>
    {src && !failed ? <img src={src} alt="" loading="lazy" decoding="async" width={80} height={56} className="h-full w-full object-contain" onError={() => setFailed(true)} /> : <span className="text-sm font-bold uppercase tracking-wide text-brand-purple">{initials}</span>}
  </span>;
}
