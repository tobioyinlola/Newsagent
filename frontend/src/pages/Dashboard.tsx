import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api, unwrap } from "../api/client";
import { Card, ErrorBox } from "../components/ui";
import { stateLabel } from "../lib/states";

const cta = "rounded-sm border-2 border-ink bg-brand-green px-4 py-2 text-sm font-bold text-ink hover:bg-ink hover:text-brand-green";

// Where people land after signing in: what to do next, and the latest videos.
export function Dashboard() {
  const me = useQuery({ queryKey: ["me"], queryFn: () => unwrap(api.GET("/v1/me")), retry: false });
  const projects = useQuery({ queryKey: ["projects"], queryFn: () => unwrap(api.GET("/v1/projects")) });
  const list = projects.data ?? [];
  const done = list.filter((p) => p.state === "final_ready").length;
  const recent = list.slice(0, 5);
  return (
    <>
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-2xl font-bold">{me.data ? `Welcome, ${me.data.workspace_name}` : "Dashboard"}</h1>
        <Link to="/projects/new" className={cta}>Make a video</Link>
      </div>
      <ErrorBox error={me.error ?? projects.error} />
      <div className="grid gap-4 sm:grid-cols-3">
        <Card title="Credits"><p className="font-mono text-3xl font-bold">{me.data ? Number(me.data.credit_balance).toFixed(2) : "…"}</p><p className="mt-1 text-sm text-muted"><Link className="underline" to="/billing">Add credits</Link></p></Card>
        <Card title="Videos"><p className="font-mono text-3xl font-bold">{projects.isLoading ? "…" : list.length}</p><p className="mt-1 text-sm text-muted">{done} finished</p></Card>
        <Card title="Brand kit"><p className="text-sm">Your logo, colours and fonts appear in every video.</p><p className="mt-1 text-sm"><Link className="underline" to="/brand">Open brand kit</Link></p></Card>
      </div>
      <Card title="How it works">
        <ol className="list-decimal space-y-1 pl-5 text-sm">
          <li>Tell us about your business.</li>
          <li>Answer a short interview with our AI interviewer.</li>
          <li>Review your written story and pick two or three pictures.</li>
          <li>We make the video; download it or share a link.</li>
        </ol>
      </Card>
      <Card title="Recent videos">
        {projects.isLoading ? <p aria-busy="true">Loading…</p> : recent.length ? (
          <ul className="divide-y divide-line">
            {recent.map((p) => (
              <li key={p.id}>
                <Link to={`/projects/${p.id}`} className="flex flex-wrap items-center justify-between gap-2 py-3 hover:bg-paper">
                  <span className="font-medium">Video {p.id.slice(0, 6)} <span className="text-sm font-normal text-muted">· {new Date(p.created_at).toLocaleDateString()}</span></span>
                  <span className="rounded-full bg-paper px-3 py-1 text-sm">{stateLabel(p.state)}</span>
                </Link>
              </li>
            ))}
          </ul>
        ) : <p className="text-muted">No videos yet. <Link className="underline" to="/projects/new">Make your first one</Link>.</p>}
        {list.length > recent.length && <p className="mt-2 text-sm"><Link className="underline" to="/projects">See all videos</Link></p>}
      </Card>
    </>
  );
}
