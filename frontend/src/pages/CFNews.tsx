import { useInfiniteQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api, unwrap } from "../api/client";
import { StoryTile, type StoryCard } from "../components/StoryCards";
import { Cta, Eyebrow, SiteShell } from "./Landing";

// Stories shown at first and added by each "See more". One extra is asked for, only to know whether older stories remain.
export const CF_NEWS_PAGE = 20;

export function CFNews() {
  const q = useInfiniteQuery({
    queryKey: ["cf-news-page"],
    initialPageParam: 0,
    queryFn: ({ pageParam }) =>
      unwrap(api.GET("/v1/public/cf-news", { params: { query: { limit: CF_NEWS_PAGE + 1, offset: pageParam } } })) as Promise<StoryCard[]>,
    getNextPageParam: (last, all) => (last.length > CF_NEWS_PAGE ? all.length * CF_NEWS_PAGE : undefined),
    staleTime: 60_000,
  });
  // a story published while someone is reading shifts the pages by one: never show the same story twice
  const seen = new Set<string>();
  const cards = (q.data?.pages ?? []).flatMap((p) => p.slice(0, CF_NEWS_PAGE)).filter((c) => !seen.has(c.slug) && seen.add(c.slug));
  return (
    <SiteShell>
      <main className="px-4 py-10 md:px-8">
        <div className="mx-auto max-w-6xl">
          <Eyebrow>Cover Founder</Eyebrow>
          <h1 className="mt-3 text-3xl text-white md:text-5xl">CF News</h1>
          <p className="mt-3 max-w-2xl text-white/70">Breaking news produced by the Cover Founder News Desk.</p>
          {q.isLoading ? (
            <p className="mt-8 text-white/70" aria-busy="true">Loading CF News…</p>
          ) : q.isError && !cards.length ? (
            <p className="mt-8 text-white/70" role="alert">We couldn't load CF News just now. Please refresh the page.</p>
          ) : cards.length ? (
            <section aria-label="CF News stories" className="mt-8 border-t border-white/10 pt-8">
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
          ) : (
            <div className="mt-8 border border-white/15 p-10 text-center">
              <h2 className="text-2xl font-bold text-white">CF News is coming soon.</h2>
              <p className="mx-auto mt-2 max-w-md text-white/70">Breaking news from the Cover Founder News Desk will appear here.</p>
              <div className="mt-6 flex justify-center"><Cta to="/signup" primary>Publish your free story!</Cta></div>
            </div>
          )}
          <Link to="/latest-stories" className="mt-8 inline-flex text-sm font-bold text-brand-green hover:underline">Browse CF Featured Stories →</Link>
        </div>
      </main>
    </SiteShell>
  );
}
