import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api, unwrap } from "../api/client";
import { articleText, PressRelease, type Story } from "./PressRelease";
import { Button, Card, ErrorBox, Notice } from "./ui";

export { articleText };
export const socialText = (s: Story) => `${s.social.hook}\n\n${s.social.post}\n\n${s.social.hashtags.join(" ")}`.trim();

function CopyButton({ text, label }: { text: string; label: string }) {
  const [done, setDone] = useState(false);
  return <Button variant="secondary" onClick={async () => { try { await navigator.clipboard.writeText(text); setDone(true); setTimeout(() => setDone(false), 1500); } catch { setDone(false); } }}>{done ? "Copied" : label}</Button>;
}

// The written announcement and the separate, scroll-stopping social post. `compact` is the preview before the video is made.
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
        <PressRelease story={s} pictures={pictures} showContact />
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
