import { useState } from "react";
import { useQuery } from "@tanstack/react-query";
import { distributionApi } from "../../lib/distribution";
import { getToken } from "../lib/auth";

type Rates = { use_of_viewed: number | null; submitted_of_used: number | null; unchanged_of_submitted: number | null; average_credits: string | null };
type Block = { shown: number; asked: number; used: number; continued: number; submitted: number; unchanged: number; credits_submitted: string; rates: Rates };
type Stats = { days: number; since: string; total: Block; by_source: Record<"public" | "request" | "ready_prompt" | "email", Block> };

const SOURCES: { key: keyof Stats["by_source"]; label: string; hint: string }[] = [
  { key: "public", label: "Website distribution page", hint: "Visitors, before they sign up" },
  { key: "ready_prompt", label: "Video-ready pop-up", hint: "Shown when a video finishes" },
  { key: "request", label: "Distribution request", hint: "The outlets step" },
  { key: "email", label: "Email link", hint: "People who clicked through from an email" },
];
const pct = (v: number | null) => (v === null ? "–" : `${Math.round(v * 100)}%`);

// How the suggested plans are doing. Counts only: nothing here says who a visitor was.
export function PlannerStats() {
  const [days, setDays] = useState(30);
  const q = useQuery({ queryKey: ["planner-stats", days], queryFn: () => distributionApi<Stats>(`admin/planner-stats?days=${days}`, getToken()), refetchOnWindowFocus: false });
  const data = q.data;
  const t = data?.total;
  const card = (label: string, value: string, note: string) => (
    <div className="rounded-lg border-2 border-line p-4"><p className="text-sm text-muted">{label}</p><p className="mt-1 text-3xl font-bold tabular-nums">{value}</p><p className="mt-1 text-xs text-muted">{note}</p></div>
  );
  return (
    <section aria-labelledby="planner-stats-h" className="space-y-5 rounded-lg border bg-white p-4 sm:p-6">
      <div className="flex flex-wrap items-end justify-between gap-3">
        <div><h2 id="planner-stats-h" className="text-xl font-bold">Suggested plans</h2><p className="text-sm text-muted">How often a plan is made, chosen, and paid for, and whether people keep what we suggest. Counts only.</p></div>
        <label className="text-sm font-semibold">Period
          <select className="ml-2 min-h-11 rounded border p-2 font-normal" value={days} onChange={(e) => setDays(Number(e.target.value))}>
            <option value={7}>Last 7 days</option><option value={30}>Last 30 days</option><option value={90}>Last 90 days</option>
          </select>
        </label>
      </div>
      {q.isLoading && <p aria-busy="true">Loading…</p>}
      {q.error && <p role="alert">We could not load the numbers. Please try again.</p>}
      {data && t && (
        <>
          <div className="grid gap-3 sm:grid-cols-2 lg:grid-cols-4">
            {card("Plans viewed", String(t.shown + t.asked), `${t.shown} made automatically, ${t.asked} asked for`)}
            {card("Plans chosen", String(t.used), `${pct(t.rates.use_of_viewed)} of plans viewed`)}
            {card("Requests paid", String(t.submitted), `${pct(t.rates.submitted_of_used)} of plans chosen`)}
            {card("Kept as suggested", pct(t.rates.unchanged_of_submitted), `${t.unchanged} of ${t.submitted} paid requests were not changed`)}
          </div>
          {t.rates.average_credits && <p className="text-sm">Average paid request that began from a plan: <strong>{t.rates.average_credits} credits</strong>.</p>}
          <div className="overflow-x-auto">
            <table className="w-full min-w-[40rem] text-left text-sm">
              <caption className="sr-only">Suggested plans by screen</caption>
              <thead><tr className="border-b"><th scope="col" className="py-2 pr-3">Where</th><th scope="col" className="px-3 text-right">Viewed</th><th scope="col" className="px-3 text-right">Chosen</th><th scope="col" className="px-3 text-right">Went on to sign up</th><th scope="col" className="px-3 text-right">Paid</th><th scope="col" className="pl-3 text-right">Kept as suggested</th></tr></thead>
              <tbody>
                {SOURCES.map((s) => { const b = data.by_source[s.key]; return (
                  <tr key={s.key} className="border-b align-top"><th scope="row" className="py-2 pr-3 font-semibold">{s.label}<span className="block text-xs font-normal text-muted">{s.hint}</span></th><td className="px-3 text-right tabular-nums">{b.shown + b.asked}</td><td className="px-3 text-right tabular-nums">{b.used}</td><td className="px-3 text-right tabular-nums">{b.continued}</td><td className="px-3 text-right tabular-nums">{b.submitted}</td><td className="pl-3 text-right tabular-nums">{b.submitted ? `${b.unchanged} of ${b.submitted}` : "–"}</td></tr>
                ); })}
              </tbody>
            </table>
          </div>
          <p className="text-xs text-muted">"Viewed" counts plans shown automatically as well as ones someone asked for, so one person can count more than once. Counts since {new Date(data.since).toLocaleDateString("en")}.</p>
        </>
      )}
    </section>
  );
}
