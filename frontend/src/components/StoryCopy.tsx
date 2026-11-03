import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, unwrap } from "../api/client";
import { articleText, paragraphsOf, PressRelease, type Story } from "./PressRelease";
import { Button, Card, ErrorBox, Field, inputCls, Notice } from "./ui";

export { articleText };
export const socialText = (s: Story) => `${s.social.hook}\n\n${s.social.post}\n\n${s.social.hashtags.join(" ")}`.trim();

function CopyButton({ text, label }: { text: string; label: string }) {
  const [done, setDone] = useState(false);
  return <Button variant="secondary" onClick={async () => { try { await navigator.clipboard.writeText(text); setDone(true); setTimeout(() => setDone(false), 1500); } catch { setDone(false); } }}>{done ? "Copied" : label}</Button>;
}

// The owner's own wording of the press release: the subject, the summary line and the body (a blank line between paragraphs).
function PressReleaseEditor({ projectId, story, onDone }: { projectId: string; story: Story; onDone: () => void }) {
  const qc = useQueryClient();
  const [headline, setHeadline] = useState(story.headline);
  const [dek, setDek] = useState(story.dek ?? "");
  const [body, setBody] = useState(paragraphsOf(story).join("\n\n"));
  const save = useMutation({
    mutationFn: () => unwrap(api.PUT("/v1/projects/{project_id}/story", { params: { path: { project_id: projectId } }, body: { headline: headline.trim(), dek: dek.trim(), paragraphs: body.split(/\n\s*\n/).map((x) => x.trim()).filter(Boolean) } })),
    onSuccess: async () => { await qc.invalidateQueries({ queryKey: ["story", projectId] }); onDone(); },
  });
  return (
    <form className="space-y-4" onSubmit={(e) => { e.preventDefault(); save.mutate(); }}>
      <Field label="Subject (headline)">{(id) => <input id={id} required maxLength={200} className={inputCls} value={headline} onChange={(e) => setHeadline(e.target.value)} />}</Field>
      <Field label="Summary line" hint="The short line under the headline.">{(id) => <textarea id={id} maxLength={500} rows={2} className={inputCls} value={dek} onChange={(e) => setDek(e.target.value)} />}</Field>
      <Field label="Press release" hint="Leave a blank line between paragraphs. The dateline (place and date) is added in front of the first paragraph.">{(id) => <textarea id={id} required rows={14} className={inputCls} value={body} onChange={(e) => setBody(e.target.value)} />}</Field>
      <Notice tone="info">If you go back to the interview, the story is written again and your changes here are replaced.</Notice>
      <ErrorBox error={save.error} />
      <div className="flex flex-wrap gap-3">
        <Button type="submit" disabled={save.isPending || !headline.trim() || !body.trim()}>{save.isPending ? "Saving…" : "Save the press release"}</Button>
        <Button type="button" variant="secondary" onClick={onDone} disabled={save.isPending}>Cancel</Button>
      </div>
    </form>
  );
}

// The written announcement and the separate, scroll-stopping social post. `compact` is the preview before the video is made.
export function StoryCopy({ projectId, compact = false }: { projectId: string; compact?: boolean }) {
  const broll = useQuery({ queryKey: ["broll", projectId], queryFn: () => unwrap(api.GET("/v1/projects/{project_id}/broll", { params: { path: { project_id: projectId } } })), retry: false });
  const pictures = (broll.data?.items ?? []).map((i) => ({ url: broll.data?.candidates.find((c) => c.key === i.key)?.url ?? "", caption: i.caption })).filter((x) => x.url);
  const [editing, setEditing] = useState(false);
  const q = useQuery({ queryKey: ["story", projectId], queryFn: () => unwrap(api.GET("/v1/projects/{project_id}/story", { params: { path: { project_id: projectId } } })) as Promise<Story>, retry: false });
  if (q.isError) return compact ? null : <ErrorBox error={q.error} />;
  const s = q.data;
  if (!s) return <p aria-busy="true">Loading…</p>;
  return (
    <>
      <Card title={compact ? "Your press release" : "Your announcement"}>
        {editing ? <PressReleaseEditor projectId={projectId} story={s} onDone={() => setEditing(false)} /> : <>
          <PressRelease story={s} pictures={pictures} showContact />
          {(s.unverified?.length ?? 0) > 0 && <div className="mt-3"><Notice tone="warn">We hedged these because we couldn't check them: {s.unverified!.join("; ")}.</Notice></div>}
          <div className="mt-3 flex flex-wrap gap-3">
            {compact && <Button variant="secondary" onClick={() => setEditing(true)}>Edit the press release</Button>}
            <CopyButton text={articleText(s)} label="Copy the press release" />
          </div>
        </>}
      </Card>
      <Card title="Social post">
        <div className="space-y-2">
          <p className="text-lg font-bold">{s.social.hook}</p>
          <p className="text-sm">{s.social.post}</p>
          <p className="text-sm text-muted">{s.social.hashtags.join(" ")}</p>
          <CopyButton text={socialText(s)} label="Copy the social post" />
        </div>
      </Card>
    </>
  );
}
