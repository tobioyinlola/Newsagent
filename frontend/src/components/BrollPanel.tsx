import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api, unwrap } from "../api/client";
import { Button, Card, ErrorBox, Field, inputCls, Notice } from "./ui";

type Pick = { key: string; caption: string; seconds: number };

// Product footage for the video: the owner's own images and clips, and (if set up) AI-generated shots that are always labelled.
export function BrollPanel({ projectId }: { projectId: string }) {
  const qc = useQueryClient();
  const path = { params: { path: { project_id: projectId } } };
  const data = useQuery({ queryKey: ["broll", projectId], queryFn: () => unwrap(api.GET("/v1/projects/{project_id}/broll", path)) });
  const [picks, setPicks] = useState<Pick[]>([]);
  const [prompt, setPrompt] = useState("");
  const save = useMutation({
    mutationFn: (items?: Pick[]) => unwrap(api.PUT("/v1/projects/{project_id}/broll", { ...path, body: { items: items ?? picks } })),
    onSuccess: (d) => qc.setQueryData(["broll", projectId], d),
  });
  const autoDone = useRef(false);
  useEffect(() => {
    if (!data.data) return;
    const saved = data.data.items.map((i) => ({ key: i.key, caption: i.caption, seconds: i.seconds }));
    setPicks(saved);
    // First visit with uploads on file: use the owner's own product footage by default (up to 5) so there is nothing to set up.
    const mine = data.data.candidates.filter((c) => !c.synthetic).slice(0, 5);
    if (!autoDone.current && saved.length === 0 && mine.length > 0) {
      autoDone.current = true;
      const auto = mine.map((c) => ({ key: c.key, caption: "", seconds: c.kind === "image" ? 4 : 5 }));
      setPicks(auto);
      save.mutate(auto);
    }
  }, [data.data]);
  const gen = useMutation({
    mutationFn: () => unwrap(api.POST("/v1/projects/{project_id}/broll/generate", { ...path, body: { prompt, seconds: 5 } })),
    onSuccess: (d) => { qc.setQueryData(["broll", projectId], d); setPrompt(""); },
  });
  if (!data.data) return null;
  const { candidates, ai_available, note } = data.data;
  const chosen = (k: string) => picks.find((p) => p.key === k);
  const toggle = (k: string, kind: string) => setPicks(chosen(k) ? picks.filter((p) => p.key !== k) : [...picks, { key: k, caption: "", seconds: kind === "image" ? 4 : 5 }]);
  const patch = (k: string, v: Partial<Pick>) => setPicks(picks.map((p) => (p.key === k ? { ...p, ...v } : p)));
  return (
    <Card title="Product footage (optional)">
      <div className="space-y-3">
        <p className="text-sm text-muted">We use your uploaded product images and clips automatically (up to 5) right after the presenter introduces your startup. Untick any you don't want. They play silent, with an optional caption.</p>
        {candidates.length === 0 && <Notice>You haven't uploaded product images or videos yet. Add them on the <Link className="underline" to="/brand">Brand kit</Link> page.</Notice>}
        <ul className="grid gap-3 sm:grid-cols-2">
          {candidates.map((c) => {
            const p = chosen(c.key);
            return (
              <li key={c.key} className="space-y-2 rounded-sm border-2 border-ink p-3">
                {c.kind === "image" ? <img src={c.url ?? ""} alt="Product" className="h-28 w-full rounded object-cover" /> : <video src={c.url ?? ""} muted controls preload="metadata" className="h-28 w-full rounded bg-ink object-cover" aria-label="Product video" />}
                <label className="flex items-center gap-2 text-sm font-medium">
                  <input type="checkbox" checked={!!p} onChange={() => toggle(c.key, c.kind)} /> Show this {c.synthetic ? "AI-generated shot" : c.kind}
                </label>
                {c.synthetic && <p className="text-xs text-muted">Shown with an "AI-generated visual" label.</p>}
                {p && (
                  <div className="space-y-2">
                    <Field label="Caption (optional)">{(id) => <input id={id} maxLength={80} className={inputCls} value={p.caption} onChange={(e) => patch(c.key, { caption: e.target.value })} />}</Field>
                    <Field label="Seconds on screen">{(id) => <input id={id} type="number" min={c.kind === "image" ? 3 : 2} max={8} step={0.5} className={inputCls} value={p.seconds} onChange={(e) => patch(c.key, { seconds: Number(e.target.value) })} />}</Field>
                  </div>
                )}
              </li>
            );
          })}
        </ul>
        <div className="flex flex-wrap gap-2"><Button onClick={() => save.mutate(undefined)} disabled={save.isPending}>Save product footage</Button></div>
        {save.isSuccess && <Notice tone="ok">Saved. {picks.length ? `${picks.length} shot${picks.length === 1 ? "" : "s"} will be used.` : "No product footage will be used."}</Notice>}
        <div className="space-y-2 border-t-2 border-line pt-3">
          <p className="text-sm font-medium">AI-generated shot</p>
          {ai_available ? (
            <>
              <Field label="Describe the shot" hint="It is always labelled “AI-generated visual” and is never presented as real footage of your product.">{(id) => <input id={id} className={inputCls} maxLength={300} value={prompt} onChange={(e) => setPrompt(e.target.value)} />}</Field>
              <Button variant="secondary" onClick={() => gen.mutate()} disabled={gen.isPending || prompt.trim().length < 10}>{gen.isPending ? "Making the shot…" : "Make a shot"}</Button>
            </>
          ) : <p className="text-sm text-muted">{note}</p>}
        </div>
        <ErrorBox error={save.error ?? gen.error} />
      </div>
    </Card>
  );
}
