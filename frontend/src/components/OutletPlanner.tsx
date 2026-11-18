import { useEffect, useId, useRef, useState } from "react";
import { credits, GOALS, planIds, type Goal, type Plan, type PlanAsk, type PlanResult } from "../lib/outletPlanner";

type Props = {
  countries: string[]; // the countries we have outlets in
  fetchPlan: (ask: PlanAsk) => Promise<PlanResult>;
  initialCountries?: string[];
  industry?: string | null;
  dark?: boolean; // on the dark public page
  autoRun?: boolean; // make a first suggestion straight away from what we already know
  appliedIds?: string[]; // the outlets already chosen, to show which plan is in use
  onResult?: (r: PlanResult | null) => void; // so the full list can mark the suggested outlets
  onApply: (plan: Plan) => void;
  applyLabel?: string;
  onTopUp?: (plan: Plan) => void;
};

// "Not sure where to start?": three questions, then up to three ready-made plans. The full list of outlets stays on the page.
export function OutletPlanner({ countries, fetchPlan, initialCountries = [], industry = null, dark = false, autoRun = false, appliedIds = [], onResult, onApply, applyLabel = "Use this plan", onTopUp }: Props) {
  const uid = useId();
  const [picked, setPicked] = useState<string[]>(initialCountries);
  const [budget, setBudget] = useState("");
  const [goal, setGoal] = useState<Goal>("credibility");
  const [result, setResult] = useState<PlanResult | null>(null);
  const [busy, setBusy] = useState(false);
  const [error, setError] = useState("");
  const [applied, setApplied] = useState("");
  const ran = useRef(false);
  const run = async (next?: Partial<PlanAsk>) => {
    setBusy(true); setError(""); setApplied("");
    try {
      const r = await fetchPlan({ budget, countries: picked, goal, industry, ...next });
      setResult(r); onResult?.(r);
      if (!picked.length && r.countries.length) setPicked(r.countries); // started from the business's own country
    } catch (e) { setError(e instanceof Error ? e.message : "We could not make a plan just now. Please try again."); }
    finally { setBusy(false); }
  };
  useEffect(() => { if (autoRun && !ran.current) { ran.current = true; void run(); } }, []);
  const toggle = (c: string) => setPicked((p) => (p.includes(c) ? p.filter((x) => x !== c) : [...p, c]));
  const t = dark
    ? { box: "border-white/20 bg-white/5 text-white", muted: "text-white/70", chip: (on: boolean) => (on ? "border-brand-green bg-brand-green text-ink" : "border-white/40 text-white hover:border-brand-green"), field: "border-white/40 bg-ink text-white placeholder:text-white/50", card: "border-white/25 bg-ink", accent: "text-brand-green", btn: "border-brand-green bg-brand-green text-ink hover:bg-white", ghost: "border-white/60 text-white hover:bg-white/10", warn: "text-amber-300" }
    : { box: "border-ink bg-white text-ink", muted: "text-muted", chip: (on: boolean) => (on ? "border-ink bg-ink text-white" : "border-line bg-white text-ink hover:border-ink"), field: "border-ink bg-paper text-ink", card: "border-line bg-paper", accent: "text-ink", btn: "border-ink bg-brand-green text-ink hover:bg-ink hover:text-brand-green", ghost: "border-ink text-ink hover:bg-ink hover:text-white", warn: "text-red-700" };
  const focus = "focus-visible:outline-2 focus-visible:outline-offset-2 focus-visible:outline-brand-purple";
  const inUse = (p: Plan) => appliedIds.length > 0 && appliedIds.length === p.outlets.length && planIds(p).every((id) => appliedIds.includes(id));
  return (
    <section aria-labelledby={`${uid}-h`} className={`rounded-xl border-2 p-4 sm:p-6 ${t.box}`}>
      <p className={`text-xs font-bold uppercase tracking-widest ${t.muted}`}>Not sure where to start?</p>
      <h2 id={`${uid}-h`} className="mt-1 text-xl font-bold sm:text-2xl">Get a suggested plan</h2>
      <p className={`mt-2 max-w-2xl text-sm ${t.muted}`}>Answer three quick questions and we will suggest outlets that fit. You can still choose anything from the full list below.</p>
      <form className="mt-5 space-y-5" onSubmit={(e) => { e.preventDefault(); void run(); }}>
        <fieldset>
          <legend className="text-sm font-bold">1. Where are the people you want to reach?</legend>
          <div className="mt-2 flex flex-wrap gap-2">
            {countries.map((c) => (
              <label key={c} className={`flex min-h-11 cursor-pointer items-center gap-2 rounded-full border-2 px-4 py-2 text-sm font-bold ${t.chip(picked.includes(c))} ${focus} focus-within:outline-2 focus-within:outline-offset-2 focus-within:outline-brand-purple`}>
                <input type="checkbox" className="sr-only" checked={picked.includes(c)} onChange={() => toggle(c)} />{picked.includes(c) && <span aria-hidden="true">✓ </span>}{c}
              </label>
            ))}
          </div>
          <p className={`mt-1 text-xs ${t.muted}`}>Pick as many as you like. Leave empty to see options anywhere.</p>
        </fieldset>
        <div>
          <label htmlFor={`${uid}-budget`} className="text-sm font-bold">2. How many credits do you want to spend?</label>
          <div className="mt-2 flex flex-wrap items-center gap-2">
            <input id={`${uid}-budget`} type="number" inputMode="decimal" min={0} step="any" value={budget} onChange={(e) => setBudget(e.target.value)} placeholder="No limit" className={`min-h-11 w-40 rounded-lg border px-3 py-2 text-base ${t.field} ${focus}`} />
            {result?.budget_presets.map((p) => (
              <button key={p} type="button" aria-pressed={budget === p} onClick={() => { setBudget(p); void run({ budget: p }); }} className={`min-h-11 rounded-full border-2 px-4 py-2 text-sm font-bold ${t.chip(budget === p)} ${focus}`}>{credits(p)}</button>
            ))}
          </div>
          <p className={`mt-1 text-xs ${t.muted}`}>Optional. Leave it blank to see what each plan would cost{result?.balance_credits !== undefined ? `. You have ${credits(result.balance_credits)}.` : "."}</p>
        </div>
        <fieldset>
          <legend className="text-sm font-bold">3. What do you want from this story?</legend>
          <div className="mt-2 grid gap-2 sm:grid-cols-2 lg:grid-cols-4">
            {GOALS.map((g) => (
              <label key={g.key} className={`block min-h-11 cursor-pointer rounded-lg border-2 p-3 ${t.chip(goal === g.key)} focus-within:outline-2 focus-within:outline-offset-2 focus-within:outline-brand-purple`}>
                <input type="radio" name={`${uid}-goal`} className="sr-only" checked={goal === g.key} onChange={() => setGoal(g.key)} />
                <span className="block text-sm font-bold">{g.label}</span><span className="block text-xs opacity-80">{g.hint}</span>
              </label>
            ))}
          </div>
        </fieldset>
        <button type="submit" disabled={busy} className={`min-h-11 rounded-lg border-2 px-5 py-2 font-bold disabled:opacity-60 ${t.btn} ${focus}`}>{busy ? "Working…" : result ? "Update suggestions" : "Suggest outlets"}</button>
      </form>
      <div role="status" aria-live="polite" className="mt-4">
        {error && <p role="alert" className={`text-sm font-bold ${t.warn}`}>{error}</p>}
        {!error && result && !result.plans.length && <p className="text-sm font-bold">{result.empty ?? "We could not find a plan for that. Try different answers, or browse the full list."}</p>}
        {!error && result && result.plans.length > 0 && <p className="sr-only">{result.plans.length} suggested {result.plans.length === 1 ? "plan" : "plans"} ready.</p>}
        {applied && <p className={`text-sm font-bold ${t.accent}`}>{applied}</p>}
      </div>
      {result?.notes.map((n) => <p key={n} className={`mt-2 text-sm ${t.muted}`}>ℹ {n}</p>)}
      {result && result.plans.length > 0 && (
        <div className="mt-5 grid gap-4 lg:grid-cols-3">
          {result.plans.map((p) => {
            const short = Number(p.shortfall_credits ?? 0);
            return (
              <article key={p.key} aria-labelledby={`${uid}-${p.key}`} className={`flex flex-col rounded-lg border-2 p-4 ${t.card}`}>
                <h3 id={`${uid}-${p.key}`} className="text-lg font-bold">{p.name}</h3>
                <p className={`text-sm ${t.muted}`}>{p.summary}</p>
                <p className="mt-3 text-2xl font-bold">{credits(p.total_credits)}</p>
                <p className={`text-xs ${t.muted}`}>{p.outlets.length} {p.outlets.length === 1 ? "outlet" : "outlets"} · from this price, logo and pictures are added at review</p>
                {short > 0 && <p className={`mt-2 text-sm font-bold ${t.warn}`}>You need {credits(short)} more for this plan.{onTopUp && <> <button type="button" onClick={() => onTopUp(p)} className="underline">Add credits</button></>}</p>}
                <ul className="mt-3 flex-1 space-y-2">
                  {p.outlets.map((o) => (
                    <li key={o.id} className="text-sm"><span className="font-bold">{o.name}</span> <span className={t.muted}>· {credits(o.credits)}</span><span className={`block text-xs ${t.muted}`}>{o.reasons.join(" · ")}</span></li>
                  ))}
                </ul>
                <button type="button" onClick={() => { onApply(p); setApplied(`${p.name} plan selected: ${p.outlets.length} ${p.outlets.length === 1 ? "outlet" : "outlets"}. You can change any of them in the list below.`); }} aria-pressed={inUse(p)} className={`mt-4 min-h-11 rounded-lg border-2 px-4 py-2 font-bold ${inUse(p) ? t.ghost : t.btn} ${focus}`}>{inUse(p) ? "✓ In use" : applyLabel}</button>
              </article>
            );
          })}
        </div>
      )}
      {result && <p className={`mt-4 text-xs ${t.muted}`}>Suggestions are sorted by how well they fit your answers, not by price. We request placement for you; publication is decided by each outlet and is not guaranteed.</p>}
    </section>
  );
}
