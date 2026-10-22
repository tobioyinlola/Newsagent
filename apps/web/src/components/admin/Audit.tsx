import { useQuery } from "@tanstack/react-query";
import { api, unwrap } from "../../api/client";
import { Card, ErrorBox } from "../ui";

export function Audit() {
  const log = useQuery({ queryKey: ["admin-audit"], queryFn: () => unwrap(api.GET("/v1/admin/audit", { params: { query: { limit: 200 } } })) });
  return (
    <Card title="Audit log">
      <p className="mb-3 text-sm text-slate-700">Every operator action, newest first. It can't be edited or deleted from here.</p>
      <ErrorBox error={log.error} />
      <div className="overflow-x-auto"><table className="w-full text-sm"><caption className="sr-only">Audit log</caption>
        <thead><tr className="text-left text-slate-600"><th className="py-1">When</th><th>Who</th><th>Action</th><th>Target</th><th>Details</th></tr></thead>
        <tbody>{log.data?.map((e) => (
          <tr key={e.id} className="border-t border-slate-200 align-top"><td className="py-1 whitespace-nowrap">{new Date(e.created_at).toLocaleString()}</td><td>{e.actor}</td><td>{e.action}</td><td>{e.target_type ? `${e.target_type} ${e.target_id?.slice(0, 8) ?? ""}` : ""}</td><td className="max-w-md truncate font-mono text-xs" title={JSON.stringify(e.detail)}>{JSON.stringify(e.detail)}</td></tr>))}</tbody></table></div>
    </Card>
  );
}
