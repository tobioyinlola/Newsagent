import { useQuery } from "@tanstack/react-query";
import { Link, NavLink, Outlet, useNavigate } from "react-router-dom";
import { api, unwrap } from "../api/client";
import { signOut } from "../lib/auth";
import { CFSymbol } from "./Logo";

export function useMe() {
  return useQuery({ queryKey: ["me"], queryFn: () => unwrap(api.GET("/v1/me")), retry: false });
}

const link = ({ isActive }: { isActive: boolean }) =>
  `rounded-sm px-3 py-2 text-sm font-bold ${isActive ? "bg-brand-green text-ink" : "text-white hover:bg-stripe"}`;

export function Layout() {
  const me = useMe();
  const nav = useNavigate();
  return (
    <div className="min-h-screen bg-paper text-ink">
      <header className="bg-ink">
        <nav aria-label="Main" className="mx-auto flex max-w-5xl flex-wrap items-center gap-1 px-4 py-2">
          <Link to="/projects" className="mr-4 flex items-center gap-2 text-brand-green" aria-label="Cover Founder home">
            <CFSymbol className="h-8 w-auto" />
            <span className="font-mono text-lg font-bold text-white">Cover Founder</span>
          </Link>
          <NavLink to="/projects" className={link}>Videos</NavLink>
          <NavLink to="/brand" className={link}>Brand kit</NavLink>
          <NavLink to="/billing" className={link}>Credits</NavLink>
          <NavLink to="/account" className={link}>Your data</NavLink>
          <NavLink to="/security" className={link}>Security</NavLink>
          {me.data?.is_operator && <NavLink to="/admin" className={link}>Admin</NavLink>}
          <span className="ml-auto flex items-center gap-3 text-sm text-white">
            {me.data && <span>{me.data.workspace_name} · {Number(me.data.credit_balance).toFixed(2)} credits</span>}
            <button className="font-bold text-brand-green underline" onClick={async () => { await api.POST("/v1/auth/logout").catch(() => undefined); signOut(); nav("/login"); }}>Sign out</button>
          </span>
        </nav>
      </header>
      <main className="mx-auto max-w-5xl space-y-4 px-4 py-6">
        <Outlet />
      </main>
    </div>
  );
}
