import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect } from "react";
import { useParams } from "react-router-dom";
import { api, unwrap } from "../api/client";
import { Delivery } from "../components/Delivery";
import { BrollPanel } from "../components/BrollPanel";
import { ProgressPanel } from "../components/ProgressPanel";
import { SceneEditor } from "../components/SceneEditor";
import { StoryCopy } from "../components/StoryCopy";
import { StoryImages } from "../components/StoryImages";
import { ScriptEditor } from "../components/ScriptEditor";
import { Button, Card, ErrorBox, Notice } from "../components/ui";
import { streamProjectEvents } from "../lib/sse";
import { InterviewPanel, ReviewPanel } from "../components/Interview";
import { LiveInterviewPanel } from "../interview/LiveInterview";
import { useMe } from "../components/Layout";
import { stateLabel, stepIndex, stepsFor } from "../lib/states";
import { videoTitle } from "../lib/title";

export function ProjectDetail() {
  const { id = "" } = useParams();
  const qc = useQueryClient();
  const path = { params: { path: { project_id: id } } };
  const me = useMe();
  const project = useQuery({
    queryKey: ["project", id], queryFn: () => unwrap(api.GET("/v1/projects/{project_id}", path)),
    refetchOnMount: "always", refetchOnWindowFocus: "always",
    refetchInterval: query => ["script_approved", "interviewing", "awaiting_founder", "processing_founder", "rendering_anchor", "anchor_ready", "merging"].includes(query.state.data?.state ?? "") ? 5000 : false,
  });
  const state = project.data?.state;
  const script = useQuery({
    queryKey: ["script", id],
    queryFn: () => unwrap(api.GET("/v1/projects/{project_id}/script", path)),
    enabled: state === "script_ready",
  });
  const costs = useQuery({ queryKey: ["costs", id], queryFn: () => unwrap(api.GET("/v1/projects/{project_id}/costs", path)), enabled: !!state && state !== "draft" });
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
  const guided = p.flow === "guided";
  const steps = stepsFor(p.interview_enabled, p.interview_mode, p.flow);
  const cur = stepIndex(steps, p.state, p.failure_reason ? (p.interview_enabled ? "merging" : "rendering_anchor") : undefined);

  return (
    <>
      <div className="flex flex-wrap items-center justify-between gap-2">
        <h1 className="text-2xl font-bold">{videoTitle(me.data?.workspace_name, p.created_at)}</h1>
        <span className="rounded-full bg-paper px-3 py-1 text-sm" aria-live="polite">{stateLabel(p.state)}</span>
      </div>
      <Stepper labels={steps.map((s) => s.label)} current={p.state === "final_ready" ? steps.length - 1 : cur} done={p.state === "final_ready"} />

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
      {p.state === "script_ready" && guided && <BackToInterview projectId={id} />}
      {p.state === "script_ready" && guided && <StoryCopy projectId={id} compact />}
      {p.state === "script_ready" && guided && <StoryImages projectId={id} />}
      {p.state === "script_ready" && script.data && <ScriptEditor projectId={id} script={script.data} guided={guided} />}
      {!guided && p.interview_enabled && ["interviewing", "awaiting_founder", "processing_founder"].includes(p.state) && <BrollPanel projectId={id} />}
      {p.state === "interviewing" && <LiveInterviewPanel projectId={id} founderName={p.founder_name} founderTitle={p.founder_title} guided={guided} />}
      {["script_approved", "rendering_anchor", "anchor_ready"].includes(p.state) && (
        <Card title={guided || live ? "Creating your AI presenter" : p.interview_enabled ? "Preparing your interview" : "Making your video"}>
          <p aria-busy="true">{guided || live ? "This can take 10 to 15 minutes to finish, depending on your internet speed. You can continue your work, but do not close this window. Once the video is ready, we will send you an email. It will also be waiting on your dashboard and will show ‘Ready’." : "This usually takes a few minutes. You can leave this page; we'll email you when it is ready."}</p>
        </Card>
      )}
      {p.state === "awaiting_founder" && <InterviewPanel projectId={id} />}
      {p.state === "processing_founder" && <ReviewPanel projectId={id} keepRaw={p.keep_raw_takes} />}
      {p.state === "merging" && <Card title="Making your final video"><p aria-busy="true">We're putting the interview together. You'll get an email when it is ready.</p></Card>}
      {p.state === "final_ready" && <Delivery projectId={id} />}
      {p.state === "final_ready" && guided && <StoryCopy projectId={id} />}
      {p.state === "final_ready" && p.interview_enabled && <SceneEditor projectId={id} state={p.state} />}
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

// Where the video is in its journey: numbered steps joined by arrows ("1. Details » 2. AI interview » ..."), with a bar that fills
// as each step is completed. Finished steps carry a tick; the current one is highlighted.
function Stepper({ labels, current, done }: { labels: string[]; current: number; done: boolean }) {
  const finished = done ? labels.length : current;
  const pct = Math.round(((done ? labels.length : current + 0.5) / labels.length) * 100);
  return (
    <nav aria-label="Progress" className="space-y-2">
      <p className="text-sm font-bold text-ink">{done ? "All steps complete" : `Step ${current + 1} of ${labels.length}: ${labels[current]}`}</p>
      <div className="h-2 w-full overflow-hidden rounded-full bg-line" role="progressbar" aria-valuemin={0} aria-valuemax={100} aria-valuenow={pct} aria-label="Overall progress">
        <div className="h-full rounded-full bg-brand-green transition-all duration-500" style={{ width: `${pct}%` }} />
      </div>
      <ol className="flex flex-wrap items-center gap-x-1 gap-y-2">
        {labels.map((label, i) => {
          const state = i === current ? "current" : i < finished ? "done" : "todo";
          return (
            <li key={label} className="flex items-center gap-1" aria-current={state === "current" ? "step" : undefined}>
              <span className={`inline-flex items-center gap-1.5 rounded-full border-2 px-3 py-1 text-sm font-bold ${state === "done" ? "border-ink bg-lime-tint text-ink" : state === "current" ? "border-brand-purple bg-brand-purple text-white" : "border-line bg-white text-muted"}`}>
                <span aria-hidden="true">{state === "done" || (done && i === current) ? "✓" : `${i + 1}.`}</span>{label}
                {state === "done" && <span className="sr-only"> (done)</span>}
              </span>
              {i < labels.length - 1 && <span aria-hidden="true" className={`px-1 font-bold ${i < finished ? "text-ink" : "text-line"}`}>»</span>}
            </li>
          );
        })}
      </ol>
    </nav>
  );
}

// Story review (guided): step back to the interview to re-record or re-pick answers, then produce the story again.
function BackToInterview({ projectId }: { projectId: string }) {
  const qc = useQueryClient();
  const back = useMutation({
    mutationFn: () => unwrap(api.POST("/v1/projects/{project_id}/interview/reopen", { params: { path: { project_id: projectId } } })),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["project", projectId] }); qc.invalidateQueries({ queryKey: ["interview", projectId] }); qc.invalidateQueries({ queryKey: ["script", projectId] }); },
  });
  return (
    <div className="flex flex-wrap items-center gap-3">
      <Button variant="secondary" disabled={back.isPending} onClick={() => back.mutate()}>{back.isPending ? "Going back…" : "← Back to the interview"}</Button>
      <span className="text-sm text-muted">Change or re-record your answers, then produce the story again. Nothing has been charged yet.</span>
      <ErrorBox error={back.error} />
    </div>
  );
}

