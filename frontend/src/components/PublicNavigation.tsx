import { type ReactNode, useCallback, useEffect, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { SecondaryLogo } from "./Logo";
import { getToken } from "../lib/auth";

const NAV: [string, string][] = [["Featured Stories", "/latest-stories"], ["News", "/cf-news"], ["AI Newsroom", "/ai-newsroom"], ["Press Distribution", "/press-distribution"]];

// A site link: a page of the app (client-side) or a section of the home page (a normal link, so the browser scrolls to it).
export function SiteLink({ to, className, onClick, children }: { to: string; className: string; onClick?: () => void; children: ReactNode }) {
  return to.startsWith("/") && !to.includes("#") ? <Link to={to} className={className} onClick={onClick}>{children}</Link> : <a href={to} className={className} onClick={onClick}>{children}</a>;
}

// Phones and tablets: the site menu slides in from the right edge over a dimmed page. Esc, the scrim, Close or any link closes it.
function MobileMenu({ open, onClose, signedIn }: { open: boolean; onClose: () => void; signedIn: boolean }) {
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") onClose(); };
    window.addEventListener("keydown", onKey);
    const prev = document.body.style.overflow;
    document.body.style.overflow = "hidden"; // the page behind doesn't scroll while the menu is open
    return () => { window.removeEventListener("keydown", onKey); document.body.style.overflow = prev; };
  }, [open, onClose]);
  return (
    <div className="md:hidden">
      <div aria-hidden="true" onClick={onClose} className={`fixed inset-0 z-50 bg-ink/70 transition-opacity duration-200 ${open ? "opacity-100" : "pointer-events-none opacity-0"}`} />
      <div id="site-menu" role="dialog" aria-modal="true" aria-label="Menu" className={`fixed inset-y-0 right-0 z-50 flex w-80 max-w-[85vw] flex-col border-l border-white/10 bg-ink p-5 transition-transform duration-200 ${open ? "translate-x-0" : "invisible translate-x-full"}`}>
        <div className="flex items-center justify-between">
          <span className="font-mono text-lg font-bold text-white">Menu</span>
          <button type="button" onClick={onClose} className="rounded-sm border-2 border-brand-green px-3 py-1.5 text-sm font-bold text-brand-green">Close</button>
        </div>
        <nav aria-label="Site (mobile)" className="mt-6 flex flex-col">
          {NAV.map(([l, h]) => <SiteLink key={h} to={h} onClick={onClose} className="border-b border-white/10 py-4 text-lg font-bold text-white hover:text-brand-green">{l}</SiteLink>)}
        </nav>
        <div className="mt-auto flex flex-col gap-3 pt-6">
          {signedIn ? <Link to="/dashboard" onClick={onClose} className="rounded-sm border-2 border-brand-green bg-brand-green px-4 py-3 text-center font-bold text-ink">Dashboard</Link> : (
            <>
              <Link to="/signup" onClick={onClose} className="rounded-sm border-2 border-brand-green bg-brand-green px-4 py-3 text-center font-bold text-ink">Sign up now!</Link>
              <Link to="/login" onClick={onClose} className="rounded-sm border-2 border-white/60 px-4 py-3 text-center font-bold text-white">Sign in</Link>
            </>
          )}
        </div>
      </div>
    </div>
  );
}

export function PublicNavigation() {
  const signedIn = Boolean(getToken());
  const [menu, setMenu] = useState(false);
  const closeMenu = useCallback(() => setMenu(false), []);
  const location = useLocation();
  const active = (path: string) => location.pathname === path || location.pathname.startsWith(`${path}/`);
  return <>
      <header className="sticky top-0 z-40 border-b border-white/10 bg-ink/90 shadow-[0_8px_30px_rgba(0,0,0,0.12)] backdrop-blur-xl">
        <nav aria-label="Site" className="mx-auto flex h-[4.5rem] max-w-6xl items-center justify-between gap-4 px-4 md:px-8">
          <Link to="/" className="flex shrink-0 items-center gap-3 text-brand-green" aria-label="Cover Founder home"><SecondaryLogo className="h-9 w-auto" /><span className="hidden border-l border-white/20 pl-3 font-mono text-[10px] font-bold uppercase tracking-[0.18em] text-white/45 xl:inline">AI newsroom</span></Link>
          <div className="hidden items-center gap-1 rounded-full border border-white/10 bg-white/[0.04] p-1 text-sm text-white/70 md:flex">
            {NAV.map(([l, h]) => <SiteLink key={h} to={h} className={`whitespace-nowrap rounded-full px-3 py-2 transition-colors ${active(h) ? "bg-brand-green font-bold text-ink" : "hover:bg-white/10 hover:text-white"}`} aria-current={active(h) ? "page" : undefined}>{l}</SiteLink>)}
          </div>
          <div className="flex items-center gap-2">
            {signedIn ? <Link to="/dashboard" className="rounded-full border border-brand-green bg-brand-green px-4 py-2 text-sm font-bold text-ink transition-colors hover:bg-white">Dashboard</Link> : (
              <><Link to="/login" className="whitespace-nowrap rounded-full border border-white/40 px-4 py-2 text-sm font-bold transition-colors hover:border-brand-green hover:text-brand-green">Sign in</Link>
              <Link to="/signup" className="hidden whitespace-nowrap rounded-full border border-brand-green bg-brand-green px-4 py-2 text-sm font-bold text-ink transition-colors hover:bg-white lg:inline-block">Sign up now!</Link></>
            )}
            <button type="button" onClick={() => setMenu(true)} aria-expanded={menu} aria-controls="site-menu" aria-label="Open menu" className="flex h-10 w-10 items-center justify-center rounded-full border border-brand-green text-brand-green transition-colors hover:bg-brand-green hover:text-ink md:hidden">
              <svg viewBox="0 0 24 24" width="20" height="20" aria-hidden="true" fill="none" stroke="currentColor" strokeWidth="2.5"><path d="M4 7h16M4 12h16M4 17h16" /></svg>
            </button>
          </div>
        </nav>
      </header>
      <MobileMenu open={menu} onClose={closeMenu} signedIn={signedIn} />
  </>;
}
