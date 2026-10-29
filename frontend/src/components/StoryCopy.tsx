import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api, unwrap } from "../api/client";
import { Button, Card, ErrorBox, Notice } from "./ui";

type Contact = { name?: string; title?: string; company?: string; email?: string; website?: string };
type Story = { headline: string; dek: string; sections: { heading: string; paragraphs: string[] }[]; social: { hook: string; post: string; hashtags: string[] }; unverified?: string[]; dateline?: string; about?: string; company?: string; contact?: Contact };

// A press release: the dateline opens the first paragraph, then the body, the boilerplate and the media contact.
const body = (s: Story) => s.sections.flatMap((x) => x.paragraphs).map((p, i) => (i === 0 && s.dateline ? `${s.dateline} — ${p}` : p));
const contactLines = (c?: Contact) => [c?.name, c?.title, c?.company, c?.email, c?.website].filter((x): x is string => !!x && x.trim().length > 0);
export const articleText = (s: Story) =>
  ["FOR IMMEDIATE RELEASE", "", s.headline, s.dek, "", ...body(s).flatMap((p) => [p, ""]), ...(s.about ? [`About ${s.company ?? ""}`.trim(), s.about, ""] : []), ...(contactLines(s.contact).length ? ["Media Contact", ...contactLines(s.contact)] : [])].join("\n").trim();
export const socialText = (s: Story) => `${s.social.hook}\n\n${s.social.post}\n\n${s.social.hashtags.join(" ")}`.trim();

function CopyButton({ text, label }: { text: string; label: string }) {
  const [done, setDone] = useState(false);
  return <Button variant="secondary" onClick={async () => { try { await navigator.clipboard.writeText(text); setDone(true); setTimeout(() => setDone(false), 1500); } catch { setDone(false); } }}>{done ? "Copied" : label}</Button>;
}

// The written announcement and the separate, scroll-stopping social post. `compact` is the preview before the video is made.
// Pictures the owner uploaded for the story, spread through the text: with N pictures and P paragraphs, picture i follows
// paragraph floor((i + 1) * P / (N + 1)). The same list the upload box edits, so a new picture appears here at once.
export function placePictures<T>(paragraphs: string[], pictures: T[]): { after: number; picture: T }[] {
  const p = paragraphs.length;
  return pictures.map((picture, i) => ({ after: Math.max(1, Math.floor(((i + 1) * p) / (pictures.length + 1))), picture }));
}

export function StoryCopy({ projectId, compact = false }: { projectId: string; compact?: boolean }) {
  const broll = useQuery({ queryKey: ["broll", projectId], queryFn: () => unwrap(api.GET("/v1/projects/{project_id}/broll", { params: { path: { project_id: projectId } } })), retry: false });
  const pictures = (broll.data?.items ?? []).map((i) => ({ url: broll.data?.candidates.find((c) => c.key === i.key)?.url ?? "", caption: i.caption })).filter((x) => x.url);
  const q = useQuery({ queryKey: ["story", projectId], queryFn: () => unwrap(api.GET("/v1/projects/{project_id}/story", { params: { path: { project_id: projectId } } })) as Promise<Story>, retry: false });
  if (q.isError) return compact ? null : <ErrorBox error={q.error} />;
  const s = q.data;
  if (!s) return <p aria-busy="true">Loading…</p>;
  return (
    <>
      <Card title={compact ? "Your press release" : "Your announcement"}>
        <article className="space-y-3">
          <p className="text-xs font-bold uppercase tracking-widest text-muted">For immediate release</p>
          <h3 className="text-xl font-bold italic">{s.headline}</h3>
          <p className="font-semibold italic text-muted">{s.dek}</p>
          {(() => {
            const paras = body(s);
            const at = placePictures(paras, pictures);
            return paras.map((p, i) => (
              <div key={i} className="space-y-3">
                <p className="text-sm">{i === 0 && s.dateline ? <><strong className="italic">{s.dateline}</strong>{p.slice(s.dateline.length)}</> : p}</p>
                {at.filter((x) => x.after === i + 1).map((x) => (
                  <figure key={x.picture.url} className="my-1">
                    <img src={x.picture.url} alt={x.picture.caption || "Picture for the story"} className="max-h-80 w-full rounded-sm border border-line object-cover" loading="lazy" />
                    {x.picture.caption && <figcaption className="mt-1 text-xs italic text-muted">{x.picture.caption}</figcaption>}
                  </figure>
                ))}
              </div>
            ));
          })()}
          {s.about && (
            <section className="space-y-1">
              <h4 className="font-bold italic">About {s.company}</h4>
              <p className="text-sm">{s.about}</p>
            </section>
          )}
          {contactLines(s.contact).length > 0 && (
            <section className="space-y-0.5 text-sm">
              <h4 className="font-bold">Media Contact</h4>
              {contactLines(s.contact).map((l, i) => <p key={i}>{l}</p>)}
            </section>
          )}
        </article>
        {(s.unverified?.length ?? 0) > 0 && <div className="mt-3"><Notice tone="warn">We hedged these because we couldn't check them: {s.unverified!.join("; ")}.</Notice></div>}
        <div className="mt-3"><CopyButton text={articleText(s)} label="Copy the press release" /></div>
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
