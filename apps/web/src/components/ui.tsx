import { type ButtonHTMLAttributes, type ReactNode, useId } from "react";

export function Button({ variant = "primary", className = "", ...p }: ButtonHTMLAttributes<HTMLButtonElement> & { variant?: "primary" | "secondary" | "danger" }) {
  const styles = {
    primary: "bg-blue-700 text-white hover:bg-blue-800 disabled:bg-slate-300",
    secondary: "bg-white text-slate-900 border border-slate-300 hover:bg-slate-50 disabled:text-slate-400",
    danger: "bg-red-700 text-white hover:bg-red-800 disabled:bg-slate-300",
  }[variant];
  return (
    <button
      {...p}
      className={`rounded-md px-4 py-2 text-sm font-semibold focus:outline-none focus-visible:ring-2 focus-visible:ring-blue-500 focus-visible:ring-offset-2 disabled:cursor-not-allowed ${styles} ${className}`}
    />
  );
}

export function Card({ title, children, actions }: { title?: string; children: ReactNode; actions?: ReactNode }) {
  return (
    <section className="rounded-lg border border-slate-200 bg-white p-4 shadow-sm sm:p-6">
      {(title || actions) && (
        <div className="mb-4 flex items-center justify-between gap-2">
          {title && <h2 className="text-lg font-semibold text-slate-900">{title}</h2>}
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
      <label htmlFor={id} className="block text-sm font-medium text-slate-800">{label}</label>
      {children(id)}
      {hint && <p className="text-xs text-slate-600">{hint}</p>}
    </div>
  );
}

export const inputCls =
  "w-full rounded-md border border-slate-300 bg-white px-3 py-2 text-sm text-slate-900 focus:border-blue-600 focus:outline-none focus:ring-2 focus:ring-blue-200";

export function ErrorBox({ error }: { error: unknown }) {
  if (!error) return null;
  return (
    <p role="alert" className="rounded-md border border-red-300 bg-red-50 p-3 text-sm text-red-900">
      {error instanceof Error ? error.message : "Something went wrong"}
    </p>
  );
}

export function Notice({ tone = "info", children }: { tone?: "info" | "warn" | "ok"; children: ReactNode }) {
  const c = { info: "border-blue-200 bg-blue-50 text-blue-950", warn: "border-amber-300 bg-amber-50 text-amber-950", ok: "border-green-300 bg-green-50 text-green-950" }[tone];
  return <div role="status" className={`rounded-md border p-3 text-sm ${c}`}>{children}</div>;
}

// Mandatory disclosure (hard rule 2). Rendered wherever a finished video is shown; not configurable.
export function DisclosureBadge({ text }: { text: string }) {
  return (
    <p className="flex flex-wrap items-center gap-2 text-sm text-slate-800">
      <span className="rounded bg-amber-400 px-2 py-0.5 text-xs font-extrabold uppercase tracking-wide text-slate-900">Featured</span>
      <span>{text}</span>
    </p>
  );
}
