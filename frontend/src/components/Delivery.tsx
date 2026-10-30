import { useQuery } from "@tanstack/react-query";
import { useState } from "react";
import { api, unwrap } from "../api/client";
import { ShareLinks } from "./ShareLinks";
import { Button, Card, DisclosureBadge, ErrorBox } from "./ui";

export function Delivery({ projectId }: { projectId: string }) {
  const p = { params: { path: { project_id: projectId } } };
  const dl = useQuery({ queryKey: ["downloads", projectId], queryFn: () => unwrap(api.GET("/v1/projects/{project_id}/downloads", p)) });
  const caps = useQuery({ queryKey: ["captions", projectId], queryFn: () => unwrap(api.GET("/v1/projects/{project_id}/captions", p)) });
  const [copied, setCopied] = useState<string | null>(null);
  const pub = useQuery({ queryKey: ["publication", projectId], queryFn: () => unwrap(api.GET("/v1/projects/{project_id}/publication", p)) });
  const storyUrl = pub.data?.path ? `${window.location.origin}${pub.data.path}` : null;

  const copy = async (key: string, text: string) => {
    try { await navigator.clipboard.writeText(text); setCopied(key); setTimeout(() => setCopied(null), 1500); } catch { setCopied(null); }
  };
  const shape = (f: string | null) => (f === "9x16" ? "Vertical video (9:16)" : "Widescreen video (16:9)");
  const label = (t: string, f: string | null) => t === "render" ? `${shape(f)}: HD` : t === "render_light" ? `${shape(f)}: Light` : ({ thumbnail: "Thumbnail", caption: "Captions (.srt)", preview: "Preview" } as Record<string, string>)[t] ?? t;
  const note = (t: string) => t === "render" ? "The original file, at full quality. Larger." : t === "render_light" ? "The same video, compressed to a much smaller file. Easier to upload and share." : null;
  const order = (t: string) => ["render", "render_light", "thumbnail", "caption"].indexOf(t);
  const items = (dl.data?.items ?? []).filter((i) => i.type !== "preview").sort((a, b) => order(a.type) - order(b.type) || String(a.format).localeCompare(String(b.format)));
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
        <ul className="divide-y divide-line">
          {items.map((i) => (
            <li key={i.filename} className="flex items-center justify-between py-2">
              <span>{label(i.type, i.format)}{note(i.type) && <span className="block text-xs text-muted">{note(i.type)}</span>}</span>
              <a className="rounded-md border border-ink px-3 py-1 text-sm font-medium hover:bg-paper" href={i.url} download={i.filename}>Download</a>
            </li>
          ))}
        </ul>
        <p className="mt-2 text-xs text-muted">Download links expire after 15 minutes. Reload this page for fresh ones.</p>
      </Card>
      <Card title="Your story on Cover Founder">
        <div className="space-y-3">
          {pub.data?.published && storyUrl ? (
            <>
              <p className="text-sm">Your video and press release are published on Cover Founder Latest Stories. Share this link anywhere:</p>
              <div className="flex gap-2">
                <input readOnly aria-label="Link to your published story" className="w-full rounded-md border border-ink bg-paper px-3 py-2 text-sm" value={storyUrl} onFocus={(e) => e.currentTarget.select()} />
                <Button variant="secondary" onClick={() => copy("story", storyUrl)}>{copied === "story" ? "Copied" : "Copy"}</Button>
              </div>
              <ShareLinks url={storyUrl} title="My story on Cover Founder News" text="Our story on Cover Founder News" />
              <div className="flex flex-wrap gap-2">
                <a className="rounded-md border-2 border-ink bg-brand-green px-4 py-2 text-sm font-bold text-ink hover:bg-ink hover:text-brand-green" href={pub.data.path ?? "#"} target="_blank" rel="noreferrer">View your story</a>
              </div>
              <p className="text-xs text-muted">Anyone with the link, and anyone browsing Latest Stories, can see it. The contact details in your press release are never shown. To have it removed, contact us.</p>
            </>
          ) : pub.data?.slug ? (
            <>
              <p className="text-sm text-muted">Your story is not published right now. Contact us if you have questions.</p>
            </>
          ) : pub.isLoading ? <p aria-busy="true" className="text-sm text-muted">Checking…</p> : (
            <p className="text-sm text-muted">This video has no written story, so there is nothing to publish.</p>
          )}
          <ErrorBox error={pub.error} />
        </div>
      </Card>
      <Card title="Suggested captions">
        <p className="mb-3 text-sm text-muted">Copy-ready text for each platform. The disclosure is included and can't be removed.</p>
        <div className="space-y-4">
          {Object.entries(caps.data?.captions ?? {}).map(([platform, text]) => (
            <div key={platform} className="space-y-1">
              <div className="flex items-center justify-between"><h3 className="text-sm font-semibold capitalize">{platform === "x" ? "X" : platform}</h3>
                <Button variant="secondary" onClick={() => copy(platform, text)}>{copied === platform ? "Copied" : "Copy"}</Button></div>
              <pre className="whitespace-pre-wrap rounded-md bg-paper p-3 text-sm">{text}</pre>
            </div>
          ))}
        </div>
      </Card>
    </>
  );
}
