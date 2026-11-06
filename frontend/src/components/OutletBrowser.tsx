import { useQuery } from "@tanstack/react-query";
import { useMemo, useState } from "react";
import { useNavigate } from "react-router-dom";
import { getToken } from "../lib/auth";
import { ALL, groupOutlets, matches, outletTitle, readPick, savePick, setAfterAuth, type Facets, type OutletFilters as FilterList } from "../lib/distributionFilters";
import { DistributionOutletLogo } from "./DistributionOutletLogo";
import { OutletFilters } from "./OutletFilters";

type PublicOutlet = { id: string; name: string; topic: string; category: string; region: string; country: string | null; credits: string };
type Catalogue = { outlets: PublicOutlet[]; filters: FilterList; coming_soon: string[] };

async function loadOutlets(): Promise<Catalogue> {
  const r = await fetch(`${import.meta.env.VITE_API_URL ?? ""}/v1/public/distribution/outlets`);
  if (!r.ok) throw new Error("We could not load the outlets. Please try again.");
  return r.json();
}

const credits = (n: number) => `${Number(n.toFixed(2))} ${n === 1 ? "credit" : "credits"}`;

// Public outlet browser: pick outlets by topic and place, then sign up and carry the choice into the distribution request.
export function OutletBrowser() {
  const nav = useNavigate();
  const data = useQuery({ queryKey: ["public-outlets"], queryFn: loadOutlets, staleTime: 60_000 });
  const [facets, setFacets] = useState<Facets>(ALL);
  const [search, setSearch] = useState("");
  const [picked, setPicked] = useState<string[]>(() => readPick());
  const all = data.data?.outlets ?? [];
  const known = useMemo(() => new Set(all.map((o) => o.id)), [all]);
  const chosen = all.filter((o) => picked.includes(o.id));
  const total = chosen.reduce((n, o) => n + Number(o.credits), 0);
  const q = search.trim().toLowerCase();
  const visible = all.filter((o) => matches(o, facets) && (!q || o.name.toLowerCase().includes(q)));
  const toggle = (id: string) => { const next = picked.includes(id) ? picked.filter((x) => x !== id) : [...picked, id]; setPicked(next); savePick(next); };
  const signedIn = Boolean(getToken());
  const go = () => {
    const ids = picked.filter((id) => known.has(id));
    savePick(ids);
    if (signedIn) { nav("/distribution/request?pick=1"); return; }
    setAfterAuth("/distribution/request?pick=1"); // after sign-up the person lands back in the request, outlets already chosen
    nav("/signup");
  };
  return (
    <section id="choose" aria-labelledby="choose-h" className="scroll-mt-4 border-b border-white/10 bg-ink px-4 py-16 pb-32 md:px-8">
      <div className="mx-auto max-w-6xl">
        <div className="text-center">
          <p className="text-xs font-bold uppercase tracking-widest text-brand-green">Choose your outlets</p>
          <h2 id="choose-h" className="mt-3 text-3xl text-white md:text-5xl">Pick where your story goes.</h2>
          <p className="mx-auto mt-3 max-w-2xl text-white/70">Browse by topic and place, tick the outlets you want and see the credits as you go. Then create your free account and finish your request. Nothing is charged until you submit.</p>
        </div>
        {data.isLoading && <p className="mt-10 text-center text-white/70" aria-busy="true">Loading outlets…</p>}
        {data.isError && <p role="alert" className="mt-10 text-center text-red-300">We could not load the outlets right now. Please refresh and try again.</p>}
        {data.data && (
          <div className="mt-10 space-y-6">
            <OutletFilters dark filters={data.data.filters} outlets={all} value={facets} onChange={setFacets} />
            <label className="block max-w-xl text-sm font-bold text-white">Search by name
              <input type="search" value={search} onChange={(e) => setSearch(e.target.value)} placeholder="For example Techpoint" className="mt-1 min-h-11 w-full rounded-lg border border-white/40 bg-ink px-3 py-2 text-base font-normal text-white placeholder:text-white/40 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-purple" />
            </label>
            <div className="space-y-10">
              {groupOutlets(visible, data.data.filters).map((g) => (
                <section key={g.topic} aria-labelledby={`topic-${g.topic}`}>
                  <h3 id={`topic-${g.topic}`} className="flex flex-wrap items-baseline gap-3 border-b border-white/15 pb-2 text-2xl font-bold text-white">{g.topic}<span className="text-sm font-normal text-white/60">{g.count} {g.count === 1 ? "outlet" : "outlets"}</span></h3>
                  {g.locations.map((l) => (
                    <div key={l.key} className="mt-5">
                      <h4 className="text-sm font-bold uppercase tracking-widest text-brand-green">{l.label} ({g.topic} Channels)</h4>
                      <ul className="mt-3 grid grid-cols-1 gap-3 sm:grid-cols-2 lg:grid-cols-3">
                        {l.items.map((o) => {
                          const on = picked.includes(o.id);
                          return (
                            <li key={o.id} className="min-w-0">
                              <label className={`flex min-h-24 cursor-pointer items-center gap-3 rounded-lg border-2 p-3 focus-within:ring-2 focus-within:ring-brand-purple focus-within:ring-offset-2 focus-within:ring-offset-ink ${on ? "border-brand-green bg-brand-green/15" : "border-white/15 bg-white/5 hover:border-white/50"}`}>
                                <input type="checkbox" className="h-5 w-5 shrink-0 accent-[#8BE04E]" checked={on} onChange={() => toggle(o.id)} />
                                <DistributionOutletLogo name={o.name} />
                                <span className="min-w-0 flex-1">
                                  <span className="block truncate font-bold text-white">{outletTitle(o)}</span>
                                  <span className="block break-words text-xs text-white/65">{o.topic} · {o.country ?? o.region}</span>
                                  <span className="mt-1 block text-sm font-bold text-brand-green">{credits(Number(o.credits))}</span>
                                </span>
                              </label>
                            </li>
                          );
                        })}
                      </ul>
                    </div>
                  ))}
                </section>
              ))}
            </div>
            {data.data.coming_soon.length > 0 && <p className="text-sm text-white/60">Coming soon: {data.data.coming_soon.join(", ")}.</p>}
          </div>
        )}
      </div>
      <div role="region" aria-label="Your selection" className="fixed inset-x-3 bottom-[max(0.75rem,env(safe-area-inset-bottom))] z-30 mx-auto flex max-w-2xl flex-wrap items-center justify-between gap-3 rounded-xl border-2 border-ink bg-white p-3 text-ink shadow-xl sm:px-5">
        <span className="text-sm" aria-live="polite"><strong className="tabular-nums">{chosen.length} selected</strong><span className="ml-2 text-muted">· {credits(total)}</span></span>
        <button type="button" disabled={chosen.length === 0} onClick={go} className="min-h-11 rounded-lg border-2 border-ink bg-brand-green px-5 py-2 text-sm font-bold text-ink disabled:cursor-not-allowed disabled:opacity-50 focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-purple">
          {signedIn ? "Continue" : "Continue: create your free account"}
        </button>
      </div>
    </section>
  );
}
