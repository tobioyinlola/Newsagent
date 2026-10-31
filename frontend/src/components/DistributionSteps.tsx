export const DISTRIBUTION_STEPS = ["outlets", "content", "contact", "review"];
const labels = ["Choose outlets", "Video & announcement", "Contact & images", "Review & pay"];

export function DistributionSteps({ current, disabled, onStep, bottom = false }: { current: string; disabled: boolean; onStep: (step: string) => void; bottom?: boolean }) {
  const active = DISTRIBUTION_STEPS.indexOf(current);
  return <nav aria-label={bottom ? "Distribution steps (bottom)" : "Distribution steps"} className={`rounded-xl border border-line bg-white p-3 sm:p-4 ${bottom ? "mt-6" : ""}`}><ol className="flex flex-wrap items-center gap-x-2 gap-y-3">{DISTRIBUTION_STEPS.map((step, i) => <li key={step} className="flex items-center gap-2"><button type="button" disabled={disabled} aria-current={step === current ? "step" : undefined} onClick={() => onStep(step)} className={`min-h-11 rounded-lg border-2 px-3 py-2 text-sm font-bold disabled:opacity-50 ${step === current ? "border-ink bg-brand-green text-ink" : i < active ? "border-line bg-lime-tint text-ink" : "border-line bg-white text-muted"}`}>{i + 1}. {labels[i]}</button>{i < DISTRIBUTION_STEPS.length - 1 && <span aria-hidden="true" className={`text-xl font-bold ${i < active ? "text-ink" : "text-line"}`}>›</span>}</li>)}</ol><p className="mt-3 text-xs text-muted">Step {active + 1} of 4 · {labels[active] ?? "Choose outlets"}</p></nav>;
}
