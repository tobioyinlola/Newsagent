import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, unwrap } from "../api/client";
import { Button, Card, ErrorBox, Field, inputCls, Notice } from "../components/ui";

const ROLES = [
  { id: "intro", label: "Opening shot", help: "Plays first, before the AI presenter. 3 to 20 seconds." },
  { id: "cutaway", label: "Cutaway between answers", help: "Plays between the founder's answers. 2 to 10 seconds." },
  { id: "outro", label: "Sign-off", help: "Plays last, after the AI presenter's closing. 3 to 20 seconds." },
] as const;
type Role = (typeof ROLES)[number]["id"];
const TYPES: Record<string, string> = { mp4: "video/mp4", mov: "video/quicktime", webm: "video/webm" };

const typeOf = (f: File) => (f.type && Object.values(TYPES).includes(f.type) ? f.type : TYPES[f.name.split(".").pop()?.toLowerCase() ?? ""]);

function AddClip() {
  const qc = useQueryClient();
  const [title, setTitle] = useState("");
  const [role, setRole] = useState<Role>("intro");
  const [file, setFile] = useState<File | null>(null);
  const [rights, setRights] = useState(false);
  const [step, setStep] = useState("");
  const add = useMutation({
    mutationFn: async () => {
      if (!file) throw new Error("Choose a video file.");
      const content_type = typeOf(file);
      if (!content_type) throw new Error("Use an MP4, MOV or WebM video.");
      setStep("Starting the upload…");
      const slot = await unwrap(api.POST("/v1/admin/presenter-clips", { body: { title, role, content_type, size_bytes: file.size, rights_confirmed: rights } }));
      setStep("Uploading…");
      const put = await fetch(slot.upload_url, { method: "PUT", body: file, headers: { "content-type": content_type } });
      if (!put.ok) throw new Error("The upload failed. Please try again.");
      setStep("Checking the video…");
      return unwrap(api.POST("/v1/admin/presenter-clips/{clip_id}/confirm", { params: { path: { clip_id: slot.id } } }));
    },
    onSuccess: () => { setTitle(""); setFile(null); setRights(false); setStep(""); void qc.invalidateQueries({ queryKey: ["clips"] }); },
    onSettled: () => setStep(""),
  });
  return (
    <Card title="Add a clip">
      <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); add.mutate(); }}>
        <Field label="Title" hint="Only you see this, e.g. “Studio wide, evening bulletin”.">{(id) => <input id={id} required maxLength={200} className={inputCls} value={title} onChange={(e) => setTitle(e.target.value)} />}</Field>
        <Field label="How it is used" hint={ROLES.find((r) => r.id === role)?.help}>
          {(id) => <select id={id} className={inputCls} value={role} onChange={(e) => setRole(e.target.value as Role)}>{ROLES.map((r) => <option key={r.id} value={r.id}>{r.label}</option>)}</select>}
        </Field>
        <Field label="Video file" hint="MP4, MOV or WebM, landscape, at least 720p, up to 150 MB. Sound is kept.">
          {(id) => <input id={id} type="file" required accept="video/mp4,video/quicktime,video/webm,.mp4,.mov,.webm" className={inputCls} onChange={(e) => setFile(e.target.files?.[0] ?? null)} />}
        </Field>
        <label className="flex items-start gap-3 text-sm">
          <input type="checkbox" className="mt-1 h-4 w-4" checked={rights} onChange={(e) => setRights(e.target.checked)} />
          <span>I own this footage or it is licensed for this use, the presenter agreed to appear in videos made with this product, and it shows no real network’s logos or branding.</span>
        </label>
        <ErrorBox error={add.error} />
        {add.isSuccess && <Notice tone="ok">Added. It will be used in new videos from now on.</Notice>}
        <Button type="submit" disabled={add.isPending || !rights || !file}>{add.isPending ? step || "Working…" : "Upload clip"}</Button>
      </form>
    </Card>
  );
}

function Library() {
  const qc = useQueryClient();
  const list = useQuery({ queryKey: ["clips"], queryFn: () => unwrap(api.GET("/v1/admin/presenter-clips")) });
  const refresh = () => qc.invalidateQueries({ queryKey: ["clips"] });
  const toggle = useMutation({
    mutationFn: (v: { id: string; active: boolean }) => unwrap(api.PATCH("/v1/admin/presenter-clips/{clip_id}", { params: { path: { clip_id: v.id } }, body: { active: v.active } })),
    onSuccess: refresh,
  });
  const remove = useMutation({
    mutationFn: (id: string) => unwrap(api.DELETE("/v1/admin/presenter-clips/{clip_id}", { params: { path: { clip_id: id } } })),
    onSuccess: refresh,
  });
  const clips = list.data ?? [];
  return (
    <div className="space-y-4">
      <ErrorBox error={list.error ?? toggle.error ?? remove.error} />
      {ROLES.map((r) => {
        const rows = clips.filter((c) => c.role === r.id);
        return (
          <Card key={r.id} title={`${r.label} (${rows.filter((c) => c.active).length} in use)`}>
            {rows.length === 0 ? (
              <p className="text-sm text-muted">None yet. {r.id === "cutaway" ? "Without cutaways, answers follow each other directly." : "Videos skip this."}</p>
            ) : (
              <ul className="grid gap-4 sm:grid-cols-2 lg:grid-cols-3">
                {rows.map((c) => (
                  <li key={c.id} className="space-y-2 rounded-sm border-2 border-ink p-3">
                    {c.url && <video src={c.url} controls preload="metadata" className="aspect-video w-full bg-ink" aria-label={`Preview: ${c.title}`} />}
                    <p className="font-bold">{c.title}</p>
                    <p className="text-xs text-muted">{c.duration_s?.toFixed(1)} s · {c.width}×{c.height} · {c.has_audio ? "with sound" : "no sound"} · added by {c.rights_confirmed_by}</p>
                    <div className="flex flex-wrap gap-2">
                      <Button variant="secondary" onClick={() => toggle.mutate({ id: c.id, active: !c.active })} aria-pressed={c.active}>{c.active ? "In use: switch off" : "Off: switch on"}</Button>
                      <Button variant="danger" onClick={() => { if (confirm(`Delete “${c.title}”? Videos already made are not affected.`)) remove.mutate(c.id); }}>Delete</Button>
                    </div>
                  </li>
                ))}
              </ul>
            )}
          </Card>
        );
      })}
    </div>
  );
}

export function Presenter() {
  return (
    <>
      <h1 className="text-2xl font-bold">Presenter clips</h1>
      <Notice>Real presenter footage is mixed around the AI presenter in interview videos: an opening shot, cutaways between the founder’s answers and a sign-off. Each video picks from what is switched on here. The “AI-generated anchor” label stays on screen throughout.</Notice>
      <AddClip />
      <Library />
    </>
  );
}
