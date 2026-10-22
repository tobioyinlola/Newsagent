import { useQuery } from "@tanstack/react-query";
import { Link } from "react-router-dom";
import { api, unwrap } from "../api/client";
import { stateLabel } from "../lib/states";
import { Card, ErrorBox } from "../components/ui";

export function Projects() {
  const q = useQuery({ queryKey: ["projects"], queryFn: () => unwrap(api.GET("/v1/projects")) });
  return (
    <>
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Your videos</h1>
        <Link to="/projects/new" className="rounded-md bg-blue-700 px-4 py-2 text-sm font-semibold text-white hover:bg-blue-800">New video</Link>
      </div>
      <ErrorBox error={q.error} />
      <Card>
        {q.isLoading ? <p aria-busy="true">Loading…</p> : q.data?.length ? (
          <ul className="divide-y divide-slate-200">
            {q.data.map((p) => (
              <li key={p.id}>
                <Link to={`/projects/${p.id}`} className="flex flex-wrap items-center justify-between gap-2 py-3 hover:bg-slate-50">
                  <span className="font-medium">Video {p.id.slice(0, 6)} <span className="text-sm font-normal text-slate-600">· {new Date(p.created_at).toLocaleDateString()}</span></span>
                  <span className="rounded-full bg-slate-100 px-3 py-1 text-sm">{stateLabel(p.state)}</span>
                </Link>
              </li>
            ))}
          </ul>
        ) : <p className="text-slate-700">No videos yet. Start with a short brief about your startup.</p>}
      </Card>
    </>
  );
}
