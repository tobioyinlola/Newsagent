import { createContext, type ReactNode, useCallback, useContext, useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { Toast } from "./ui";

// The marketing section's shared pieces, so every screen explains itself and behaves the same way.

export const MARKETING = "/marketing";

// ---- saved / done messages: a short pop-up so nobody wonders whether something worked ----
const ToastCtx = createContext<(message: string) => void>(() => {});
export const useToast = () => useContext(ToastCtx);
export function ToastProvider({ children }: { children: ReactNode }) {
  const [message, setMessage] = useState<string | null>(null);
  const timer = useRef<number | undefined>(undefined);
  const show = useCallback((m: string) => {
    setMessage(m);
    window.clearTimeout(timer.current);
    timer.current = window.setTimeout(() => setMessage(null), 4000);
  }, []);
  useEffect(() => () => window.clearTimeout(timer.current), []);
  return <ToastCtx.Provider value={show}>{children}{message && <Toast>{message}</Toast>}</ToastCtx.Provider>;
}

// ---- where am I: "Campaigns › Morning send" ----
export function Crumbs({ trail }: { trail: [label: string, to?: string][] }) {
  return (
    <nav aria-label="Breadcrumb" className="text-sm">
      <ol className="flex flex-wrap items-center gap-1.5 text-muted">
        {trail.map(([label, to], i) => (
          <li key={label + i} className="flex items-center gap-1.5">
            {i > 0 && <span aria-hidden="true">›</span>}
            {to ? <Link to={to} className="font-semibold text-ink underline underline-offset-2">{label}</Link> : <span aria-current="page" className="font-semibold text-ink">{label}</span>}
          </li>
        ))}
      </ol>
    </nav>
  );
}

// ---- what is this screen for, in one sentence, with the longer explanation tucked away ----
export function PageIntro({ title, children, how, actions }: { title: string; children: ReactNode; how?: string[]; actions?: ReactNode }) {
  return (
    <header className="space-y-2">
      <div className="flex flex-wrap items-start justify-between gap-3">
        <div className="min-w-0 space-y-1">
          <h2 className="text-xl font-bold">{title}</h2>
          <p className="max-w-2xl text-sm text-muted">{children}</p>
        </div>
        {actions && <div className="flex shrink-0 flex-wrap gap-2">{actions}</div>}
      </div>
      {how && (
        <details className="max-w-2xl text-sm">
          <summary className="cursor-pointer font-semibold underline underline-offset-2">How does this work?</summary>
          <ol className="mt-2 list-decimal space-y-1 pl-5 text-muted">{how.map((h) => <li key={h}>{h}</li>)}</ol>
        </details>
      )}
    </header>
  );
}

// ---- an empty list that says what to do next ----
export function EmptyState({ title, children, actions }: { title: string; children?: ReactNode; actions?: ReactNode }) {
  return (
    <div className="rounded-xl border-2 border-dashed border-line bg-paper p-6 text-center">
      <p className="font-bold">{title}</p>
      {children && <p className="mx-auto mt-1 max-w-md text-sm text-muted">{children}</p>}
      {actions && <div className="mt-4 flex flex-wrap justify-center gap-2">{actions}</div>}
    </div>
  );
}

// ---- a small numbered heading for the parts of a form, so a long form reads as a few clear steps ----
export function Step({ n, title, hint, children }: { n: number; title: string; hint?: string; children: ReactNode }) {
  return (
    <section className="space-y-3" aria-labelledby={`step-${n}-${title.replace(/\W+/g, "-")}`}>
      <div className="flex items-start gap-3">
        <span aria-hidden="true" className="flex h-7 w-7 shrink-0 items-center justify-center rounded-full border border-ink bg-brand-green text-sm font-bold">{n}</span>
        <div><h3 id={`step-${n}-${title.replace(/\W+/g, "-")}`} className="font-bold">{title}</h3>{hint && <p className="text-sm text-muted">{hint}</p>}</div>
      </div>
      <div className="space-y-3 sm:pl-10">{children}</div>
    </section>
  );
}

// ---- a "done / to do" line for checklists ----
export function Check({ done, children, action }: { done: boolean; children: ReactNode; action?: ReactNode }) {
  return (
    <li className="flex flex-wrap items-center justify-between gap-2 py-2.5">
      <span className="flex items-start gap-3">
        <span aria-hidden="true" className={`mt-0.5 flex h-5 w-5 shrink-0 items-center justify-center rounded-full border text-xs font-bold ${done ? "border-ink bg-brand-green" : "border-line bg-white text-muted"}`}>{done ? "✓" : ""}</span>
        <span className="text-sm"><span className="sr-only">{done ? "Done: " : "To do: "}</span>{children}</span>
      </span>
      {!done && action}
    </li>
  );
}

// Words used on these screens, in plain language. Shown on the Start here page.
export const GLOSSARY: [string, string][] = [
  ["Segment", "A saved group of people, picked by rules. For example, “joined in the last 7 days and hasn’t made a video”."],
  ["Email copy", "An email you’ve written once and can use again: subject, message and an optional button."],
  ["Campaign", "Sends one email to one segment, now or at a time you choose."],
  ["Workflow", "A sequence that emails people over time on its own: send, wait a few days, send again, and stop when they’ve done what you wanted."],
  ["Goal", "What you want people to do, such as buying credits. Anyone who does it is taken out of the workflow, so they stop getting emails about it."],
  ["Dry run", "A test mode: everything works and is recorded in Activity, but no email is really sent."],
  ["Unsubscribed", "Someone who chose to stop getting marketing email. Only they can turn it back on."],
  ["Blocked address", "An address that bounced for good, or whose owner marked our email as spam. We never send marketing email to it."],
];
