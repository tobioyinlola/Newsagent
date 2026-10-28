import { useMutation, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { api, type Schemas, unwrap } from "../api/client";
import { Button, Card, ErrorBox, Notice, inputCls } from "./ui";

type Script = Schemas["ScriptOut"];
type Seg = { kind: string; text: string };

export function ScriptEditor({ projectId, script, guided = false }: { projectId: string; script: Script; guided?: boolean }) {
  const qc = useQueryClient();
  const [segments, setSegments] = useState<Seg[]>(script.segments as Seg[]);
  const [ticker, setTicker] = useState(script.ticker_lines.join("\n"));
  const [questions, setQuestions] = useState<string[]>(script.interview_questions);
  const [mode, setMode] = useState<"live" | "invite" | "none">("live");
  const withInterview = guided || mode !== "none";
  const [confirmed, setConfirmed] = useState<Set<string>>(new Set(script.claim_flags.filter((c) => c.confirmed).map((c) => String(c.text))));
  useEffect(() => {
    setSegments(script.segments as Seg[]);
    setTicker(script.ticker_lines.join("\n"));
    setQuestions(script.interview_questions);
    setConfirmed(new Set(script.claim_flags.filter((c) => c.confirmed).map((c) => String(c.text))));
  }, [script.id]);

  const ORDER = ["intro", "body", "explanation", "analysis", "outro"];
  const EXTRA: Record<string, string> = {
    explanation: "Explanation: the presenter explains the business before your interview",
    analysis: "Analysis: the presenter reflects on your answers after the interview",
  };
  const addable = Object.keys(EXTRA).filter((k) => !segments.some((x) => x.kind === k));
  const addPart = (kind: string) => setSegments([...segments, { kind, text: "" }].sort((a, b) => ORDER.indexOf(a.kind) - ORDER.indexOf(b.kind)));
  const body = () => ({ segments: segments.filter((x) => x.text.trim() || !(x.kind in EXTRA)), ticker_lines: ticker.split("\n").map((s) => s.trim()).filter(Boolean), lower_thirds: script.lower_thirds, interview_questions: questions.map((q) => q.trim()).filter(Boolean), confirmed_claims: [...confirmed] });
  const refresh = () => { qc.invalidateQueries({ queryKey: ["script", projectId] }); qc.invalidateQueries({ queryKey: ["project", projectId] }); };
  const path = { params: { path: { project_id: projectId } } };

  const save = useMutation({ mutationFn: () => unwrap(api.PUT("/v1/projects/{project_id}/script", { ...path, body: body() })), onSuccess: refresh });
  const regenerate = useMutation({ mutationFn: () => unwrap(api.POST("/v1/projects/{project_id}/script/generate", path)), onSuccess: refresh });
  const approve = useMutation({
    mutationFn: async () => {
      const saved = await unwrap(api.PUT("/v1/projects/{project_id}/script", { ...path, body: body() }));
      const left = new Set(saved.claim_flags.filter((c) => !c.confirmed).map((c) => String(c.text))).size; // one per sentence, as listed
      if (left) throw new Error(`Please confirm the ${left === 1 ? "flagged claim" : `${left} flagged claims`} above (or press "Confirm all") before we make your video.`);
      return unwrap(api.POST("/v1/projects/{project_id}/script/approve", { ...path, body: { with_interview: withInterview, interview_mode: guided || mode !== "invite" ? "live" : "invite" } }));
    },
    onSettled: refresh, // also on failure: the save above may have produced claims to confirm
  });

  // Claims to show: those the server flagged for the saved text. Unsaved edits re-flag on save.
  // One row per sentence even if it matched several categories (e.g. a user count and a "first").
  const flagMap = new Map<string, string[]>();
  for (const c of script.claim_flags) flagMap.set(String(c.text), [...(flagMap.get(String(c.text)) ?? []), String(c.category)]);
  const flags = [...flagMap.keys()];
  const toggle = (t: string) => setConfirmed((s) => { const n = new Set(s); if (n.has(t)) n.delete(t); else n.add(t); return n; });

  return (
    <Card title={guided ? "What your presenter says" : `Script (version ${script.version})`}>
      <div className="space-y-4">
        <Notice>{guided ? "Check what the presenter says. It is short on purpose: your story and your own answers do the rest. Nothing is made until you approve." : "Review what the anchor will say. Nothing is rendered, and no credits are used, until you approve."}</Notice>
        {segments.map((s, i) => (
          <div key={i} className="space-y-1">
            <label htmlFor={`seg-${i}`} className="text-sm font-medium capitalize">{s.kind}</label>
            <textarea id={`seg-${i}`} rows={3} className={inputCls} value={s.text} onChange={(e) => setSegments(segments.map((x, j) => (j === i ? { ...x, text: e.target.value } : x)))} />
          </div>
        ))}
        {!guided && withInterview && addable.length > 0 && (
          <div className="flex flex-wrap items-center gap-2">
            <label htmlFor="add-part" className="text-sm font-medium">Add a presenter part</label>
            <select id="add-part" className={inputCls + " max-w-md"} value="" onChange={(e) => e.target.value && addPart(e.target.value)}>
              <option value="">Choose…</option>
              {addable.map((k) => <option key={k} value={k}>{EXTRA[k]}</option>)}
            </select>
          </div>
        )}
        <div className="space-y-1">
          <label htmlFor="ticker" className="text-sm font-medium">News ticker (one line each)</label>
          <textarea id="ticker" rows={3} className={inputCls} value={ticker} onChange={(e) => setTicker(e.target.value)} />
        </div>
        {!guided && <fieldset className="space-y-3 rounded-md border-2 border-ink p-3">
          <legend className="px-1 text-sm font-semibold">Interview</legend>
          {([
            ["live", "Interview me now with the AI interviewer (recommended)", "The AI interviewer greets you by name, asks these questions out loud, and records your answers on camera. About 4 minutes, never more than 5. Your camera must be on. Your answers appear in the video beside the AI presenter."],
            ["invite", "Send an interview link to a founder", "The presenter asks the questions in the video and your founder answers from their phone, any time in the next 14 days."],
            ["none", "No interview", "You get the AI presenter video only."],
          ] as const).map(([value, label, hint]) => (
            <label key={value} className="flex items-start gap-2 text-sm">
              <input type="radio" name="interview-mode" className="mt-1" checked={mode === value} onChange={() => setMode(value)} />
              <span><span className="font-bold">{label}</span><br /><span className="text-muted">{hint}</span></span>
            </label>
          ))}
          {withInterview && (
            <div className="space-y-2">
              <p className="text-sm font-medium">Interview questions</p>
              {questions.map((q, i) => (
                <div key={i} className="flex gap-2">
                  <input aria-label={`Interview question ${i + 1}`} maxLength={200} className={inputCls} value={q} onChange={(e) => setQuestions(questions.map((x, j) => (j === i ? e.target.value : x)))} />
                  <Button variant="secondary" aria-label={`Remove question ${i + 1}`} onClick={() => setQuestions(questions.filter((_, j) => j !== i))}>Remove</Button>
                </div>
              ))}
              {questions.length < 5 && <Button variant="secondary" onClick={() => setQuestions([...questions, ""])}>Add a question</Button>}
              <p className="text-xs text-muted">4 or 5 short, open questions fit the 5 minute interview. The most we allow is 5.</p>
            </div>
          )}
        </fieldset>}
        {flags.length > 0 && (
          <fieldset className="space-y-2 rounded-md border border-brand-peach bg-peach-tint p-3">
            <legend className="px-1 text-sm font-semibold text-ink">Confirm these claims are accurate</legend>
            <div className="flex flex-wrap items-center justify-between gap-2">
              <p className="text-sm text-ink">Revenue, user counts, funding, rankings and “first/best” statements must be confirmed by you before we render. <strong>{flags.filter((t) => confirmed.has(t)).length} of {flags.length} confirmed.</strong></p>
              <Button variant="secondary" onClick={() => setConfirmed(new Set(flags))} disabled={flags.every((t) => confirmed.has(t))}>Confirm all</Button>
            </div>
            {flags.map((t) => (
              <label key={t} className="flex items-start gap-2 text-sm">
                <input type="checkbox" className="mt-1" checked={confirmed.has(t)} onChange={() => toggle(t)} />
                <span>{t} <span className="text-xs text-ink">({[...new Set(flagMap.get(t))].join(", ")})</span></span>
              </label>
            ))}
          </fieldset>
        )}
        <ErrorBox error={save.error ?? regenerate.error ?? approve.error} />
        <div className="flex flex-wrap gap-2">
          <Button variant="secondary" onClick={() => save.mutate()} disabled={save.isPending}>Save changes</Button>
          {!guided && <Button variant="secondary" onClick={() => regenerate.mutate()} disabled={regenerate.isPending}>Regenerate</Button>}
          <Button onClick={() => approve.mutate()} disabled={approve.isPending}>{approve.isPending ? "Starting your video…" : guided ? "Make my video" : "Approve and make my video"}</Button>
        </div>
      </div>
    </Card>
  );
}
