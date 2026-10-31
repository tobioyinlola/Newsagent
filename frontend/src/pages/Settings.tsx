import { Link, Outlet, useLocation } from "react-router-dom";
import { useMe } from "../components/Layout";
import { Card } from "../components/ui";
import { Account } from "./Account";

const tabs = [
  { name: "Profile", to: "/settings/profile" },
  { name: "Password", to: "/settings/password" },
  { name: "Billing", to: "/settings/billing" },
  { name: "Referral", to: "/settings/referral" },
];

export function Settings() {
  const location = useLocation();
  return <div className="min-w-0 space-y-6">
    <header><p className="dashboard-eyebrow">YOUR WORKSPACE, YOUR WAY</p><h1 className="mt-2 text-3xl font-bold">Settings</h1><p className="mt-2 text-sm text-muted">Manage your profile, security, credits and referrals in one place.</p></header>
    <nav aria-label="Settings tabs" className="flex gap-2 overflow-x-auto rounded-xl border border-line bg-white p-2">
      {tabs.map(tab => <Link key={tab.to} to={tab.to} aria-current={location.pathname.startsWith(tab.to) ? "page" : undefined} className={`min-h-11 shrink-0 rounded-lg px-5 py-3 text-sm font-bold transition-colors ${location.pathname.startsWith(tab.to) ? "bg-brand-green text-ink" : "text-muted hover:bg-paper"}`}>{tab.name}</Link>)}
    </nav>
    <section className="min-w-0 space-y-5"><Outlet /></section>
  </div>;
}

export function ProfileSettings() {
  const me = useMe();
  return <div className="space-y-5"><Card title="Your profile"><div className="flex items-center gap-4"><span aria-hidden="true" className="flex h-14 w-14 shrink-0 items-center justify-center rounded-full border border-ink bg-brand-green text-xl font-bold">{me.data?.workspace_name.slice(0, 1).toUpperCase() || "CF"}</span><div className="min-w-0"><p className="break-words font-bold">{me.data?.workspace_name}</p><p className="break-all text-sm text-muted">{me.data?.email}</p></div></div><dl className="mt-6 grid gap-4 border-t border-line pt-5 sm:grid-cols-2"><div><dt className="text-xs text-muted">Workspace</dt><dd className="mt-1 break-words font-semibold">{me.data?.workspace_name}</dd></div><div><dt className="text-xs text-muted">Email address</dt><dd className="mt-1 break-all font-semibold">{me.data?.email}</dd></div></dl><Link className="mt-5 inline-flex min-h-11 items-center text-sm font-bold underline" to="/brand">Manage your brand kit →</Link></Card><Account /></div>;
}
