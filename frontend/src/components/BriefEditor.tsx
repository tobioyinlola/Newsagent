import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, unwrap } from "../api/client";
import { Button, Card, ErrorBox, Field, inputCls } from "./ui";

// Step back to the announcement: change it, and the script is written again from the new text.
export function BriefEditor({ projectId, founderName, founderTitle, onDone }: { projectId: string; founderName: string; founderTitle: string; onDone: () => void }) {
  const qc = useQueryClient();
  const path = { params: { path: { project_id: projectId } } };
  const facts = useQuery({ queryKey: ["understanding", projectId], queryFn: () => unwrap(api.GET("/v1/projects/{project_id}/understanding", path)) });
  const [brief, setBrief] = useState("");
  const [name, setName] = useState(founderName);
  const [role, setRole] = useState(founderTitle);
  const [site, setSite] = useState("");
  const save = useMutation({
    mutationFn: async () => {
      await unwrap(api.PATCH("/v1/projects/{project_id}/brief", { ...path, body: { brief_text: brief, website_url: site || null, founder_name: name.trim(), founder_title: role.trim() } }));
      await unwrap(api.POST("/v1/projects/{project_id}/script/generate", path));
    },
    onSuccess: () => {
      qc.invalidateQueries({ queryKey: ["script", projectId] });
      qc.invalidateQueries({ queryKey: ["project", projectId] });
      qc.invalidateQueries({ queryKey: ["understanding", projectId] });
      onDone();
    },
  });
  const loaded = facts.data;
  return (
    <Card title="Your announcement">
      <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); save.mutate(); }}>
        <p className="text-sm text-muted">Change what you told us and we'll write the script again from it. Your current script is replaced.</p>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Your name">{(id) => <input id={id} required maxLength={200} className={inputCls} value={name} onChange={(e) => setName(e.target.value)} />}</Field>
          <Field label="Your role">{(id) => <input id={id} maxLength={200} className={inputCls} value={role} onChange={(e) => setRole(e.target.value)} />}</Field>
        </div>
        <Field label="Your announcement" hint={loaded?.announcement ? `We read it as: ${loaded.company ? loaded.company + ", " : ""}${loaded.announcement}` : "At least 20 characters."}>
          {(id) => <textarea id={id} required minLength={20} maxLength={8000} rows={8} className={inputCls} placeholder="Paste or retype your announcement" value={brief} onChange={(e) => setBrief(e.target.value)} />}
        </Field>
        <Field label="Website (optional)">{(id) => <input id={id} type="url" className={inputCls} value={site} onChange={(e) => setSite(e.target.value)} placeholder="https://" />}</Field>
        <ErrorBox error={save.error} />
        <div className="flex flex-wrap gap-2">
          <Button type="submit" disabled={save.isPending}>{save.isPending ? "Writing your script…" : "Save and write my script again"}</Button>
          <Button type="button" variant="secondary" onClick={onDone}>Keep my current script</Button>
        </div>
      </form>
    </Card>
  );
}
