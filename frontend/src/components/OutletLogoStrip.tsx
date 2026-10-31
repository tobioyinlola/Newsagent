import { type Outlet, OUTLETS_BOTTOM, OUTLETS_TOP } from "../lib/outlets";

function LogoRow({ outlets, reverse = false, compact }: { outlets: Outlet[]; reverse?: boolean; compact: boolean }) {
  const tile = (o: Outlet, hidden: boolean) => <li key={`${hidden}-${o.slug}`} aria-hidden={hidden || undefined} className={`shrink-0 ${hidden ? "motion-reduce:hidden" : ""}`}><img src={`/outlets/${o.slug}.webp`} alt={hidden ? "" : o.name} width={200} height={86} loading="lazy" decoding="async" draggable={false} className={`${compact ? "h-[62px] w-[144px]" : "h-[86px] w-[200px]"} rounded-lg border border-black/5 bg-white object-cover shadow-sm motion-reduce:aspect-[200/86] motion-reduce:h-auto motion-reduce:w-full`} /></li>;
  return <div className="overflow-hidden [mask-image:linear-gradient(to_right,transparent,#000_8%,#000_92%,transparent)] motion-reduce:[mask-image:none]"><ul className={`flex w-max gap-4 py-2 pr-4 motion-reduce:grid motion-reduce:w-full motion-reduce:grid-cols-3 motion-reduce:gap-2 motion-reduce:pr-0 sm:motion-reduce:grid-cols-4 lg:motion-reduce:grid-cols-6 ${reverse ? "cf-marquee-rev" : "cf-marquee"}`}>{outlets.map(o => tile(o, false))}{outlets.map(o => tile(o, true))}</ul></div>;
}

export function OutletLogoStrip({ compact = false }: { compact?: boolean }) {
  return <div role="region" aria-label="Media outlet logos" className={`cf-marquee-wrap min-w-0 overflow-hidden ${compact ? "space-y-1" : "space-y-4"}`}>
    <LogoRow outlets={compact ? OUTLETS_TOP.slice(0, 8) : OUTLETS_TOP} compact={compact} />
    <LogoRow outlets={compact ? OUTLETS_BOTTOM.slice(0, 8) : OUTLETS_BOTTOM} compact={compact} reverse />
  </div>;
}
