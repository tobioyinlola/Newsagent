import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, unwrap } from "../api/client";
import { Button, Card, ErrorBox, Field, inputCls } from "../components/ui";

export function NewProject() {
  const nav = useNavigate();
  const [brief, setBrief] = useState("");
  const [site, setSite] = useState("");
  const [accent, setAccent] = useState("british");
  const voices = useQuery({ queryKey: ["voices"], queryFn: () => unwrap(api.GET("/v1/voices")) });
  const m = useMutation({
    mutationFn: async () => {
      const p = await unwrap(api.POST("/v1/projects", { body: { brief_text: brief, website_url: site || null, region: "NG", voice_accent: accent } }));
      await unwrap(api.POST("/v1/projects/{project_id}/script/generate", { params: { path: { project_id: p.id } } }));
      return p;
    },
    onSuccess: (p) => nav(`/projects/${p.id}`),
  });
  return (
    <Card title="New video">
      <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); m.mutate(); }}>
        <Field label="Tell us about your startup" hint="What you do, who it is for, and one or two facts you want featured. At least 20 characters.">
          {(id) => <textarea id={id} required minLength={20} maxLength={8000} rows={7} className={inputCls} value={brief} onChange={(e) => setBrief(e.target.value)} />}
        </Field>
        <Field label="Website (optional)">{(id) => <input id={id} type="url" className={inputCls} value={site} onChange={(e) => setSite(e.target.value)} placeholder="https://" />}</Field>
        <Field label="Anchor voice accent">
          {(id) => (
            <select id={id} className={inputCls} value={accent} onChange={(e) => setAccent(e.target.value)}>
              {(voices.data ?? []).map((v) => <option key={v.id} value={v.accent}>{v.accent.replace("_", " ")}</option>)}
              {!voices.data && <option value="british">british</option>}
            </select>
          )}
        </Field>
        <p className="text-sm text-muted">Writing the script is free. Nothing is rendered until you approve it.</p>
        <ErrorBox error={m.error} />
        <Button type="submit" disabled={m.isPending}>{m.isPending ? "Writing your script…" : "Write my script"}</Button>
      </form>
    </Card>
  );
}
