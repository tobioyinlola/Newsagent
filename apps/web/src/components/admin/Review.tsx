import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, unwrap } from "../../api/client";
import { Button, Card, ErrorBox, inputCls } from "../ui";

export function Review() {
  const qc = useQueryClient();
  const [status, setStatus] = useState("pending");
  const [notes, setNotes] = useState<Record<string, string>>({});
  const list = useQuery({ queryKey: ["admin-moderation", status], queryFn: () => unwrap(api.GET("/v1/admin/moderation", { params: { query: { status } } })), refetchInterval: 15000 });
  const decide = useMutation({
    mutationFn: ({ id, decision }: { id: string; decision: "approve" | "reject" }) => unwrap(api.POST("/v1/admin/moderation/{case_id}/decision", { params: { path: { case_id: id } }, body: { decision, note: notes[id] ?? "" } })),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["admin-moderation"] }); qc.invalidateQueries({ queryKey: ["admin-queue"] }); },
  });
  return (
    <Card title="Content review queue" actions={
      <label className="flex items-center gap-2 text-sm">Show
        <select aria-label="Status filter" className={inputCls + " w-auto"} value={status} onChange={(e) => setStatus(e.target.value)}>
          <option value="pending">waiting</option><option value="blocked">blocked</option><option value="approved">approved</option><option value="rejected">rejected</option><option value="all">all</option></select></label>}>
      <ErrorBox error={list.error ?? decide.error} />
      {list.data?.length === 0 && <p className="text-slate-700">{status === "pending" ? "Nothing waiting." : `Nothing ${status === "all" ? "yet" : status}.`}</p>}
      <ul className="space-y-4">
        {list.data?.map((c) => (
          <li key={c.id} className="space-y-2 rounded-md border border-slate-200 p-3">
            <div className="flex flex-wrap items-center gap-2 text-sm">
              <span className="rounded bg-slate-100 px-2 py-0.5 font-medium">{c.stage}</span>
              <span>{c.workspace_name ?? c.workspace_id}</span>
              <span className="text-slate-500">{new Date(c.created_at).toLocaleString()}</span>
              {c.reasons.map((r) => <span key={r} className="rounded bg-amber-100 px-2 py-0.5 text-amber-900">{r.replace("_", " ")}</span>)}
              <span className="ml-auto font-medium">{c.status}</span>
            </div>
            <pre className="max-h-48 overflow-auto whitespace-pre-wrap rounded bg-slate-50 p-2 text-sm" aria-label="Content under review">{c.excerpt}</pre>
            {c.status === "pending" && (
              <div className="flex flex-wrap gap-2">
                <input aria-label="Note to the owner" placeholder="Note to the owner (optional)" className={inputCls + " flex-1"} value={notes[c.id] ?? ""} onChange={(e) => setNotes({ ...notes, [c.id]: e.target.value })} />
                <Button disabled={decide.isPending} onClick={() => decide.mutate({ id: c.id, decision: "approve" })}>Approve</Button>
                <Button variant="danger" disabled={decide.isPending} onClick={() => decide.mutate({ id: c.id, decision: "reject" })}>Reject</Button>
              </div>
            )}
            {c.note && <p className="text-sm text-slate-700">Note: {c.note} {c.reviewed_by && `(${c.reviewed_by})`}</p>}
          </li>
        ))}
      </ul>
    </Card>
  );
}
