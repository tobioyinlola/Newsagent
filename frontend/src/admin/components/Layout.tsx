import { type ReactNode, useEffect, useState } from "react";
import { Link, NavLink, Outlet, useLocation, useNavigate } from "react-router-dom";
import { api } from "../api/client";
import { signOut } from "../lib/auth";
import { CFSymbol, SecondaryLogo } from "./Logo";
import { ConfirmDialog } from "./ui";
import { useCan } from "../lib/can";
import { useMe } from "./RequireOperator";

const KEY = "newsagent.admin.sidebar";
const readCollapsed = () => {
  try { return localStorage.getItem(KEY) === "collapsed"; } catch { return false; }
};

const Icon = ({ children }: { children: ReactNode }) => (
  <svg viewBox="0 0 24 24" width="22" height="22" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="square" strokeLinejoin="miter" aria-hidden className="shrink-0">{children}</svg>
);
const I = {
  overview: <Icon><rect x="3" y="3" width="8" height="10" /><rect x="13" y="3" width="8" height="6" /><rect x="13" y="11" width="8" height="10" /><rect x="3" y="15" width="8" height="6" /></Icon>,
  customers: <Icon><circle cx="9" cy="8" r="3.5" /><path d="M2 20c0-4 3-6 7-6s7 2 7 6M17 5a3.5 3.5 0 010 7M19 14c2 .8 3 2.6 3 5" /></Icon>,
  revenue: <Icon><circle cx="12" cy="12" r="9" /><path d="M12 7v10M9 10h6M9 14h6" /></Icon>,
  ops: <Icon><path d="M4 6h16M4 12h16M4 18h16" /><circle cx="9" cy="6" r="2" fill="currentColor" /><circle cx="15" cy="12" r="2" fill="currentColor" /><circle cx="8" cy="18" r="2" fill="currentColor" /></Icon>,
  review: <Icon><path d="M4 4h16v12H8l-4 4z" /><path d="M8 9h8M8 12h5" /></Icon>,
  jobs: <Icon><rect x="3" y="4" width="18" height="16" /><path d="M3 9h18M8 4v5" /></Icon>,
  costs: <Icon><path d="M4 20V10M10 20V4M16 20v-8M22 20H2" /></Icon>,
  clips: <Icon><rect x="3" y="5" width="18" height="14" /><path d="M10 9l5 3-5 3z" fill="currentColor" /></Icon>,
  packs: <Icon><path d="M3 8l9-5 9 5v8l-9 5-9-5z" /><path d="M3 8l9 5 9-5M12 13v8" /></Icon>,
  setup: <Icon><circle cx="12" cy="12" r="3" /><path d="M12 2v3M12 19v3M2 12h3M19 12h3M5 5l2 2M17 17l2 2M19 5l-2 2M7 17l-2 2" /></Icon>,
  audit: <Icon><path d="M6 3h9l4 4v14H6z" /><path d="M9 12h7M9 16h7" /></Icon>,
  team: <Icon><circle cx="9" cy="8" r="3.5" /><path d="M2 20c0-4 3-6 7-6s7 2 7 6" /><path d="M19 8v6M16 11h6" /></Icon>,
  security: <Icon><rect x="5" y="11" width="14" height="10" /><path d="M8 11V7a4 4 0 018 0v4" /></Icon>,
  out: <Icon><path d="M9 4H4v16h5M16 8l4 4-4 4M20 12H9" /></Icon>,
};

// [path, label, icon, the permissions that open it (any one of them); none listed = everyone on the team]
type Item = [string, string, ReactNode, string[]];
const GROUPS: { title: string; items: Item[] }[] = [
  { title: "Business", items: [["/", "Overview", I.overview, ["overview.view"]], ["/customers", "Customers", I.customers, ["customers.view"]], ["/revenue", "Revenue", I.revenue, ["finance.view"]]] },
  { title: "Operations", items: [["/operations", "Operations", I.ops, ["operations.view"]], ["/review", "Review queue", I.review, ["review.manage"]], ["/jobs", "Jobs", I.jobs, ["operations.view"]], ["/costs", "Costs", I.costs, ["finance.view"]]] },
  { title: "Admin", items: [["/presenter", "Presenter clips", I.clips, ["presenter.manage"]], ["/billing", "Credit packs", I.packs, ["finance.view"]], ["/setup", "Setup", I.setup, ["customers.manage", "finance.view"]], ["/team", "Team", I.team, ["team.manage"]], ["/audit", "Audit log", I.audit, ["audit.view"]]] },
  { title: "You", items: [["/security", "Security", I.security, []]] },
];

// The back office's own shell: a collapsible sidebar (a slide-over from the right on phones).
export function Layout() {
  const me = useMe();
  const can = useCan();
  const nav = useNavigate();
  const loc = useLocation();
  const [collapsed, setCollapsed] = useState(readCollapsed);
  const [open, setOpen] = useState(false);
  useEffect(() => setOpen(false), [loc.pathname]);
  useEffect(() => {
    if (!open) return;
    const onKey = (e: KeyboardEvent) => { if (e.key === "Escape") setOpen(false); };
    window.addEventListener("keydown", onKey);
    return () => window.removeEventListener("keydown", onKey);
  }, [open]);
  const toggle = () => setCollapsed((c) => {
    try { localStorage.setItem(KEY, c ? "expanded" : "collapsed"); } catch { /* lasts until reload */ }
    return !c;
  });
  const rail = collapsed && !open;
  const [confirmOut, setConfirmOut] = useState(false);
  const signOutNow = async () => { await api.POST("/v1/auth/logout").catch(() => undefined); signOut(); nav("/login"); };

  return (
    <div className="min-h-screen bg-paper text-ink md:flex">
      {confirmOut && <ConfirmDialog title="Sign out?" confirmLabel="Sign out" cancelLabel="Stay signed in" onConfirm={() => { setConfirmOut(false); void signOutNow(); }} onCancel={() => setConfirmOut(false)}>You will need to sign in again to get back to the back office.</ConfirmDialog>}
      <div className="flex items-center justify-between bg-ink px-4 py-2 md:hidden">
        <Link to="/" className="flex items-center gap-2 text-brand-green" aria-label="Back office home">
          <SecondaryLogo className="h-8 w-auto" />
          <span className="rounded-sm bg-brand-purple px-1.5 py-0.5 font-mono text-[10px] font-bold uppercase tracking-widest text-white">Back office</span>
        </Link>
        <button type="button" className="rounded-sm border-2 border-brand-green px-3 py-1.5 text-sm font-bold text-brand-green" aria-expanded={open} aria-controls="sidebar" onClick={() => setOpen(true)}>Menu</button>
      </div>
      {open && <div className="fixed inset-0 z-20 bg-ink/60 md:hidden" aria-hidden onClick={() => setOpen(false)} />}
      <aside
        id="sidebar"
        className={`fixed inset-y-0 right-0 z-30 w-72 max-w-[85vw] overflow-y-auto bg-ink transition-transform duration-200 md:sticky md:top-0 md:z-auto md:h-screen md:max-w-none md:shrink-0 md:translate-x-0 md:visible ${collapsed ? "md:w-[72px]" : "md:w-64"} ${open ? "translate-x-0" : "invisible translate-x-full"}`}
      >
        <nav aria-label="Back office" className="flex h-full flex-col gap-1 p-3">
          <div className="mb-2 flex items-center justify-between md:hidden">
            <span className="font-mono text-lg font-bold text-white">Menu</span>
            <button type="button" className="rounded-sm border-2 border-brand-green px-3 py-1.5 text-sm font-bold text-brand-green" onClick={() => setOpen(false)}>Close</button>
          </div>
          <Link to="/" className={`mb-3 hidden items-center gap-2 px-1 py-1 text-brand-green md:flex ${rail ? "justify-center" : ""}`} aria-label="Back office home">
            {rail ? <CFSymbol className="h-8 w-auto" /> : <span className="flex flex-col items-start gap-1.5"><SecondaryLogo className="h-9 w-auto" /><span className="rounded-sm bg-brand-purple px-1.5 py-0.5 font-mono text-[10px] font-bold uppercase tracking-widest text-white">Back office</span></span>}
          </Link>
          {GROUPS.map((g) => ({ ...g, items: g.items.filter(([, , , need]) => need.length === 0 || can(...need)) })).filter((g) => g.items.length > 0).map((g) => (
            <div key={g.title} className="space-y-1 pb-2">
              {!rail && <p className="px-3 pt-2 font-mono text-[11px] font-bold uppercase tracking-widest text-brand-green">{g.title}</p>}
              {rail && <div className="mx-2 border-t-2 border-stripe" aria-hidden />}
              {g.items.map(([to, label, icon]) => (
                <NavLink
                  key={to}
                  to={to}
                  end={to === "/"}
                  title={rail ? label : undefined}
                  className={({ isActive }) => `flex items-center gap-3 rounded-sm px-3 py-2.5 text-sm font-bold ${rail ? "justify-center" : ""} ${isActive ? "bg-brand-purple text-white" : "text-white hover:bg-stripe"}`}
                >
                  {icon}
                  <span className={rail ? "sr-only" : ""}>{label}</span>
                </NavLink>
              ))}
            </div>
          ))}
          <div className="mt-auto space-y-2 border-t-2 border-stripe pt-3">
            {me.data && !rail && <div className="px-3 text-sm text-white"><p className="truncate" title={me.data.email}>{me.data.email}</p>{me.data.staff_role && <p className="font-mono text-[11px] font-bold uppercase tracking-widest text-brand-green">{me.data.staff_role}</p>}</div>}
            <button type="button" onClick={() => setConfirmOut(true)} title={rail ? "Sign out" : undefined} className={`flex w-full items-center gap-3 rounded-sm px-3 py-2.5 text-sm font-bold text-brand-green hover:bg-stripe ${rail ? "justify-center" : ""}`}>
              {I.out}<span className={rail ? "sr-only" : ""}>Sign out</span>
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
        <div className="mx-auto max-w-6xl space-y-4 px-4 py-6">
          <Outlet />
        </div>
      </main>
    </div>
  );
}
