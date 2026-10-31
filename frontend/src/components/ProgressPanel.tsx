import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";
import { api, unwrap } from "../api/client";
import { Button, Card, ErrorBox } from "./ui";

const MARK: Record<string, string> = { done: "✓", working: "…", waiting: "⏳", pending: "○", failed: "✕", paused: "⏸", cancelled: "■" };
const TEXT: Record<string, string> = { done: "Done", working: "Working", waiting: "Waiting for you", pending: "Not started", failed: "Needs attention", paused: "Paused", cancelled: "Cancelled" };

// Every piece of the video with its own status, so a partial failure shows exactly what is left (and what is kept).
export function ProgressPanel({ projectId, state }: { projectId: string; state: string }) {
  const qc = useQueryClient();
  const path = { params: { path: { project_id: projectId } } };
  const live = ["script_approved", "rendering_anchor", "anchor_ready", "merging"].includes(state);
  const progress = useQuery({
    queryKey: ["progress", projectId, state],
    queryFn: () => unwrap(api.GET("/v1/projects/{project_id}/progress", path)),
    refetchInterval: live ? 4000 : false,
  });
  const done = () => { void qc.invalidateQueries({ queryKey: ["project", projectId] }); void qc.invalidateQueries({ queryKey: ["progress", projectId] }); };
  const cancel = useMutation({ mutationFn: () => unwrap(api.POST("/v1/projects/{project_id}/cancel", path)), onSuccess: done });
  const retry = useMutation({ mutationFn: () => unwrap(api.POST("/v1/projects/{project_id}/retry", path)), onSuccess: done });
  useEffect(() => {
    if (progress.data?.state && progress.data.state !== state) void qc.invalidateQueries({ queryKey: ["project", projectId] });
  }, [progress.data?.state, projectId, state, qc]);
  const p = progress.data;
  if (!p) return null;
  return (
    <Card title={`Progress: ${p.percent}%`}>
      <div className="h-2 w-full rounded-full bg-paper" role="progressbar" aria-valuenow={p.percent} aria-valuemin={0} aria-valuemax={100} aria-label="Video progress">
        <div className="h-2 rounded-full bg-brand-green" style={{ width: `${p.percent}%` }} />
      </div>
      {p.queue_ahead > 0 && <p className="mt-2 text-sm text-muted">Lots of videos are being made right now. About {p.queue_ahead} {p.queue_ahead === 1 ? "is" : "are"} ahead of yours. It starts by itself, and you can leave this page.</p>}
      <ul className="mt-3 space-y-1 text-sm">
        {p.stages.map((s) => (
          <li key={s.key} className="flex flex-wrap items-baseline gap-2">
            <span aria-hidden className="w-5 text-center font-bold">{MARK[s.status] ?? "○"}</span>
            <span className={s.status === "done" ? "text-muted" : "font-medium"}>{s.label}</span>
            <span className="text-xs text-muted">{TEXT[s.status] ?? s.status}</span>
            {s.detail && s.status !== "done" && <span className="basis-full pl-7 text-xs text-muted">{s.detail}</span>}
          </li>
        ))}
      </ul>
      <div className="mt-3 flex flex-wrap gap-2">
        {p.cancellable && (
          <Button variant="secondary" disabled={cancel.isPending} onClick={() => { if (confirm("Stop making this video? Clips already made are kept and you can continue later. A clip the presenter service is already making may still be charged.")) cancel.mutate(); }}>Cancel</Button>
        )}
        {p.retryable && <Button onClick={() => retry.mutate()} disabled={retry.isPending}>Retry from where it stopped</Button>}
      </div>
      <ErrorBox error={cancel.error ?? retry.error} />
    </Card>
  );
}
