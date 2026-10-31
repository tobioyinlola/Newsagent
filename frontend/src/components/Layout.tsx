import { useQuery } from "@tanstack/react-query";
import { type ReactNode, useEffect, useState } from "react";
import { OutOfCredits } from "./OutOfCredits";
import { Link, NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { api, unwrap } from "../api/client";
import { signOut } from "../lib/auth";
import { CFSymbol, SecondaryLogo } from "./Logo";
import { ConfirmDialog } from "./ui";

export function useMe() {
  return useQuery({ queryKey: ["me"], queryFn: () => unwrap(api.GET("/v1/me")), retry: false });
}

const KEY = "newsagent.sidebar";
const readCollapsed = () => {
  try { return localStorage.getItem(KEY) === "collapsed"; } catch { return false; }
};

const Icon = ({ children }: { children: ReactNode }) => (
  <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="square" strokeLinejoin="miter" aria-hidden className="shrink-0">{children}</svg>
);
const ICONS = {
  home: <Icon><path d="M3 11l9-7 9 7v9H3z" /><path d="M9 20v-6h6v6" /></Icon>,
  videos: <Icon><rect x="3" y="5" width="18" height="14" /><path d="M10 9v6l5-3z" /></Icon>,
  brand: <Icon><rect x="3" y="3" width="18" height="18" /><path d="M12 3v18M3 15h9" /></Icon>,
  credits: <Icon><circle cx="12" cy="12" r="9" /><path d="M12 7v10M9 10h6M9 14h6" /></Icon>,
  data: <Icon><path d="M12 3l8 3v6c0 5-3.5 8-8 9-4.5-1-8-4-8-9V6z" /></Icon>,
  security: <Icon><rect x="5" y="11" width="14" height="10" /><path d="M8 11V7a4 4 0 018 0v4" /></Icon>,
  out: <Icon><path d="M9 4H4v16h5M16 8l4 4-4 4M20 12H9" /></Icon>,
};

// With mock providers the presenter, voices and transcripts are stand-ins. Say so, so a demo is never mistaken for output.
function DemoBanner() {
  const caps = useQuery({ queryKey: ["capabilities"], queryFn: () => unwrap(api.GET("/v1/capabilities")), staleTime: 600000, retry: false });
  const c = caps.data as { demo_mode?: boolean; message?: string | null } | undefined;
  if (!c?.demo_mode) return null;
  return <div role="note" className="rounded-sm border-2 border-brand-peach bg-peach-tint p-3 text-sm text-ink"><strong>Demo mode.</strong> {c.message ?? "The presenter and voices are stand-ins."}</div>;
}

// Collapsible sidebar: full width with labels, or a narrow icon rail (remembered between visits).
// On phones it becomes a slide-over opened from a top bar.
export function Layout() {
  const me = useMe();
  const nav = useNavigate();
  const [collapsed, setCollapsed] = useState(readCollapsed);
  const [open, setOpen] = useState(false); // phone slide-over
  const loc = useLocation();
  useEffect(() => setOpen(false), [loc.pathname]);
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);
  const toggle = () => {
    setCollapsed((c) => {
      try { localStorage.setItem(KEY, c ? "expanded" : "collapsed"); } catch { /* storage unavailable: lasts until reload */ }
      return !c;
    });
  };
  const rail = collapsed && !open; // the phone slide-over is always full width

  const item = (to: string, label: string, icon: ReactNode) => (
    <NavLink
      to={to}
      title={rail ? label : undefined}
      className={({ isActive }) =>
        `flex items-center gap-3 rounded-sm px-3 py-2.5 text-sm font-bold ${rail ? "justify-center" : ""} ${isActive ? "bg-brand-green text-ink" : "text-white hover:bg-stripe"}`
      }
    >
      {icon}
      <span className={rail ? "sr-only" : ""}>{label}</span>
    </NavLink>
  );
  const [confirmOut, setConfirmOut] = useState(false);
  const signOutNow = async () => { await api.POST("/v1/auth/logout").catch(() => undefined); signOut(); nav("/login"); };

  return (
    <div className="min-h-screen bg-paper text-ink md:flex">
      {confirmOut && <ConfirmDialog title="Sign out?" confirmLabel="Sign out" cancelLabel="Stay signed in" onConfirm={() => { setConfirmOut(false); void signOutNow(); }} onCancel={() => setConfirmOut(false)}>You will need to sign in again to get back to your work.</ConfirmDialog>}
      {/* phone top bar */}
      <div className="flex items-center justify-between bg-ink px-4 py-2 md:hidden">
        <Link to="/dashboard" className="flex items-center gap-2 text-brand-green" aria-label="Cover Founder home">
          <SecondaryLogo className="h-8 w-auto" />
        </Link>
        <button type="button" className="rounded-sm border-2 border-brand-green px-3 py-1.5 text-sm font-bold text-brand-green" aria-expanded={open} aria-controls="sidebar" onClick={() => setOpen(true)}>
          Menu
        </button>
      </div>

      {/* phone scrim: tap outside the menu to close it */}
      {open && <div className="fixed inset-0 z-20 bg-ink/60 md:hidden" aria-hidden onClick={() => setOpen(false)} />}

      {/* On phones the menu slides in from the right; from md up it is the static sidebar. */}
      <aside
        id="sidebar"
        className={`fixed inset-y-0 right-0 z-30 w-72 max-w-[85vw] overflow-y-auto bg-ink transition-transform duration-200 md:sticky md:top-0 md:right-auto md:bottom-auto md:transition-none md:z-auto md:h-screen md:max-w-none md:shrink-0 md:translate-x-0 md:visible ${collapsed ? "md:w-[72px]" : "md:w-64"} ${open ? "translate-x-0" : "invisible translate-x-full"}`}
      >
        <nav aria-label="Main" className="flex h-full flex-col gap-1 p-3">
          <div className="mb-2 flex items-center justify-between md:hidden">
            <span className="font-mono text-lg font-bold text-white">Menu</span>
            <button type="button" className="rounded-sm border-2 border-brand-green px-3 py-1.5 text-sm font-bold text-brand-green" onClick={() => setOpen(false)}>Close</button>
          </div>
          <Link to="/dashboard" className={`mb-4 hidden items-center gap-2 px-1 py-1 text-brand-green md:flex ${rail ? "justify-center" : ""}`} aria-label="Cover Founder home">
            {rail ? <CFSymbol className="h-8 w-auto" /> : <SecondaryLogo className="h-9 w-auto" />}
          </Link>

          {item("/dashboard", "Dashboard", ICONS.home)}
          {item("/ai-newsroom/videos", "Videos", ICONS.videos)}
          {item("/brand", "Brand kit", ICONS.brand)}
          {item("/distribution/request", "Distribution", ICONS.videos)}
          {item("/analytics", "Analytics", ICONS.videos)}
          {item("/billing", "Credits", ICONS.credits)}
          {item("/referrals", "Referrals", ICONS.credits)}
          {item("/account", "Your data", ICONS.data)}
          {item("/security", "Security", ICONS.security)}

          <div className="mt-auto space-y-2 border-t-2 border-stripe pt-3">
            {me.data && !rail && (
              <p className="px-3 text-sm text-white">
                <span className="block font-bold">{me.data.workspace_name}</span>
                <span className="text-brand-green">{Number(me.data.credit_balance).toFixed(2)} credits</span>
              </p>
            )}
            {me.data && rail && (
              <p className="text-center font-mono text-xs font-bold text-brand-green" title={`${me.data.workspace_name}: ${Number(me.data.credit_balance).toFixed(2)} credits`}>
                {Number(me.data.credit_balance).toFixed(0)}
                <span className="sr-only"> credits in {me.data.workspace_name}</span>
              </p>
            )}
            <button type="button" onClick={() => setConfirmOut(true)} title={rail ? "Sign out" : undefined} className={`flex w-full items-center gap-3 rounded-sm px-3 py-2.5 text-sm font-bold text-brand-green hover:bg-stripe ${rail ? "justify-center" : ""}`}>
              {ICONS.out}
              <span className={rail ? "sr-only" : ""}>Sign out</span>
            </button>
            <button
              type="button"
              onClick={toggle}
              aria-expanded={!collapsed}
              aria-controls="sidebar"
              title={collapsed ? "Expand sidebar" : "Collapse sidebar"}
              className={`hidden w-full items-center gap-3 rounded-sm px-3 py-2.5 text-sm font-bold text-white hover:bg-stripe md:flex ${collapsed ? "justify-center" : ""}`}
            >
              <Icon>{collapsed ? <path d="M9 5l7 7-7 7" /> : <path d="M15 5l-7 7 7 7" />}</Icon>
              <span className={collapsed ? "sr-only" : ""}>{collapsed ? "Expand sidebar" : "Collapse sidebar"}</span>
            </button>
          </div>
        </nav>
      </aside>

      <main className="min-w-0 flex-1">
        <div className="mx-auto max-w-5xl space-y-4 px-4 py-6">
          <DemoBanner />
          <Outlet />
          <OutOfCredits />
        </div>
      </main>
    </div>
  );
}
