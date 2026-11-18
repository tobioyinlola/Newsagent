// The outlet planner: what we ask a person, what comes back, and the few helpers the screens share.
export const GOALS: { key: Goal; label: string; hint: string }[] = [
  { key: "credibility", label: "Look credible", hint: "Be seen in respected news outlets" },
  { key: "investors", label: "Reach investors", hint: "Technology and business readers" },
  { key: "customers", label: "Win customers", hint: "A broad news audience" },
  { key: "hiring", label: "Support hiring", hint: "Technology readers and job seekers" },
];
export type Goal = "credibility" | "investors" | "customers" | "hiring";

export type PlanOutlet = { id: string; name: string; topic: string; country: string | null; region: string; credits: string; reasons: string[] };
export type Plan = { key: "essential" | "balanced" | "max"; name: string; summary: string; total_credits: string; outlets: PlanOutlet[]; countries: string[]; topics: string[]; shortfall_credits?: string };
export type PlanResult = {
  plans: Plan[];
  suggested: Record<string, string[]>; // outlet id -> why it was suggested
  budget_presets: string[];
  cheapest_credits: string | null;
  notes: string[];
  countries: string[];
  goal: Goal;
  balance_credits?: string;
  empty?: string;
};
export type PlanAsk = { budget: string; countries: string[]; goal: Goal; industry?: string | null };

const base = () => import.meta.env.VITE_API_URL ?? "";

/** What the planner is sent: a blank or invalid budget means "no limit", so people see what each plan would cost. */
export function planBody(ask: PlanAsk) {
  const n = Number(ask.budget);
  return { budget: ask.budget.trim() !== "" && Number.isFinite(n) && n >= 0 ? String(n) : null, countries: ask.countries, goal: ask.goal, industry: ask.industry ?? null };
}

export async function fetchPublicPlan(ask: PlanAsk): Promise<PlanResult> {
  const r = await fetch(`${base()}/v1/public/distribution/plan`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(planBody(ask)) });
  if (!r.ok) throw new Error(r.status === 429 ? "Too many tries. Please wait a moment." : "We could not make a plan just now. Please try again.");
  return r.json();
}

export const credits = (v: string | number) => { const n = Number(v); return `${Number(n.toFixed(2)).toLocaleString("en")} ${n === 1 ? "credit" : "credits"}`; };

/** Ids of every outlet in a plan, in order. */
export const planIds = (p: Plan) => p.outlets.map((o) => o.id);
