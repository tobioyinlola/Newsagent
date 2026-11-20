import { Link } from "react-router-dom";
import { api, unwrapPage } from "../api/client";
import { Pager } from "../components/Pager";
import { usePaged } from "../lib/usePaged";
import { useMe } from "../components/Layout";
import { stateLabel } from "../lib/states";
import { videoTitle } from "../lib/title";
import { Card, ErrorBox } from "../components/ui";

export function Projects() {
  const me = useMe();
  const q = usePaged(["projects"], (limit, offset) => unwrapPage(api.GET("/v1/projects", { params: { query: { limit, offset } } }), undefined, offset));
  return (
    <>
      <div className="flex items-center justify-between">
        <h1 className="text-2xl font-bold">Your videos</h1>
        <Link to="/ai-newsroom/new" className="rounded-sm border-2 border-ink bg-brand-green px-4 py-2 text-sm font-bold text-ink hover:bg-ink hover:text-brand-green">New video</Link>
      </div>
      <ErrorBox error={q.query.error} />
      <Card>
        {q.query.isLoading ? <p aria-busy="true">Loading…</p> : q.items.length ? (
          <ul className="divide-y divide-line">
            {q.items.map((p) => (
              <li key={p.id}>
                <Link to={`/ai-newsroom/${p.id}`} className="flex flex-wrap items-center justify-between gap-2 py-3 hover:bg-paper">
                  <span className="font-medium">{videoTitle(me.data?.workspace_name, p.created_at)}</span>
                  <span className="rounded-full bg-paper px-3 py-1 text-sm">{stateLabel(p.state)}</span>
                </Link>
              </li>
            ))}
          </ul>
        ) : <p className="text-muted">No videos yet. Start with a short brief about your business.</p>}
        <Pager total={q.total} page={q.page} size={q.size} onPage={q.setPage} onSize={q.setSize} noun="videos" busy={q.query.isFetching} />
      </Card>
    </>
  );
}
