// The outlet planner: what we ask a person, what comes back, and the few helpers the screens share.
export const GOALS: { key: Goal; label: string; hint: string }[] = [
  { key: "credibility", label: "Look credible", hint: "General news outlets first" },
  { key: "investors", label: "Reach investors", hint: "Technology outlets first" },
  { key: "customers", label: "Win customers", hint: "General news outlets first" },
  { key: "hiring", label: "Support hiring", hint: "Technology outlets first" },
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
export type PlanSource = "public" | "request" | "ready_prompt" | "email";
export type PlanAsk = { budget: string; countries: string[]; goal: Goal; industry?: string | null; source?: PlanSource; auto?: boolean };

const base = () => import.meta.env.VITE_API_URL ?? "";

/** What the planner is sent: a blank or invalid budget means "no limit", so people see what each plan would cost. */
export function planBody(ask: PlanAsk) {
  const n = Number(ask.budget);
  return { budget: ask.budget.trim() !== "" && Number.isFinite(n) && n >= 0 ? String(n) : null, countries: ask.countries, goal: ask.goal, industry: ask.industry ?? null, source: ask.source ?? "public", auto: ask.auto ?? false };
}

export async function fetchPublicPlan(ask: PlanAsk): Promise<PlanResult> {
  const r = await fetch(`${base()}/v1/public/distribution/plan`, { method: "POST", headers: { "Content-Type": "application/json" }, body: JSON.stringify(planBody(ask)) });
  if (!r.ok) throw new Error(r.status === 429 ? "Too many tries. Please wait a moment." : "We could not make a plan just now. Please try again.");
  return r.json();
}

export const credits = (v: string | number) => { const n = Number(v); return `${Number(n.toFixed(2)).toLocaleString("en")} ${n === 1 ? "credit" : "credits"}`; };

/** Ids of every outlet in a plan, in order. */
export const planIds = (p: Plan) => p.outlets.map((o) => o.id);

/** Whether a reply is really a plan result. A suggestion is never worth breaking a page over: anything else is ignored. */
export function isPlanResult(x: unknown): x is PlanResult {
  const r = x as Partial<PlanResult> | null;
  return !!r && typeof r === "object" && Array.isArray(r.plans) && Array.isArray(r.countries) && Array.isArray(r.notes) && Array.isArray(r.budget_presets) && !!r.suggested && typeof r.suggested === "object";
}

/** The plan to feature on the "video is ready" prompt: the biggest that fits the wallet, else the smallest with what is missing.
 *  None when there is nothing personal to say (no country we recognise, or no plans), so the prompt stays as it was. */
export function featuredPlan(r: PlanResult): { plan: Plan; fits: boolean; balance: number; missing: number } | null {
  if (!isPlanResult(r) || !r.plans.length || !r.countries.length) return null;
  const balance = Number(r.balance_credits ?? 0);
  const fitting = r.plans.filter((p) => Number(p.total_credits) <= balance);
  const plan = fitting.length ? fitting[fitting.length - 1] : r.plans[0];
  const missing = Math.max(0, Number((Number(plan.total_credits) - balance).toFixed(2)));
  return { plan, fits: missing === 0, balance, missing };
}

/** "Tribune, Independent, Techeconomy and 2 more" */
export function outletSummary(p: Plan, show = 3): string {
  const names = p.outlets.map((o) => o.name);
  return names.length <= show ? names.join(", ") : `${names.slice(0, show).join(", ")} and ${names.length - show} more`;
}

/** What we keep of a plan when someone acts on it: which one, how many outlets, how many credits. Never who they are. */
export type PlanRef = { key: Plan["key"]; outlets: number; total_credits: string };
export const planRef = (p: Plan): PlanRef => ({ key: p.key, outlets: p.outlets.length, total_credits: p.total_credits });

/** Tell the server a plan was used (or carried on to sign-up). It never blocks or breaks the screen: if it fails, nothing happens. */
export function trackPlan(kind: "used" | "continued", source: PlanSource, plan: PlanRef, token: string | null) {
  try {
    const body = JSON.stringify({ kind, source, plan_key: plan.key, outlets: plan.outlets, credits: plan.total_credits });
    void fetch(`${base()}/v1/${token ? "" : "public/"}distribution/plan/event`, { method: "POST", keepalive: true, headers: { "Content-Type": "application/json", ...(token ? { Authorization: `Bearer ${token}` } : {}) }, body }).catch(() => undefined);
  } catch { /* measuring must never get in the way */ }
}
