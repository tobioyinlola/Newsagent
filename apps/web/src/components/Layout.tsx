import { useQuery } from "@tanstack/react-query";
import { Link, NavLink, Outlet, useNavigate } from "react-router-dom";
import { api, unwrap } from "../api/client";
import { signOut } from "../lib/auth";

export function useMe() {
  return useQuery({ queryKey: ["me"], queryFn: () => unwrap(api.GET("/v1/me")), retry: false });
}

const link = ({ isActive }: { isActive: boolean }) =>
  `rounded px-3 py-2 text-sm font-medium ${isActive ? "bg-blue-100 text-blue-900" : "text-slate-700 hover:bg-slate-100"}`;

export function Layout() {
  const me = useMe();
  const nav = useNavigate();
  return (
    <div className="min-h-screen bg-slate-50 text-slate-900">
      <header className="border-b border-slate-200 bg-white">
        <nav aria-label="Main" className="mx-auto flex max-w-5xl flex-wrap items-center gap-1 px-4 py-2">
          <Link to="/projects" className="mr-3 text-lg font-extrabold text-blue-900">Newsagent</Link>
          <NavLink to="/projects" className={link}>Videos</NavLink>
          <NavLink to="/brand" className={link}>Brand kit</NavLink>
          {me.data?.is_operator && <NavLink to="/admin" className={link}>Admin</NavLink>}
          <span className="ml-auto flex items-center gap-3 text-sm text-slate-700">
            {me.data && <span>{me.data.workspace_name} · {Number(me.data.credit_balance).toFixed(2)} credits</span>}
            <button className="underline" onClick={() => { signOut(); nav("/login"); }}>Sign out</button>
          </span>
        </nav>
      </header>
      <main className="mx-auto max-w-5xl space-y-4 px-4 py-6"><Outlet /></main>
    </div>
  );
}
