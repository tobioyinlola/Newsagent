import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api, unwrap } from "../api/client";
import { Card, ErrorBox } from "../components/ui";
import { stateLabel } from "../lib/states";
import { videoTitle } from "../lib/title";
import { distributionApi, type Distribution } from "../lib/distribution";
import { analyticsRequest, type AudienceReport } from "../lib/analytics";
import { getToken } from "../lib/auth";

const cta = "rounded-sm border-2 border-ink bg-brand-green px-4 py-2 text-sm font-bold text-ink hover:bg-ink hover:text-brand-green";

// Where people land after signing in: what to do next, and the latest videos.
export function Dashboard() {
  const me = useQuery({ queryKey: ["me"], queryFn: () => unwrap(api.GET("/v1/me")), retry: false });
  const projects = useQuery({ queryKey: ["projects"], queryFn: () => unwrap(api.GET("/v1/projects")) });
  const distributions = useQuery({ queryKey: ["distributions"], queryFn: () => distributionApi<Distribution[]>("distribution", getToken()), refetchInterval: 15000 });
  const audience = useQuery({ queryKey: ["dashboard-audience", getToken()], queryFn: () => analyticsRequest<AudienceReport>("analytics", getToken()), refetchInterval: 60000 });
  const published = (distributions.data ?? []).flatMap(r => (r.placements ?? []).filter(p => p.status === "published" && p.published_url).map(p => ({ ...p, headline: r.data.headline })));
  const list = projects.data ?? [];
  const done = list.filter((p) => p.state === "final_ready").length;
  const recent = list.slice(0, 5);
  const firstName = list.find(p => p.founder_name?.trim())?.founder_name.trim().split(/\s+/)[0];
  const name = firstName || me.data?.workspace_name;
  return <div className="dashboard-design">
    <div className="dashboard-heading"><div><p className="dashboard-eyebrow">YOUR WORKSPACE, AT A GLANCE</p><h1>{name ? `Welcome, ${name}` : "Dashboard"} <span aria-hidden="true">👋</span></h1><p>Let’s give your next story the audience it deserves.</p></div><span className="dashboard-date">{new Date().toLocaleDateString(undefined, { weekday: "long", month: "short", day: "numeric" })}</span></div>
    <ErrorBox error={me.error ?? projects.error ?? distributions.error} />
    <section className="dashboard-hero cf-stripes"><div><p className="dashboard-eyebrow">FROM YOUR IDEA TO THE HEADLINES</p><h2>Your business has a story.<br />Let’s make it news.</h2><p>Create a video, shape your announcement and put your business in front of new audiences.</p><div className="flex flex-wrap gap-3"><Link to="/ai-newsroom/new" className={cta}>Make a video <span aria-hidden="true">→</span></Link><Link to="/distribution/request" className="dashboard-secondary">Distribute your story</Link></div></div><div className="dashboard-hero-note"><span className="dashboard-hero-symbol" aria-hidden="true">CF</span><span>YOUR NEXT<br />BIG CHAPTER.</span><Link to="/latest-stories">Explore the newsroom →</Link></div></section>
    <div className="dashboard-stats">{[
      { label: "Available credits", value: me.data ? Number(me.data.credit_balance).toFixed(2) : "…", detail: "Ready for your next story", link: "/billing", action: "Add credits", icon: "+" },
      { label: "Your videos", value: projects.isLoading ? "…" : String(list.length), detail: `${done} finished${list.length ? ` · ${list.length - done} in your workspace` : ""}`, link: "/ai-newsroom/videos", action: "View videos", icon: "▷" },
      { label: "Press Distributed", value: distributions.isLoading ? "…" : String(published.length), detail: "Published outlet placements", link: "/distribution/request", action: "Manage distribution", icon: "◎" },
    ].map(stat => <section className="dashboard-stat" key={stat.label}><div><h2>{stat.label}</h2><span aria-hidden="true">{stat.icon}</span></div><p className="dashboard-stat-value">{stat.value}</p><p className="text-xs text-muted">{stat.detail}</p><Link to={stat.link}>{stat.action} <span aria-hidden="true">→</span></Link></section>)}</div>
    <div className="dashboard-columns"><section className="dashboard-card"><div className="dashboard-card-heading"><div><p className="dashboard-eyebrow">KEEP YOUR STORY MOVING</p><h2>Recent videos</h2></div><Link to="/ai-newsroom/videos">View all →</Link></div>{projects.isLoading ? <p aria-busy="true">Loading your videos…</p> : recent.length ? <ul className="dashboard-projects">{recent.map((p, i) => <li key={p.id}><Link to={`/ai-newsroom/${p.id}`}><span className={`dashboard-project-number ${p.state === "final_ready" ? "is-ready" : ""}`}>{String(i + 1).padStart(2, "0")}</span><div><p>{videoTitle(me.data?.workspace_name, p.created_at)}</p><span>{new Date(p.created_at).toLocaleDateString(undefined, { month: "short", day: "numeric", year: "numeric" })}</span></div><span className={`dashboard-status ${p.state === "final_ready" ? "is-ready" : ""}`}>{stateLabel(p.state)}</span><span aria-hidden="true">→</span></Link></li>)}</ul> : <div className="dashboard-empty"><span aria-hidden="true">▷</span><h3>Your first story starts here.</h3><p>A short interview is all it takes to get started.</p><Link to="/ai-newsroom/new" className={cta}>Make your first video</Link></div>}</section>
    <section className="dashboard-card dashboard-audience"><p className="dashboard-eyebrow">REAL PEOPLE. REAL REACH.</p><h2>Your audience</h2><p className="text-xs text-muted">Last 30 days · on Cover Founder</p>{audience.data ? <dl>{[["Story visits", audience.data.platform.story_visits], ["Engaged video views", audience.data.platform.video_views], ["Story impressions", audience.data.platform.impressions]].map(([label, value]) => <div key={label}><dt>{label}</dt><dd>{Number(value).toLocaleString()}</dd></div>)}</dl> : <p className="my-6 text-sm text-muted">{audience.isError ? "Audience report is temporarily unavailable." : "Loading audience measurements…"}</p>}<Link to="/analytics">View reports and publisher results →</Link></section></div>
    <section className="dashboard-card"><div className="dashboard-card-heading"><div><p className="dashboard-eyebrow">A LITTLE MOMENTUM GOES A LONG WAY</p><h2>What’s next?</h2></div></div><div className="dashboard-next">{[["01", "Tell your story", "Start with a short interview about your business.", "/ai-newsroom/new"], ["02", "Shape your identity", "Keep your logo and brand assets ready to go.", "/brand"], ["03", "Reach new audiences", "Choose the media outlets for your announcement.", "/distribution/request"]].map(([number, title, detail, to]) => <Link key={number} to={to}><span>{number}</span><h3>{title}</h3><p>{detail}</p><span className="dashboard-next-arrow" aria-hidden="true">→</span></Link>)}</div></section>
    {published.length > 0 && <Card title="Your published press"><ul className="divide-y divide-line">{published.slice(0, 5).map(p => <li key={p.id} className="py-3"><a className="block break-words font-semibold underline" href={p.published_url} target="_blank" rel="noopener noreferrer">{p.name} — {p.headline}</a></li>)}</ul><Link className="mt-3 inline-block min-h-11 py-2 text-sm underline" to="/distribution/request">See all distribution requests and links</Link></Card>}
  </div>;
}
