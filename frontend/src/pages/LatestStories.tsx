import { useInfiniteQuery, useQuery } from "@tanstack/react-query";
import { api, unwrap } from "../api/client";
import { useEffect, useMemo, useState } from "react";
import { Link } from "react-router-dom";
import { PlayDisc, StoryRow, StoryThumb, StoryTile, storyPath, type StoryCard } from "../components/StoryCards";
import { Cta, Eyebrow, SiteShell } from "./Landing";

const SLIDE_MS = 8000;

// Stories shown at first and added by each "See more". One extra is asked for, only to know whether older stories remain.
export const LATEST_STORIES_PAGE = 12;

// The top of the page: the newest stories, one at a time, with the story's words on the left and its video picture on the right.
function Hero({ cards }: { cards: StoryCard[] }) {
  const [i, setI] = useState(0);
  const [paused, setPaused] = useState(false);
  const reduced = typeof window !== "undefined" && window.matchMedia?.("(prefers-reduced-motion: reduce)").matches;
  const n = cards.length;
  useEffect(() => {
    if (paused || reduced || n < 2) return;
    const t = window.setTimeout(() => setI((x) => (x + 1) % n), SLIDE_MS);
    return () => window.clearTimeout(t);
  }, [i, paused, reduced, n]);
  const c = cards[i % n];
  return (
    <section aria-roledescription="carousel" aria-label="Featured stories" className="relative border border-white/15 bg-[#050a1c] px-4 pb-10 pt-6 md:px-14" onMouseEnter={() => setPaused(true)} onMouseLeave={() => setPaused(false)} onFocus={() => setPaused(true)} onBlur={() => setPaused(false)}>
      <div className="mb-8 flex gap-3" aria-hidden="true">
        {cards.map((x, k) => (
          <span key={x.slug} className="h-1.5 flex-1 overflow-hidden rounded-full bg-white/25">
            <span className="block h-full bg-white" style={k < i ? { width: "100%" } : k === i && !paused && !reduced && n > 1 ? { animation: `cf-fill ${SLIDE_MS}ms linear forwards` } : k === i ? { width: "100%" } : { width: "0%" }} key={k === i ? `a${i}` : `b${k}`} />
          </span>
        ))}
      </div>
      <div className="grid items-center gap-8 md:grid-cols-[minmax(0,2fr)_minmax(0,3fr)]">
        <div className="order-2 md:order-1">
          {c.industry && <p className="mb-3 font-mono text-xs font-bold uppercase tracking-wider text-brand-green">{c.industry}</p>}
          <h2 className="text-3xl font-extrabold leading-tight text-white md:text-4xl"><Link to={storyPath(c.slug)} className="hover:text-brand-green">{c.title}</Link></h2>
          <p className="mt-4 line-clamp-5 text-sm leading-relaxed text-white/85">{c.summary}</p>
          <p className="mt-2 text-xs text-white/60">{c.company}</p>
          <Link to={storyPath(c.slug)} className="mt-5 inline-flex items-center gap-2 rounded-full border border-white/70 px-4 py-2 text-sm font-bold text-white hover:border-brand-green hover:text-brand-green">
            {c.has_video !== false ? <><PlayDisc size={20} /> Watch Now</> : "Read story →"}
          </Link>
        </div>
        <Link to={storyPath(c.slug)} className="order-1 md:order-2" aria-label={`Watch: ${c.title}`}><StoryThumb card={c} big /></Link>
      </div>
      {n > 1 && (
        <>
          <button type="button" onClick={() => setI((x) => (x - 1 + n) % n)} aria-label="Previous story" className="absolute left-2 top-1/2 -translate-y-1/2 p-2 text-4xl text-white hover:text-brand-green"><span aria-hidden="true">‹</span></button>
          <button type="button" onClick={() => setI((x) => (x + 1) % n)} aria-label="Next story" className="absolute right-2 top-1/2 -translate-y-1/2 p-2 text-4xl text-white hover:text-brand-green"><span aria-hidden="true">›</span></button>
        </>
      )}
    </section>
  );
}

export function LatestStories() {
  const q = useInfiniteQuery({
    queryKey: ["latest-stories-page"],
    initialPageParam: 0,
    queryFn: ({ pageParam }) =>
      unwrap(api.GET("/v1/public/stories", { params: { query: { limit: LATEST_STORIES_PAGE + 1, offset: pageParam } } })) as Promise<StoryCard[]>,
    getNextPageParam: (last, all) => (last.length > LATEST_STORIES_PAGE ? all.length * LATEST_STORIES_PAGE : undefined),
    retry: false,
    staleTime: 60_000,
  });
  const news = useQuery({ queryKey: ["cf-news"], queryFn: () => unwrap(api.GET("/v1/public/cf-news")), staleTime: 60000 });
  // a story published while someone is reading shifts the pages by one: never show the same story twice
  const cards = useMemo(() => {
    const seen = new Set<string>();
    return (q.data?.pages ?? []).flatMap((p) => p.slice(0, LATEST_STORIES_PAGE)).filter((c) => !seen.has(c.slug) && seen.add(c.slug));
  }, [q.data]);
  return (
    <SiteShell>
      <main className="px-4 py-10 md:px-8">
        <div className="mx-auto max-w-6xl">
          <Eyebrow>Cover Founder</Eyebrow>
          <h1 className="mt-3 text-3xl text-white md:text-5xl">CF Featured Stories</h1>
          <p className="mt-3 max-w-2xl text-white/70">News from the businesses on Cover Founder: each story is a video and its press release, published the moment it is ready.</p>
          <div className="mt-8">
            {q.isLoading ? <p aria-busy="true" className="text-white/70">Loading…</p> : cards.length === 0 ? (
              <div className="border border-white/15 p-10 text-center">
                <h2 className="text-2xl font-bold text-white">The first story could be yours.</h2>
                <p className="mx-auto mt-2 max-w-md text-white/70">Tell us about your announcement. We interview you, make the video and write the press release, and it appears here.</p>
                <div className="mt-6 flex justify-center"><Cta to="/signup" primary>Publish your free story!</Cta></div>
              </div>
            ) : (
              <>
                <Hero cards={cards.slice(0, 4)} />
                {/* no categories yet: just the latest stories, newest first, with a button for older ones */}
                <section aria-label="Latest stories" className="mt-10">
                  <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-4">
                    {cards.map((c) => <li key={c.slug}><StoryTile card={c} fluid /></li>)}
                  </ul>
                  {q.hasNextPage && (
                    <div className="mt-8 flex justify-center">
                      <button type="button" onClick={() => void q.fetchNextPage()} disabled={q.isFetchingNextPage} className="rounded-full border border-white/40 px-6 py-2.5 text-sm font-bold text-white hover:border-brand-green hover:text-brand-green disabled:opacity-60">
                        {q.isFetchingNextPage ? "Loading…" : "See more"}
                      </button>
                    </div>
                  )}
                  {q.isFetchNextPageError && <p className="mt-3 text-center text-sm text-white/70" role="alert">Couldn't load more stories. Please try again.</p>}
                </section>
              </>
            )}
          </div>
          {news.data?.length ? <StoryRow title="CF News" cards={news.data} /> : <section className="mt-8 border-t border-white/15 py-8"><h2 className="text-xl text-white">CF News</h2><p className="mt-3 text-sm text-white/70">{news.isError ? "CF News is temporarily unavailable. Please try again shortly." : news.isLoading ? "Loading CF News…" : "Breaking news from the Cover Founder News Desk will appear here."}</p></section>}
        </div>
      </main>
    </SiteShell>
  );
}
