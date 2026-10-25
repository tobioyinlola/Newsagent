import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { ApiError, api, unwrap } from "../api/client";
import { Button, Card, ErrorBox, Field, Notice, inputCls } from "./ui";

const LAYOUTS: Record<string, string> = { column: "Question and words in a column", pip: "Large, presenter in a small window", split: "Split screen", full: "Full screen" };

type Scene = {
  id: string; type: string; label: string; duration_s: number; narration?: string | null; caption?: string | null; layout?: string | null;
  question_index?: number | null; trim_start_s?: number | null; trim_end_s?: number | null; synthetic: boolean; editable: string[];
};

// Edit a finished interview video scene by scene. Nothing is made again until "Apply changes".
export function SceneEditor({ projectId, state }: { projectId: string; state: string }) {
  const qc = useQueryClient();
  const path = { params: { path: { project_id: projectId } } };
  const data = useQuery({ queryKey: ["scenes", projectId, state], queryFn: () => unwrap(api.GET("/v1/projects/{project_id}/scenes", path)), retry: false });
  const [claims, setClaims] = useState<{ sceneId: string; text: string; list: string[] } | null>(null);
  const [confirmed, setConfirmed] = useState<Set<string>>(new Set());
  const refresh = () => { void qc.invalidateQueries({ queryKey: ["scenes", projectId] }); };
  const patch = useMutation({
    mutationFn: (v: { id: string; body: Record<string, unknown> }) => unwrap(api.PATCH("/v1/projects/{project_id}/scenes/{scene_id}", { params: { path: { project_id: projectId, scene_id: v.id } }, body: { confirmed_claims: [], ...v.body } })),
    onSuccess: () => { setClaims(null); setConfirmed(new Set()); refresh(); },
    onError: (e, v) => {
      const d = e instanceof ApiError ? (e.detail as { error?: string; claims?: { text: string }[] } | undefined) : undefined;
      if (d?.error === "claims_unconfirmed" && typeof v.body.narration === "string") setClaims({ sceneId: v.id, text: v.body.narration, list: (d.claims ?? []).map((c) => c.text) });
    },
  });
  const apply = useMutation({
    mutationFn: () => unwrap(api.POST("/v1/projects/{project_id}/revise", path)),
    onSuccess: () => { refresh(); void qc.invalidateQueries({ queryKey: ["project", projectId] }); },
  });
  const [text, setText] = useState<Record<string, string>>({});
  if (!data.data) return null; // presenter-only videos have no scenes to edit
  const d = data.data;
  const save = (s: Scene, body: Record<string, unknown>) => patch.mutate({ id: s.id, body });
  return (
    <Card title="Edit your video">
      <div className="space-y-4">
        <Notice>Change a scene, then apply. Only what changed is made again: a presenter part is made again only if you changed its words, and your own recordings are never touched. Applying uses credits for anything made again, and the video is unavailable for a few minutes while it re-renders.</Notice>
        <ol className="space-y-3">
          {(d.scenes as Scene[]).map((s) => (
            <li key={s.id} className="space-y-2 rounded-sm border-2 border-ink p-3">
              <div className="flex flex-wrap items-baseline gap-2"><span className="font-bold">{s.label}</span><span className="text-xs text-muted">{s.duration_s.toFixed(1)} s</span>{s.synthetic && <span className="rounded bg-peach-tint px-2 py-0.5 text-xs">AI-generated visual</span>}</div>
              {s.editable.includes("narration") && (
                <div className="space-y-2">
                  <Field label="What the presenter says">{(id) => <textarea id={id} rows={3} className={inputCls} value={text[s.id] ?? s.narration ?? ""} onChange={(e) => setText({ ...text, [s.id]: e.target.value })} />}</Field>
                  <Button variant="secondary" disabled={patch.isPending || (text[s.id] ?? s.narration) === s.narration} onClick={() => save(s, { narration: text[s.id], confirmed_claims: claims?.sceneId === s.id ? [...confirmed] : [] })}>Save these words</Button>
                  {claims?.sceneId === s.id && (
                    <fieldset className="space-y-1 rounded border-2 border-brand-peach p-2">
                      <legend className="px-1 text-sm font-semibold">Confirm these claims are accurate</legend>
                      {claims.list.map((c) => <label key={c} className="flex items-start gap-2 text-sm"><input type="checkbox" checked={confirmed.has(c)} onChange={() => setConfirmed((x) => { const n = new Set(x); if (n.has(c)) n.delete(c); else n.add(c); return n; })} /> {c}</label>)}
                    </fieldset>
                  )}
                </div>
              )}
              {s.editable.includes("layout") && (
                <Field label="How this answer appears">{(id) => <select id={id} className={inputCls} value={s.layout ?? "column"} onChange={(e) => save(s, { layout: e.target.value })}>{Object.entries(LAYOUTS).map(([v, l]) => <option key={v} value={v}>{l}</option>)}</select>}</Field>
              )}
              {s.editable.includes("trim") && (
                <div className="flex flex-wrap gap-3">
                  <Field label="Cut from the start (seconds)">{(id) => <input id={id} type="number" min={0} step={0.5} className={inputCls} defaultValue={s.trim_start_s ?? 0} onBlur={(e) => Number(e.target.value) !== (s.trim_start_s ?? 0) && save(s, { trim_start_s: Number(e.target.value) })} />}</Field>
                  <Field label="Cut from the end (seconds)">{(id) => <input id={id} type="number" min={0} step={0.5} className={inputCls} defaultValue={s.trim_end_s ?? 0} onBlur={(e) => Number(e.target.value) !== (s.trim_end_s ?? 0) && save(s, { trim_end_s: Number(e.target.value) })} />}</Field>
                </div>
              )}
              {s.editable.includes("caption") && (
                <Field label="Caption">{(id) => <input id={id} maxLength={80} className={inputCls} defaultValue={s.caption ?? ""} onBlur={(e) => e.target.value !== (s.caption ?? "") && save(s, { caption: e.target.value })} />}</Field>
              )}
              {s.editable.includes("include") && <Button variant="secondary" disabled={patch.isPending} onClick={() => save(s, { include: false })}>Remove from the video</Button>}
            </li>
          ))}
        </ol>
        {d.excluded_answers.length > 0 && (
          <div className="space-y-2">
            <p className="text-sm font-medium">Answers left out</p>
            {d.excluded_answers.map((a) => (
              <div key={String(a.question_index)} className="flex flex-wrap items-center gap-2 text-sm"><span>{String(a.question)}</span><Button variant="secondary" onClick={() => patch.mutate({ id: `answer-${a.question_index}`, body: { include: true } })}>Put back</Button></div>
            ))}
          </div>
        )}
        <ErrorBox error={claims ? null : patch.error ?? apply.error} />
        {d.revision_pending && (
          <div className="flex flex-wrap items-center gap-3">
            <Button disabled={apply.isPending} onClick={() => { if (confirm("Apply your changes? Anything changed is made again and uses credits.")) apply.mutate(); }}>Apply changes</Button>
            <span className="text-sm text-muted">You have changes waiting.</span>
          </div>
        )}
      </div>
    </Card>
  );
}
