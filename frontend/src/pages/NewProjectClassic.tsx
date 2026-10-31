import { useMutation, useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { useNavigate } from "react-router-dom";
import { api, unwrap } from "../api/client";
import { PresenterPicker } from "../components/PresenterPicker";
import { Button, Card, ErrorBox, Field, inputCls } from "../components/ui";

export function NewProjectClassic() {
  const [location, setLocation] = useState("");
  const nav = useNavigate();
  const [brief, setBrief] = useState("");
  const [founder, setFounder] = useState("");
  const [role, setRole] = useState("");
  const [site, setSite] = useState("");
  const [accent, setAccent] = useState("british");
  const [presenter, setPresenter] = useState("");
  const voices = useQuery({ queryKey: ["voices"], queryFn: () => unwrap(api.GET("/v1/voices")) });
  const m = useMutation({
    mutationFn: async () => {
      const p = await unwrap(api.POST("/v1/projects", { body: { founder_location: location.trim(), brief_text: brief, website_url: site || null, region: "NG", voice_accent: accent, founder_name: founder.trim(), founder_title: role.trim(), anchor_id: presenter || null, flow: "classic" } }));
      await unwrap(api.POST("/v1/projects/{project_id}/script/generate", { params: { path: { project_id: p.id } } }));
      return p;
    },
    onSuccess: (p) => nav(`/ai-newsroom/${p.id}`),
  });
  return (
    <Card title="New video">
      <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); m.mutate(); }}>
        <div className="grid gap-3 sm:grid-cols-2">
          <Field label="Your name" hint="Our AI interviewer greets you by name.">{(id) => <input id={id} required maxLength={200} className={inputCls} value={founder} onChange={(e) => setFounder(e.target.value)} />}</Field>
          <Field label="Your role" hint="Include your company name, for example CEO, Bybit.">{(id) => <input id={id} maxLength={200} className={inputCls} placeholder="CEO, Bybit" value={role} onChange={(e) => setRole(e.target.value)} />}</Field>
        </div>
        <Field label="Paste your announcement or news script" hint="What you are announcing, who it is for, and any facts you want featured. We read it, work out the story, and write the presenter's script and your interview questions from it. At least 20 characters.">
          {(id) => <textarea id={id} required minLength={20} maxLength={8000} rows={9} className={inputCls} value={brief} onChange={(e) => setBrief(e.target.value)} />}
        </Field>
        <Field label="Website (optional)">{(id) => <input id={id} type="url" className={inputCls} value={site} onChange={(e) => setSite(e.target.value)} placeholder="https://" />}</Field>
        <PresenterPicker value={presenter} onChange={setPresenter} />
        {(voices.data ?? []).length > 0 && <Field label="Anchor voice accent">
          {(id) => (
            <select id={id} className={inputCls} value={accent} onChange={(e) => setAccent(e.target.value)}>
              {(voices.data ?? []).map((v) => <option key={v.id} value={v.accent}>{v.accent.replace("_", " ")}</option>)}
              {!voices.data && <option value="british">british</option>}
            </select>
          )}
        </Field>}
        <p className="text-sm text-muted">Writing the script is free. Nothing is rendered until you approve it.</p>
        <ErrorBox error={m.error} />
        <Field label="Founder location" hint="City and country shown during the founder’s answers.">{(id) => <input id={id} maxLength={200} placeholder="Lagos, Nigeria" className={inputCls} value={location} onChange={e => setLocation(e.target.value)} />}</Field>
        <Button type="submit" disabled={m.isPending}>{m.isPending ? "Reading your announcement…" : "Read it and write my script"}</Button>
      </form>
    </Card>
  );
}
