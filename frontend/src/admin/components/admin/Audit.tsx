import { api, unwrapPage } from "../../api/client";
import { Pager } from "../../../components/Pager";
import { usePaged } from "../../../lib/usePaged";
import { Card, ErrorBox } from "../ui";

export function Audit() {
  const log = usePaged(["admin-audit"], (limit, offset) => unwrapPage(api.GET("/v1/admin/audit", { params: { query: { limit, offset } } }), undefined, offset), { size: 50 });
  return (
    <Card title="Audit log">
      <p className="mb-3 text-sm text-muted">Every operator action, newest first. It can't be edited or deleted from here.</p>
      <ErrorBox error={log.query.error} />
      <div className="overflow-x-auto"><table className="w-full text-sm"><caption className="sr-only">Audit log</caption>
        <thead><tr className="text-left text-muted"><th className="py-1">When</th><th>Who</th><th>Action</th><th>Target</th><th>Details</th></tr></thead>
        <tbody>{log.items.map((e) => (
          <tr key={e.id} className="border-t border-line align-top"><td className="py-1 whitespace-nowrap">{new Date(e.created_at).toLocaleString()}</td><td>{e.actor}</td><td>{e.action}</td><td>{e.target_type ? `${e.target_type} ${e.target_id?.slice(0, 8) ?? ""}` : ""}</td><td className="max-w-md truncate font-mono text-xs" title={JSON.stringify(e.detail)}>{JSON.stringify(e.detail)}</td></tr>))}</tbody></table></div>
      <Pager total={log.total} page={log.page} size={log.size} onPage={log.setPage} onSize={log.setSize} noun="entries" busy={log.query.isFetching} />
    </Card>
  );
}
