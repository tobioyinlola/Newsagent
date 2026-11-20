import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Navigate, useNavigate } from "react-router-dom";
import { Button, ErrorBox, Field, inputCls } from "../components/ui";
import { SecondaryLogo } from "../components/Logo";
import { ONBOARDING_ON } from "../lib/onboardingFlag";
import { loadOnboarding, ONBOARDING_KEY, type OnboardingState, type Profile, saveProfile } from "../lib/onboarding";

// The first-run questions, one card at a time, shown right after sign-up. Every question is optional, every card can be skipped,
// and the whole thing can be skipped to go straight to the dashboard. Answers are saved as you go and kept with the customer's details.
const STEPS = [
  { id: "about_you", title: "A little about you", hint: "So we can say hello properly." },
  { id: "your_business", title: "About your business", hint: "This helps us suggest the right outlets and plans." },
  { id: "your_goals", title: "What do you want from your story?", hint: "Pick as many as you like." },
  { id: "how_you_heard", title: "How did you hear about us?", hint: "It helps us reach more people like you." },
];

export function Welcome() {
  const nav = useNavigate();
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ONBOARDING_KEY, queryFn: loadOnboarding, retry: false });
  const [step, setStep] = useState(0);
  const [form, setForm] = useState<Profile>({});
  const [ready, setReady] = useState(false);
  useEffect(() => {
    if (q.data && !ready) { setForm(q.data.profile); setStep(Math.min(q.data.profile_step, STEPS.length - 1)); setReady(true); }
  }, [q.data, ready]);

  const save = useMutation({ mutationFn: saveProfile, onSuccess: (s: OnboardingState) => qc.setQueryData(ONBOARDING_KEY, s) });
  const leave = () => nav("/dashboard", { replace: true });
  if (q.isLoading || !ready) return q.error ? <p className="p-6" role="alert">We could not load this. <a className="underline" href="/dashboard">Go to your dashboard</a></p> : <p className="p-6" aria-busy="true">Loading…</p>;
  const o = q.data!.options;
  const last = step === STEPS.length - 1;
  const set = <K extends keyof Profile>(k: K, v: Profile[K]) => setForm((f) => ({ ...f, [k]: v }));
  const answersFor = (id: string): Profile => id === "about_you" ? { contact_name: form.contact_name ?? "", role: form.role ?? "", phone: form.phone ?? "" }
    : id === "your_business" ? { website: form.website ?? "", company_size: form.company_size ?? "" }
    : id === "your_goals" ? { goals: form.goals ?? [] }
    : { heard_from: form.heard_from ?? "", heard_detail: form.heard_detail ?? "" };
  const next = async (skipCard = false) => {
    const body = { answers: skipCard ? undefined : answersFor(STEPS[step].id), step: step + 1, status: last ? ("done" as const) : ("in_progress" as const) };
    try { await save.mutateAsync(body); } catch { return; }
    if (last) leave(); else setStep(step + 1);
  };
  const skipAll = async () => { try { await save.mutateAsync({ status: "skipped", step }); } catch { return; } leave(); };
  const toggleGoal = (k: string) => set("goals", (form.goals ?? []).includes(k) ? (form.goals ?? []).filter((g) => g !== k) : [...(form.goals ?? []), k]);
  const choice = (selected: boolean) => `flex min-h-11 w-full cursor-pointer items-center gap-3 rounded-sm border-2 px-3 py-2 text-left text-sm font-semibold ${selected ? "border-ink bg-brand-green text-ink" : "border-line bg-white hover:border-ink"} focus-within:outline-3 focus-within:outline-offset-2 focus-within:outline-brand-purple`;

  return (
    <div className="min-h-screen bg-paper text-ink">
      <header className="flex items-center justify-between bg-ink px-4 py-3 sm:px-8"><SecondaryLogo className="h-8 w-auto" /><button type="button" className="rounded-sm border-2 border-brand-green px-3 py-1.5 text-sm font-bold text-brand-green hover:bg-brand-green hover:text-ink" onClick={() => void skipAll()}>Skip for now</button></header>
      <main className="mx-auto w-full max-w-xl px-4 py-8 sm:py-12">
        <p className="text-xs font-bold uppercase tracking-widest text-muted">Welcome to Cover Founder</p>
        <h1 className="mt-2 text-2xl font-bold sm:text-3xl">Let’s set up your workspace</h1>
        <p className="mt-1 text-sm text-muted">A few quick questions. You can skip any of them.</p>
        <ol className="mt-5 flex gap-2" aria-label="Progress">{STEPS.map((s, i) => <li key={s.id} className="h-2 flex-1 rounded bg-line" aria-current={i === step ? "step" : undefined}><div className={`h-full rounded ${i < step ? "bg-ink" : i === step ? "bg-brand-green" : ""}`} style={{ width: i <= step ? "100%" : "0%" }} /></li>)}</ol>
        <p className="mt-2 text-sm font-semibold" aria-live="polite">Step {step + 1} of {STEPS.length}</p>
        <section aria-labelledby="card-h" className="mt-4 rounded-md border-2 border-ink bg-white p-4 sm:p-6" data-tour="onboarding-card">
          <h2 id="card-h" className="text-xl font-bold">{STEPS[step].title}</h2>
          <p className="mt-1 text-sm text-muted">{STEPS[step].hint}</p>
          <div className="mt-4 space-y-4">
            {step === 0 && <>
              <Field label="What should we call you?">{(id) => <input id={id} className={inputCls} autoComplete="given-name" maxLength={120} value={form.contact_name ?? ""} onChange={(e) => set("contact_name", e.target.value)} />}</Field>
              <Field label="Your role">{(id) => <select id={id} className={inputCls} value={form.role ?? ""} onChange={(e) => set("role", e.target.value)}><option value="">Choose one</option>{o.roles.map((r) => <option key={r.key} value={r.key}>{r.label}</option>)}</select>}</Field>
              <Field label="Phone number (optional)" hint="Only used if we need to reach you about your story.">{(id) => <input id={id} className={inputCls} type="tel" autoComplete="tel" maxLength={40} value={form.phone ?? ""} onChange={(e) => set("phone", e.target.value)} />}</Field>
            </>}
            {step === 1 && <>
              <Field label="Website (optional)">{(id) => <input id={id} className={inputCls} type="text" inputMode="url" autoComplete="url" placeholder="yourcompany.com" maxLength={200} value={form.website ?? ""} onChange={(e) => set("website", e.target.value)} />}</Field>
              <Field label="How big is your team?">{(id) => <select id={id} className={inputCls} value={form.company_size ?? ""} onChange={(e) => set("company_size", e.target.value)}><option value="">Choose one</option>{o.sizes.map((r) => <option key={r.key} value={r.key}>{r.label}</option>)}</select>}</Field>
            </>}
            {step === 2 && <fieldset><legend className="sr-only">Your goals</legend><div className="grid gap-2 sm:grid-cols-2">{o.goals.map((g) => { const on = (form.goals ?? []).includes(g.key); return <label key={g.key} className={choice(on)}><input type="checkbox" className="sr-only" checked={on} onChange={() => toggleGoal(g.key)} /><span aria-hidden="true">{on ? "✓" : "○"}</span>{g.label}</label>; })}</div></fieldset>}
            {step === 3 && <>
              <fieldset><legend className="sr-only">How you heard about us</legend><div className="grid gap-2 sm:grid-cols-2">{o.heard.map((h) => { const on = form.heard_from === h.key; return <label key={h.key} className={choice(on)}><input type="radio" name="heard" className="sr-only" checked={on} onChange={() => set("heard_from", h.key)} /><span aria-hidden="true">{on ? "●" : "○"}</span>{h.label}</label>; })}</div></fieldset>
              <Field label="Tell us more (optional)" hint="For example which site, who told you, or which event.">{(id) => <input id={id} className={inputCls} maxLength={300} value={form.heard_detail ?? ""} onChange={(e) => set("heard_detail", e.target.value)} />}</Field>
            </>}
          </div>
          <ErrorBox error={save.error} />
          <div className="mt-6 flex flex-wrap items-center justify-between gap-3">
            <div className="flex gap-3">{step > 0 && <Button type="button" variant="secondary" disabled={save.isPending} onClick={() => setStep(step - 1)}>Back</Button>}<button type="button" className="text-sm font-semibold underline" disabled={save.isPending} onClick={() => void next(true)}>Skip this step</button></div>
            <Button type="button" disabled={save.isPending} onClick={() => void next()}>{save.isPending ? "Saving…" : last ? "Finish" : "Continue"}</Button>
          </div>
        </section>
        <p className="mt-4 text-xs text-muted">We keep these answers with your account to tailor suggestions and improve Cover Founder. You can change them in Settings later.</p>
      </main>
    </div>
  );
}

/** Send people to the questions while they are still waiting (a new sign-up), otherwise carry on. */
export function SendToWelcome({ children }: { children: React.ReactNode }) {
  const q = useQuery({ queryKey: ONBOARDING_KEY, queryFn: loadOnboarding, retry: false, staleTime: 60_000 });
  if (ONBOARDING_ON && q.data?.profile_status === "pending") return <Navigate to="/welcome" replace />;
  return <>{children}</>;
}

/** For accounts that were made before these questions existed: a quiet card on the dashboard they can answer or dismiss. */
export function ProfileNudge() {
  const qc = useQueryClient();
  const q = useQuery({ queryKey: ONBOARDING_KEY, queryFn: loadOnboarding, retry: false, staleTime: 60_000 });
  const hide = useMutation({ mutationFn: () => saveProfile({ status: "skipped" }), onSuccess: (s: OnboardingState) => qc.setQueryData(ONBOARDING_KEY, s) });
  if (!ONBOARDING_ON || q.data?.profile_status !== "not_started") return null;
  return (
    <section aria-label="Tell us about your business" className="flex flex-wrap items-center justify-between gap-3 rounded-md border-2 border-ink bg-lilac p-4">
      <div><p className="font-bold">Help us tailor Cover Founder to you</p><p className="text-sm">Four quick questions about you and your goals. Every one is optional.</p></div>
      <div className="flex items-center gap-3"><button type="button" className="text-sm font-semibold underline" disabled={hide.isPending} onClick={() => hide.mutate()}>Not now</button><a className="inline-flex min-h-11 items-center rounded-sm border-2 border-ink bg-brand-green px-4 text-sm font-bold hover:bg-ink hover:text-brand-green" href="/welcome">Answer them</a></div>
    </section>
  );
}
