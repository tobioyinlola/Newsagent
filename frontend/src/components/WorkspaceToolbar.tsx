import { useQuery } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { Link, useLocation } from "react-router-dom";
import { api, unwrap } from "../api/client";
import { distributionApi, type Distribution } from "../lib/distribution";
import { getToken } from "../lib/auth";
import { videoTitle } from "../lib/title";
import { useMe } from "./Layout";

const Icon = ({ kind }: { kind: "search" | "bell" | "settings" }) => <svg width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="1.7" aria-hidden="true">{kind === "search" ? <><circle cx="10.5" cy="10.5" r="6.5" /><path d="m16 16 5 5" /></> : kind === "bell" ? <><path d="M5 17h14l-2-3V9a5 5 0 0 0-10 0v5Z" /><path d="M10 20h4" /></> : <><circle cx="12" cy="12" r="3" /><path d="m9 3 6 0 1 3 3 1 2 5-2 5-3 1-1 3H9l-1-3-3-1-2-5 2-5 3-1Z" /></>}</svg>;
const destinations = [{ title: "Make a video", to: "/ai-newsroom/new" }, { title: "Your videos", to: "/ai-newsroom/videos" }, { title: "Press distribution", to: "/distribution/request" }, { title: "Buy credits and payment history", to: "/billing" }, { title: "Audience analytics", to: "/analytics" }, { title: "Brand kit", to: "/brand" }, { title: "Referrals", to: "/referrals" }];

export function WorkspaceToolbar() {
  const me = useMe(); const location = useLocation();
  const projects = useQuery({ queryKey: ["projects"], queryFn: () => unwrap(api.GET("/v1/projects")) });
  const distributions = useQuery({ queryKey: ["distributions"], queryFn: () => distributionApi<Distribution[]>("distribution", getToken()), refetchInterval: 15000 });
  const [search, setSearch] = useState(""); const [panel, setPanel] = useState<"search" | "notifications" | "settings" | null>(null);
  const [seen, setSeen] = useState<string[]>([]); const ref = useRef<HTMLDivElement>(null);
  const key = `newsagent.activity.${me.data?.workspace_id ?? ""}`;
  useEffect(() => { try { const value = JSON.parse(localStorage.getItem(key) ?? "[]"); setSeen(Array.isArray(value) ? value : []); } catch { setSeen([]); } }, [key]);
  useEffect(() => { setPanel(null); setSearch(""); }, [location.pathname]);
  useEffect(() => {
    const outside = (e: PointerEvent) => { if (!ref.current?.contains(e.target as Node)) setPanel(null); };
    const escape = (e: KeyboardEvent) => { if (e.key === "Escape") setPanel(null); };
    document.addEventListener("pointerdown", outside); document.addEventListener("keydown", escape);
    return () => { document.removeEventListener("pointerdown", outside); document.removeEventListener("keydown", escape); };
  }, []);
  const activity = [
    ...(projects.data ?? []).filter(p => ["final_ready", "failed", "needs_retake"].includes(p.state)).map(p => ({ id: `${p.id}:${p.state}`, title: p.state === "final_ready" ? "Your video is ready" : "Your video needs attention", detail: videoTitle(me.data?.workspace_name, p.created_at), to: `/ai-newsroom/${p.id}` })),
    ...(distributions.data ?? []).flatMap(d => (d.placements ?? []).filter(p => p.status === "published").map(p => ({ id: `${p.id}:published`, title: `Published on ${p.name}`, detail: d.data.headline, to: `/distribution/request?draft=${d.id}` }))),
  ];
  const unread = activity.filter(a => !seen.includes(a.id)).length;
  const results = [...destinations, ...(projects.data ?? []).map(p => ({ title: p.founder_name ? `${p.founder_name} · ${videoTitle(me.data?.workspace_name, p.created_at)}` : videoTitle(me.data?.workspace_name, p.created_at), to: `/ai-newsroom/${p.id}` })), ...(distributions.data ?? []).map(d => ({ title: `Distribution · ${d.data.headline || "Untitled draft"}`, to: `/distribution/request?draft=${d.id}` }))].filter(x => x.title.toLowerCase().includes(search.toLowerCase())).slice(0, 8);
  return <div className="workspace-toolbar" ref={ref}><div className="workspace-search"><Icon kind="search" /><input aria-label="Search your workspace" placeholder="Search your workspace…" value={search} onFocus={() => setPanel("search")} onChange={e => { setSearch(e.target.value); setPanel("search"); }} />{search && <button type="button" aria-label="Clear search" onClick={() => setSearch("")}>×</button>}</div><div className="workspace-tools"><button type="button" aria-label={`Notifications${unread ? ` (${unread} unread)` : ""}`} aria-expanded={panel === "notifications"} aria-controls="workspace-popover" onClick={() => setPanel(panel === "notifications" ? null : "notifications")}><Icon kind="bell" />{unread > 0 && <span className="workspace-unread">{unread}</span>}</button><button type="button" aria-label="Settings" aria-expanded={panel === "settings"} aria-controls="workspace-popover" onClick={() => setPanel(panel === "settings" ? null : "settings")}><Icon kind="settings" /></button><Link className="workspace-avatar" to="/account" aria-label="Your account">{me.data?.workspace_name.slice(0, 1).toUpperCase() || "CF"}</Link></div>
    {panel && <section id="workspace-popover" className={`workspace-popover ${panel === "search" ? "workspace-popover-search" : ""}`} aria-label={panel === "search" ? "Search results" : panel === "settings" ? "Workspace settings" : "Workspace notifications"}><div className="flex items-center justify-between gap-3"><h2 className="text-sm font-bold">{panel === "search" ? "Find in your workspace" : panel === "settings" ? "Workspace settings" : "Your activity"}</h2><button type="button" className="min-h-10 px-2 text-sm" aria-label="Close workspace panel" onClick={() => setPanel(null)}>×</button></div>
    {panel === "search" && <>{projects.isError || distributions.isError ? <p className="text-xs text-muted">Some workspace items could not be loaded. Page shortcuts are still available.</p> : null}{results.length ? results.map(r => <Link key={r.to} to={r.to} onClick={() => setPanel(null)}>{r.title}<span aria-hidden="true">→</span></Link>) : <p className="py-4 text-sm text-muted">No results for “{search}”. Try videos, credits or distribution.</p>}</>}
    {panel === "settings" && <>{[["Brand kit", "/brand"], ["Account and data", "/account"], ["Password and security", "/security"], ["Credits and payments", "/billing"]].map(([label, to]) => <Link key={to} to={to}>{label}<span aria-hidden="true">→</span></Link>)}</>}
    {panel === "notifications" && <>{!!unread && <button type="button" className="my-2 min-h-10 text-xs font-bold underline" onClick={() => { const ids = activity.map(a => a.id); setSeen(ids); try { localStorage.setItem(key, JSON.stringify(ids)); } catch { /* read state remains available in this tab */ } }}>Mark all as read</button>}{activity.length ? <div className="max-h-80 overflow-y-auto">{activity.map(a => <Link key={a.id} to={a.to}><div><p className="font-semibold">{!seen.includes(a.id) && <span className="mr-1 text-brand-purple" aria-label="Unread">●</span>}{a.title}</p><p className="mt-1 text-xs text-muted">{a.detail}</p></div><span aria-hidden="true">→</span></Link>)}</div> : <p className="py-4 text-sm text-muted">{projects.isError || distributions.isError ? "Activity could not be loaded. Please try again shortly." : "You’re all caught up. Completed videos and published placements will appear here."}</p>}<p className="mt-3 border-t border-line pt-3 text-xs text-muted">Activity from your workspace. Read status is saved on this device.</p></>}
    </section>}
  </div>;
}
