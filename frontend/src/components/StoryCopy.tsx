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
export function StoryCopy({ projectId, compact = false }: { projectId: string; compact?: boolean }) {
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
          {body(s).map((p, i) => <p key={i} className="text-sm">{i === 0 && s.dateline ? <><strong className="italic">{s.dateline}</strong>{p.slice(s.dateline.length)}</> : p}</p>)}
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
