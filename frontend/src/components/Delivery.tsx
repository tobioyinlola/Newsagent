import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useState } from "react";
import { api, unwrap } from "../api/client";
import { Button, Card, DisclosureBadge, ErrorBox } from "./ui";

export function Delivery({ projectId }: { projectId: string }) {
  const qc = useQueryClient();
  const p = { params: { path: { project_id: projectId } } };
  const dl = useQuery({ queryKey: ["downloads", projectId], queryFn: () => unwrap(api.GET("/v1/projects/{project_id}/downloads", p)) });
  const caps = useQuery({ queryKey: ["captions", projectId], queryFn: () => unwrap(api.GET("/v1/projects/{project_id}/captions", p)) });
  const [shareUrl, setShareUrl] = useState<string | null>(null);
  const [copied, setCopied] = useState<string | null>(null);
  const share = useMutation({ mutationFn: () => unwrap(api.POST("/v1/projects/{project_id}/share", p)), onSuccess: (d) => { setShareUrl(d.url); qc.invalidateQueries({ queryKey: ["captions", projectId] }); } });
  const revoke = useMutation({ mutationFn: () => unwrap(api.DELETE("/v1/projects/{project_id}/share", p)), onSuccess: () => { setShareUrl(null); qc.invalidateQueries({ queryKey: ["captions", projectId] }); } });

  const copy = async (key: string, text: string) => {
    try { await navigator.clipboard.writeText(text); setCopied(key); setTimeout(() => setCopied(null), 1500); } catch { setCopied(null); }
  };
  const label = (t: string, f: string | null) => ({ render: f === "9x16" ? "Vertical video (9:16)" : "Widescreen video (16:9)", thumbnail: "Thumbnail", caption: "Captions (.srt)", preview: "Preview" } as Record<string, string>)[t] ?? t;
  const items = (dl.data?.items ?? []).filter((i) => i.type !== "preview");
  const videoUrl = dl.data?.items.find((i) => i.type === "render" && i.format === "16x9")?.url;
  const poster = dl.data?.items.find((i) => i.type === "thumbnail")?.url;

  return (
    <>
      <Card title="Your video">
        {videoUrl && <video controls className="w-full rounded-md bg-black" src={videoUrl} poster={poster} aria-label="Finished video" />}
        {dl.data && <div className="mt-3"><DisclosureBadge text={dl.data.disclosure} /></div>}
        <ErrorBox error={dl.error} />
      </Card>
      <Card title="Downloads">
        <ul className="divide-y divide-slate-200">
          {items.map((i) => (
            <li key={i.filename} className="flex items-center justify-between py-2">
              <span>{label(i.type, i.format)}</span>
              <a className="rounded-md border border-slate-300 px-3 py-1 text-sm font-medium hover:bg-slate-50" href={i.url} download={i.filename}>Download</a>
            </li>
          ))}
        </ul>
        <p className="mt-2 text-xs text-slate-600">Download links expire after 15 minutes. Reload this page for fresh ones.</p>
      </Card>
      <Card title="Share">
        <div className="space-y-3">
          {shareUrl ? (
            <div className="space-y-2">
              <p className="text-sm">Anyone with this private link can watch. It is shown once, so copy it now.</p>
              <div className="flex gap-2"><input readOnly aria-label="Share link" className="w-full rounded-md border border-slate-300 bg-slate-50 px-3 py-2 text-sm" value={shareUrl} onFocus={(e) => e.currentTarget.select()} />
                <Button variant="secondary" onClick={() => copy("share", shareUrl)}>{copied === "share" ? "Copied" : "Copy"}</Button></div>
            </div>
          ) : <p className="text-sm text-slate-700">{caps.data?.has_active_share ? "A share link is active. For security the link itself can't be shown again; create a new one or revoke access." : "Create a private link you can send to anyone."}</p>}
          <div className="flex gap-2">
            <Button onClick={() => share.mutate()} disabled={share.isPending}>Create share link</Button>
            <Button variant="danger" onClick={() => revoke.mutate()} disabled={revoke.isPending}>Revoke all links</Button>
          </div>
          <ErrorBox error={share.error ?? revoke.error} />
        </div>
      </Card>
      <Card title="Suggested captions">
        <p className="mb-3 text-sm text-slate-700">Copy-ready text for each platform. The disclosure is included and can't be removed.</p>
        <div className="space-y-4">
          {Object.entries(caps.data?.captions ?? {}).map(([platform, text]) => (
            <div key={platform} className="space-y-1">
              <div className="flex items-center justify-between"><h3 className="text-sm font-semibold capitalize">{platform === "x" ? "X" : platform}</h3>
                <Button variant="secondary" onClick={() => copy(platform, text)}>{copied === platform ? "Copied" : "Copy"}</Button></div>
              <pre className="whitespace-pre-wrap rounded-md bg-slate-50 p-3 text-sm">{text}</pre>
            </div>
          ))}
        </div>
      </Card>
    </>
  );
}
