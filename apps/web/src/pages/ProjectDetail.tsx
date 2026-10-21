import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";
import { useParams } from "react-router-dom";
import { api, unwrap } from "../api/client";
import { Delivery } from "../components/Delivery";
import { ScriptEditor } from "../components/ScriptEditor";
import { Button, Card, ErrorBox, Notice } from "../components/ui";
import { streamProjectEvents } from "../lib/sse";
import { STEPS, stateLabel, stepIndex } from "../lib/states";

export function ProjectDetail() {
  const { id = "" } = useParams();
  const qc = useQueryClient();
  const path = { params: { path: { project_id: id } } };
  const project = useQuery({ queryKey: ["project", id], queryFn: () => unwrap(api.GET("/v1/projects/{project_id}", path)) });
  const state = project.data?.state;
  const script = useQuery({
    queryKey: ["script", id],
    queryFn: () => unwrap(api.GET("/v1/projects/{project_id}/script", path)),
    enabled: state === "script_ready",
  });
  const costs = useQuery({ queryKey: ["costs", id], queryFn: () => unwrap(api.GET("/v1/projects/{project_id}/costs", path)), enabled: !!state && state !== "draft" });
  const retry = useMutation({ mutationFn: () => unwrap(api.POST("/v1/projects/{project_id}/retry", path)), onSuccess: () => qc.invalidateQueries({ queryKey: ["project", id] }) });

  // Live status: refetch whenever the server pushes a new state.
  useEffect(() => {
    if (!state || ["final_ready", "draft", "script_ready"].includes(state)) return;
    const ctl = new AbortController();
    streamProjectEvents(id, () => { qc.invalidateQueries({ queryKey: ["project", id] }); qc.invalidateQueries({ queryKey: ["costs", id] }); }, ctl.signal);
    return () => ctl.abort();
  }, [id, state, qc]);

  if (project.isLoading) return <p aria-busy="true">Loading…</p>;
  if (project.error || !project.data) return <ErrorBox error={project.error ?? new Error("Not found")} />;
  const p = project.data;
  const cur = stepIndex(p.state, p.failure_reason ? "rendering_anchor" : undefined);

  return (
    <>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-2xl font-bold">Video {p.id.slice(0, 6)}</h1>
        <span className="rounded-full bg-slate-100 px-3 py-1 text-sm" aria-live="polite">{stateLabel(p.state)}</span>
      </div>
      <ol className="flex flex-wrap gap-2" aria-label="Progress">
        {STEPS.map((s, i) => (
          <li key={s.key} aria-current={i === cur ? "step" : undefined} className={`rounded-full px-3 py-1 text-sm ${i < cur || p.state === "final_ready" ? "bg-green-100 text-green-900" : i === cur ? "bg-blue-700 text-white" : "bg-slate-100 text-slate-700"}`}>{s.label}</li>
        ))}
      </ol>

      {(p.state === "failed" || p.state === "limit_reached") && (
        <Card>
          <Notice tone="warn">
            {p.state === "limit_reached" ? "Your video is paused because a usage limit was reached. Ask your operator to raise it, then retry." : "We couldn't finish this step. You were not charged for failed attempts."}
            {p.failure_reason && <p className="mt-1">{p.failure_reason}</p>}
          </Notice>
          <div className="mt-3"><Button onClick={() => retry.mutate()} disabled={retry.isPending || (p.state === "failed" && !p.failure_retryable)}>Retry</Button></div>
          <ErrorBox error={retry.error} />
        </Card>
      )}
      {p.state === "script_ready" && script.data && <ScriptEditor projectId={id} script={script.data} />}
      {["script_approved", "rendering_anchor", "anchor_ready"].includes(p.state) && (
        <Card title="Making your video"><p aria-busy="true">This usually takes a few minutes. You can leave this page; we'll email you when it is ready.</p></Card>
      )}
      {p.state === "final_ready" && <Delivery projectId={id} />}

      {costs.data && costs.data.lines.length > 0 && (
        <Card title="Cost">
          <table className="w-full text-sm"><caption className="sr-only">Cost by step</caption>
            <thead><tr className="text-left text-slate-600"><th className="py-1">Step</th><th>Status</th><th className="text-right">Credits</th></tr></thead>
            <tbody>{costs.data.lines.map((l) => <tr key={l.stage} className="border-t border-slate-200"><td className="py-1">{l.stage.replace("_", " ")}</td><td>{l.status}</td><td className="text-right">{Number(l.cost).toFixed(4)}</td></tr>)}
              <tr className="border-t border-slate-300 font-semibold"><td className="py-1" colSpan={2}>Total</td><td className="text-right">{Number(costs.data.total).toFixed(4)}</td></tr></tbody></table>
        </Card>
      )}
    </>
  );
}
