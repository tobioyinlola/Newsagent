import { type ButtonHTMLAttributes, type ReactNode, useId } from "react";

export function Button({ variant = "primary", className = "", ...p }: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "secondary" | "danger" }) {
  const styles = {
    primary: "border-2 border-ink bg-brand-green text-ink hover:bg-ink hover:text-brand-green disabled:border-line disabled:bg-line disabled:text-muted",
    secondary: "border-2 border-ink bg-white text-ink hover:bg-ink hover:text-white disabled:border-line disabled:text-muted",
    danger: "border-2 border-ink bg-brand-red text-ink hover:bg-ink hover:text-brand-red disabled:border-line disabled:bg-line disabled:text-muted",
  }[variant];
  return (
    <button
      {...p}
      className={`rounded-sm px-4 py-2 text-sm font-bold focus-visible:outline-3 focus-visible:outline-offset-2 focus-visible:outline-brand-purple disabled:cursor-not-allowed ${styles} ${className}`}
    />
  );
}

export function Card({ title, children, actions }: { title?: string; children: ReactNode; actions?: ReactNode }) {
  return (
    <section className="rounded-md border-2 border-ink bg-white p-4 sm:p-6">
      {(title || actions) && (
        <div className="mb-4 flex items-center justify-between gap-2">
          {title && <h2 className="text-lg font-bold text-ink">{title}</h2>}
          {actions}
        </div>
      )}
      {children}
    </section>
  );
}

export function Field({ label, hint, children }: { label: string; hint?: string; children: (id: string) => ReactNode }) {
  const id = useId();
  return (
    <div className="space-y-1">
      <label htmlFor={id} className="block text-sm font-medium text-ink">{label}</label>
      {children(id)}
      {hint && <p className="text-xs text-muted">{hint}</p>}
    </div>
  );
}

export const inputCls =
  "w-full rounded-sm border-2 border-ink bg-white px-3 py-2 text-sm text-ink focus:border-brand-purple focus:outline-3 focus:outline-brand-purple/40";

export function ErrorBox({ error }: { error: unknown }) {
  if (!error) return null;
  return (
    <p role="alert" className="rounded-md border-2 border-brand-red bg-red-tint p-3 text-sm text-ink">
      {error instanceof Error ? error.message : "Something went wrong"}
    </p>
  );
}

// A short pop-up for a success the person should notice before the page moves on.
export function Toast({ children }: { children: ReactNode }) {
  return (
    <div role="status" aria-live="polite" className="fixed inset-x-0 top-4 z-50 flex justify-center px-4">
      <div className="max-w-md rounded-sm border-2 border-ink bg-brand-green px-5 py-3 text-sm font-bold text-ink shadow-lg">{children}</div>
    </div>
  );
}

// Asks before something the person can't easily undo. Esc and "Stay signed in"-style cancel both close it without acting.
export function ConfirmDialog({ title, children, confirmLabel, cancelLabel = "Cancel", onConfirm, onCancel }: { title: string; children?: ReactNode; confirmLabel: string; cancelLabel?: string; onConfirm: () => void; onCancel: () => void }) {
  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center bg-ink/60 p-4" onKeyDown={(e) => { if (e.key === "Escape") onCancel(); }}>
      <div role="alertdialog" aria-modal="true" aria-labelledby="confirm-title" className="w-full max-w-sm rounded-sm border-2 border-ink bg-white p-5 shadow-xl">
        <h2 id="confirm-title" className="text-lg font-bold text-ink">{title}</h2>
        {children && <div className="mt-2 text-sm text-ink">{children}</div>}
        <div className="mt-5 flex justify-end gap-3">
          <button type="button" autoFocus className="rounded-sm border-2 border-ink px-4 py-2 text-sm font-bold text-ink hover:bg-paper" onClick={onCancel}>{cancelLabel}</button>
          <button type="button" className="rounded-sm border-2 border-ink bg-brand-green px-4 py-2 text-sm font-bold text-ink hover:bg-ink hover:text-brand-green" onClick={onConfirm}>{confirmLabel}</button>
        </div>
      </div>
    </div>
  );
}

export function Notice({ tone = "info", children }: { tone?: "info" | "warn" | "ok"; children: ReactNode }) {
  const c = { info: "border-brand-purple bg-lilac text-ink", warn: "border-brand-peach bg-peach-tint text-ink", ok: "border-ink bg-lime-tint text-ink" }[tone];
  return <div role="status" className={`rounded-sm border-2 p-3 text-sm ${c}`}>{children}</div>;
}

// Mandatory disclosure (hard rule 2). Rendered wherever a finished video is shown; not configurable.
export function DisclosureBadge({ text }: { text: string }) {
  return (
    <p className="flex flex-wrap items-center gap-2 text-sm text-ink">
      <span className="rounded-sm bg-brand-peach px-2 py-0.5 font-mono text-xs font-bold uppercase tracking-wide text-ink">Featured</span>
      <span>{text}</span>
    </p>
  );
}
