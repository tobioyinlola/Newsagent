import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { useNavigate, useParams } from "react-router-dom";
import { api, unwrap } from "../api/client";
import { Delivery } from "../components/Delivery";
import { BrollPanel } from "../components/BrollPanel";
import { BriefEditor } from "../components/BriefEditor";
import { ProgressPanel } from "../components/ProgressPanel";
import { SceneEditor } from "../components/SceneEditor";
import { ScriptEditor } from "../components/ScriptEditor";
import { Button, Card, ErrorBox, Notice } from "../components/ui";
import { streamProjectEvents } from "../lib/sse";
import { InterviewPanel, ReviewPanel } from "../components/Interview";
import { LiveInterviewPanel } from "../interview/LiveInterview";
import { stateLabel, stepIndex, stepsFor } from "../lib/states";

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
  const nav = useNavigate();
  const [editingBrief, setEditingBrief] = useState(false);
  const del = useMutation({
    mutationFn: () => unwrap(api.DELETE("/v1/projects/{project_id}", path)),
    onSuccess: () => { qc.removeQueries({ queryKey: ["project", id] }); qc.invalidateQueries({ queryKey: ["projects"] }); nav("/projects"); },
  });
  const moderation = useQuery({
    queryKey: ["moderation", id],
    queryFn: () => unwrap(api.GET("/v1/projects/{project_id}/moderation", path)),
    enabled: !!state && ["script_ready", "processing_founder", "interviewing"].includes(state),
    refetchInterval: 15000,
  });
  const retry = useMutation({ mutationFn: () => unwrap(api.POST("/v1/projects/{project_id}/retry", path)), onSuccess: () => qc.invalidateQueries({ queryKey: ["project", id] }) });

  // Live status: refetch whenever the server pushes a new state.
  useEffect(() => {
    if (!state || ["final_ready", "draft", "script_ready"].includes(state)) return;  // nothing live to watch
    const ctl = new AbortController();
    streamProjectEvents(id, () => { qc.invalidateQueries({ queryKey: ["project", id] }); qc.invalidateQueries({ queryKey: ["costs", id] }); }, ctl.signal);
    return () => ctl.abort();
  }, [id, state, qc]);

  if (project.isLoading) return <p aria-busy="true">Loading…</p>;
  if (project.error || !project.data) return <ErrorBox error={project.error ?? new Error("Not found")} />;
  const p = project.data;
  const live = p.interview_enabled && p.interview_mode === "live";
  const steps = stepsFor(p.interview_enabled, p.interview_mode);
  const cur = stepIndex(steps, p.state, p.failure_reason ? (p.interview_enabled ? "merging" : "rendering_anchor") : undefined);

  return (
    <>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-2xl font-bold">{p.title || `Video ${p.id.slice(0, 6)}`}</h1>
        <span className="rounded-full bg-paper px-3 py-1 text-sm" aria-live="polite">{stateLabel(p.state)}</span>
      </div>
      <ol className="flex flex-wrap gap-2" aria-label="Progress">
        {steps.map((s, i) => (
          <li key={s.label} aria-current={i === cur ? "step" : undefined} className={`rounded-full px-3 py-1 text-sm ${i < cur || p.state === "final_ready" ? "bg-lime-tint text-ink" : i === cur ? "bg-brand-purple text-white" : "bg-paper text-muted"}`}>{s.label}</li>
        ))}
      </ol>

      {["script_approved", "rendering_anchor", "anchor_ready", "merging", "failed", "limit_reached", "cancelled"].includes(p.state) && <ProgressPanel projectId={id} state={p.state} />}
      {p.state === "cancelled" && (
        <Notice tone="info">You cancelled this video. Clips that were already made are kept; retry continues from where it stopped.</Notice>
      )}
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
      {moderation.data?.[0]?.status === "pending" && (
        <Notice tone="info">A member of our team is checking your {moderation.data[0].stage === "interview" ? "founder's answers" : "script"} before it is made. This is usually quick, and we'll email you as soon as it's done.</Notice>
      )}
      {moderation.data?.[0]?.status === "rejected" && (
        <Notice tone="warn">Our team couldn't approve this content.{moderation.data[0].note ? ` ${moderation.data[0].note}` : ""} Please edit it and try again.</Notice>
      )}
      {p.state === "script_ready" && editingBrief && <BriefEditor projectId={id} founderName={p.founder_name} founderTitle={p.founder_title} onDone={() => setEditingBrief(false)} />}
      {p.state === "script_ready" && script.data && !editingBrief && <ScriptEditor projectId={id} script={script.data} onBack={() => setEditingBrief(true)} />}
      {p.interview_enabled && ["interviewing", "awaiting_founder", "processing_founder"].includes(p.state) && <BrollPanel projectId={id} />}
      {p.state === "interviewing" && <LiveInterviewPanel projectId={id} founderName={p.founder_name} founderTitle={p.founder_title} />}
      {["script_approved", "rendering_anchor", "anchor_ready"].includes(p.state) && (
        <Card title={live ? "Creating your AI presenter" : p.interview_enabled ? "Preparing your interview" : "Making your video"}>
          <p aria-busy="true">{live ? "Your interview is saved. We're creating the AI presenter and will weave your answers into the video. " : ""}This usually takes a few minutes. You can leave this page; we'll email you when it is ready.</p>
        </Card>
      )}
      {p.state === "awaiting_founder" && <InterviewPanel projectId={id} />}
      {p.state === "processing_founder" && <ReviewPanel projectId={id} keepRaw={p.keep_raw_takes} />}
      {p.state === "merging" && <Card title="Making your final video"><p aria-busy="true">We're putting the interview together. You'll get an email when it is ready.</p></Card>}
      {p.state === "final_ready" && <Delivery projectId={id} />}
      {p.state === "final_ready" && p.interview_enabled && <SceneEditor projectId={id} state={p.state} />}

      {!["script_approved", "rendering_anchor", "anchor_ready", "merging"].includes(p.state) && (
        <div className="flex items-center gap-3">
          <Button variant="danger" disabled={del.isPending} onClick={() => { if (confirm("Delete this video and all its files? This can't be undone.")) del.mutate(); }}>Delete video</Button>
          <ErrorBox error={del.error} />
        </div>
      )}
      {costs.data && costs.data.lines.length > 0 && (
        <Card title="Cost">
          <table className="w-full text-sm"><caption className="sr-only">Cost by step</caption>
            <thead><tr className="text-left text-muted"><th className="py-1">Step</th><th>Status</th><th className="text-right">Credits</th></tr></thead>
            <tbody>{costs.data.lines.map((l) => <tr key={l.stage} className="border-t border-line"><td className="py-1">{l.stage.replace("_", " ")}</td><td>{l.status}</td><td className="text-right">{Number(l.cost).toFixed(4)}</td></tr>)}
              <tr className="border-t border-ink font-semibold"><td className="py-1" colSpan={2}>Total</td><td className="text-right">{Number(costs.data.total).toFixed(4)}</td></tr></tbody></table>
        </Card>
      )}
    </>
  );
}
