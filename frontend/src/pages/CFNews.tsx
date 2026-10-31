import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api, unwrap } from "../api/client";
import { StoryRow, type StoryCard } from "../components/StoryCards";
import { Cta, Eyebrow, SiteShell } from "./Landing";

export function CFNews() {
  const q = useQuery({ queryKey: ["cf-news-page"], queryFn: () => unwrap(api.GET("/v1/public/cf-news", { params: { query: { limit: 60 } } })), staleTime: 60_000 });
  const cards = (q.data ?? []) as StoryCard[];
  return <SiteShell><main className="px-4 py-10 md:px-8"><div className="mx-auto max-w-6xl"><Eyebrow>Cover Founder</Eyebrow><h1 className="mt-3 text-3xl text-white md:text-5xl">CF News</h1><p className="mt-3 max-w-2xl text-white/70">Breaking news produced by the Cover Founder News Desk.</p>{q.isLoading ? <p className="mt-8 text-white/70" aria-busy="true">Loading CF News…</p> : cards.length ? <div className="mt-8"><StoryRow title="CF News" cards={cards} /></div> : <div className="mt-8 border border-white/15 p-10 text-center"><h2 className="text-2xl font-bold text-white">CF News is coming soon.</h2><p className="mx-auto mt-2 max-w-md text-white/70">Breaking news from the Cover Founder News Desk will appear here.</p><div className="mt-6 flex justify-center"><Cta to="/signup" primary>Publish your free story!</Cta></div></div>}<Link to="/latest-stories" className="mt-8 inline-flex text-sm font-bold text-brand-green hover:underline">Browse CF Featured Stories →</Link></div></main></SiteShell>;
}
