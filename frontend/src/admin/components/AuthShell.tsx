import { type ReactNode } from "react";
import { AuthShowcase } from "../../components/AuthShowcase";
import { SecondaryLogo } from "../../components/Logo";
import { BackButton } from "../../components/BackButton";

export function AdminAuthShell({ children }: { children: ReactNode }) {
  return <div className="auth-page"><header className="border-b border-white/10 bg-ink px-5 py-4 text-white"><nav aria-label="Back office public navigation" className="mx-auto flex max-w-6xl items-center justify-between gap-4"><a href="/" aria-label="Cover Founder home"><SecondaryLogo className="h-9 w-auto text-brand-green" /></a><div className="flex items-center gap-4 text-sm"><span className="hidden rounded-full border border-white/20 px-3 py-1 text-xs font-bold text-brand-green sm:inline">BACK OFFICE</span><a className="underline underline-offset-4" href="/">Visit website ↗</a></div></nav></header><main className="auth-layout"><AuthShowcase admin /><section className="auth-form-panel" aria-label="Team account access" tabIndex={0}><div className="auth-form-content"><BackButton fallback="/login" className="mb-4" /><div className="auth-form-intro"><span className="auth-eyebrow">YOUR COVER FOUNDER CONTROL ROOM</span><p>A good day for a great story.</p></div><div className="auth-fields">{children}</div><div className="auth-form-footer"><span aria-hidden="true">✳</span><p>For the team behind the headlines.</p><a className="underline" href="/login">Customer sign-in</a></div></div></section></main></div>;
}
