import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, unwrap, unwrapPage } from "../../api/client";
import { Pager } from "../../../components/Pager";
import { usePaged } from "../../../lib/usePaged";
import { useCan } from "../../lib/can";
import { Button, Card, ErrorBox, inputCls } from "../ui";

export function JobsTab() {
  const qc = useQueryClient();
  const can = useCan();
  const [status, setStatus] = useState("");
  const jobs = usePaged(["admin-jobs", status], (limit, offset) => unwrapPage(api.GET("/v1/admin/jobs", { params: { query: { ...(status ? { status } : {}), limit, offset } } }), undefined, offset), { size: 50, refetchInterval: 10000 });
  const retry = useMutation({
    mutationFn: (id: string) => unwrap(api.POST("/v1/admin/projects/{project_id}/retry", { params: { path: { project_id: id } } })),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["admin-jobs"] }),
  });
  return (
    <Card title="Jobs" actions={
      <label className="flex items-center gap-2 text-sm">Status
        <select aria-label="Job status filter" className={inputCls + " w-auto"} value={status} onChange={(e) => setStatus(e.target.value)}>
          {["", "running", "failed", "succeeded", "pending"].map((s) => <option key={s} value={s}>{s || "all"}</option>)}</select></label>}>
      <ErrorBox error={jobs.query.error ?? retry.error} />
      <div className="overflow-x-auto">
        <table className="w-full text-sm"><caption className="sr-only">Pipeline jobs</caption>
          <thead><tr className="text-left text-muted"><th className="py-1">When</th><th>Workspace</th><th>Step</th><th>Vendor</th><th>Status</th><th className="text-right">Tries</th><th className="text-right">Cost</th><th>Error</th><th /></tr></thead>
          <tbody>{jobs.items.map((j) => (
            <tr key={j.id} className="border-t border-line align-top">
              <td className="py-1 whitespace-nowrap">{new Date(j.created_at).toLocaleString()}</td><td>{j.workspace_name}</td><td>{j.stage}</td><td>{j.vendor ?? "-"}</td>
              <td><span className={j.status === "failed" ? "bg-red-tint px-1 font-bold text-ink" : j.stuck ? "bg-peach-tint px-1 font-bold text-ink" : ""}>{j.stuck ? "stuck" : j.status}</span></td>
              <td className="text-right">{j.attempts}</td><td className="text-right tabular-nums">{Number(j.cost).toFixed(4)}</td>
              <td className="max-w-xs truncate" title={j.error ?? ""}>{j.error ?? ""}</td>
              <td>{can("operations.manage") && (j.status === "failed" || j.stuck) && <Button variant="secondary" disabled={retry.isPending} onClick={() => retry.mutate(j.project_id)}>Retry video</Button>}</td>
            </tr>))}</tbody></table>
      </div>
      {jobs.total === 0 && !jobs.query.isLoading && <p className="text-muted">No jobs match.</p>}
      <Pager total={jobs.total} page={jobs.page} size={jobs.size} onPage={jobs.setPage} onSize={jobs.setSize} noun="jobs" busy={jobs.query.isFetching} />
    </Card>
  );
}
