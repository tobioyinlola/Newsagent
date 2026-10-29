import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api, unwrap } from "../api/client";
import { useMe } from "../components/Layout";
import { stateLabel } from "../lib/states";
import { videoTitle } from "../lib/title";
import { Card, ErrorBox } from "../components/ui";

export function Projects() {
  const me = useMe();
  const q = useQuery({ queryKey: ["projects"], queryFn: () => unwrap(api.GET("/v1/projects")) });
  return (
    <>
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Your videos</h1>
        <Link to="/projects/new" className="rounded-sm border-2 border-ink bg-brand-green px-4 py-2 text-sm font-bold text-ink hover:bg-ink hover:text-brand-green">New video</Link>
      </div>
      <ErrorBox error={q.error} />
      <Card>
        {q.isLoading ? <p aria-busy="true">Loading…</p> : q.data?.length ? (
          <ul className="divide-y divide-line">
            {q.data.map((p) => (
              <li key={p.id}>
                <Link to={`/projects/${p.id}`} className="flex flex-wrap items-center justify-between gap-2 py-3 hover:bg-paper">
                  <span className="font-medium">{videoTitle(me.data?.workspace_name, p.created_at)}</span>
                  <span className="rounded-full bg-paper px-3 py-1 text-sm">{stateLabel(p.state)}</span>
                </Link>
              </li>
            ))}
          </ul>
        ) : <p className="text-muted">No videos yet. Start with a short brief about your business.</p>}
      </Card>
    </>
  );
}
