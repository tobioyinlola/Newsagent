import { useQuery } from "@tanstack/react-query";
import { type ReactNode, useCallback, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api, type Schemas, unwrap } from "../api/client";

import { useStoryImpression } from "../lib/audience";

export type StoryCard = Schemas["StoryCardOut"];

export const STORIES_PATH = "/latest-stories";
export const storyPath = (slug: string) => `${STORIES_PATH}/${slug}`;

export function useStories(limit = 24) {
  return useQuery({
    queryKey: ["public-stories", limit],
    queryFn: () => unwrap(api.GET("/v1/public/stories", { params: { query: { limit } } })),
    retry: false,
    staleTime: 60_000,
  });
}

export const clock = (s?: number | null) => (s == null ? "" : `${Math.floor(s / 60)}:${String(Math.round(s % 60)).padStart(2, "0")}`);
export const dayOf = (iso: string) => new Date(iso).toLocaleDateString("en-US", { month: "short", day: "numeric", year: "numeric" });

export function PlayDisc({ size = 44 }: { size?: number }) {
  return (
    <span aria-hidden="true" className="flex items-center justify-center rounded-full border-2 border-white bg-black/45 text-white" style={{ width: size, height: size }}>
      <svg viewBox="0 0 24 24" width={size * 0.45} height={size * 0.45} fill="currentColor"><path d="M8 5v14l11-7z" /></svg>
    </span>
  );
}

/** A story's picture: the video's thumbnail with a dark fade, the play button and the length. */
export function StoryThumb({ card, big = false }: { card: StoryCard; big?: boolean }) {
  const impression = useRef<HTMLDivElement>(null);
  useStoryImpression(impression, card.category ? "" : card.slug);
  return (
    <div ref={impression} className="relative aspect-video w-full overflow-hidden rounded-sm bg-white/5">
      {card.thumbnail_url ? <img src={card.thumbnail_url} alt="" className="h-full w-full object-cover" loading="lazy" /> : <div className="h-full w-full bg-gradient-to-br from-brand-purple/60 to-ink" />}
      <div aria-hidden="true" className="absolute inset-0 bg-gradient-to-t from-black/80 via-black/10 to-transparent" />
      <div className="absolute bottom-3 left-3 flex items-center gap-2 text-sm font-semibold text-white">
        {card.has_video !== false ? <PlayDisc size={big ? 56 : 40} /> : <span className="rounded-full border border-white/50 bg-black/40 px-3 py-1 text-xs">Read story →</span>}
        {card.duration_s != null && <span>{clock(card.duration_s)}</span>}
      </div>
    </div>
  );
}

export function StoryTile({ card }: { card: StoryCard }) {
  return (
    <Link to={storyPath(card.slug)} className="group block w-[78vw] shrink-0 snap-start rounded-sm border border-white/15 bg-white/[0.03] p-0 hover:border-brand-green sm:w-[320px]">
      <StoryThumb card={card} />
      <div className="space-y-1 p-3">
        {card.industry && <p className="font-mono text-[11px] font-bold uppercase tracking-wider text-brand-green">{card.industry}</p>}
        <p className="line-clamp-2 font-bold leading-snug text-white group-hover:text-brand-green">{card.title}</p>
        <p className="text-xs text-white/60">{card.company} · {dayOf(card.published_at)}</p>
      </div>
    </Link>
  );
}

/** A row that scrolls sideways: arrows at the right, dots under it, swipe or scroll as well. */
export function ScrollRow({ label, children, count }: { label: string; children: ReactNode; count: number }) {
  const ref = useRef<HTMLDivElement>(null);
  const [page, setPage] = useState(0);
  const [pages, setPages] = useState(1);
  const measure = useCallback(() => {
    const el = ref.current;
    if (!el) return;
    setPages(Math.max(1, Math.ceil(el.scrollWidth / el.clientWidth - 0.05)));
    setPage(Math.round(el.scrollLeft / el.clientWidth));
  }, []);
  useEffect(() => { measure(); window.addEventListener("resize", measure); return () => window.removeEventListener("resize", measure); }, [measure, count]);
  const go = (dir: 1 | -1) => ref.current?.scrollBy({ left: dir * ref.current.clientWidth * 0.85, behavior: window.matchMedia("(prefers-reduced-motion: reduce)").matches ? "auto" : "smooth" });
  return (
    <div role="region" aria-roledescription="carousel" aria-label={label}>
      <div ref={ref} onScroll={measure} className="flex snap-x snap-mandatory gap-4 overflow-x-auto scroll-smooth pb-2 [scrollbar-width:none] [&::-webkit-scrollbar]:hidden" tabIndex={0}>
        {children}
      </div>
      <div className="mt-3 flex items-center justify-between">
        <div className="flex flex-1 justify-center gap-2" aria-hidden="true">
          {Array.from({ length: Math.min(pages, 8) }, (_, i) => <span key={i} className={`h-1.5 w-1.5 rounded-full ${i === page ? "bg-white" : "bg-white/30"}`} />)}
        </div>
        <div className="flex gap-2">
          <button type="button" onClick={() => go(-1)} aria-label={`Scroll ${label} left`} className="flex h-8 w-8 items-center justify-center rounded-full border border-white/40 text-white hover:border-brand-green hover:text-brand-green"><span aria-hidden="true">‹</span></button>
          <button type="button" onClick={() => go(1)} aria-label={`Scroll ${label} right`} className="flex h-8 w-8 items-center justify-center rounded-full border border-white/70 text-white hover:border-brand-green hover:text-brand-green"><span aria-hidden="true">›</span></button>
        </div>
      </div>
    </div>
  );
}

export function StoryRow({ title, cards }: { title: string; cards: StoryCard[] }) {
  return (
    <section className="border-t border-white/10 py-8">
      <h2 className="mb-4 text-xl font-bold text-white">{title}</h2>
      <ScrollRow label={title} count={cards.length}>{cards.map((c) => <StoryTile key={c.slug} card={c} />)}</ScrollRow>
    </section>
  );
}
