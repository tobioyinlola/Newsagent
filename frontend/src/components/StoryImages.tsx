import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useRef, useState } from "react";
import { api, unwrap } from "../api/client";
import { Button, Card, ErrorBox, Notice } from "./ui";

const TYPES = ["image/png", "image/jpeg", "image/webp"];
export const MIN_PICTURES = 2;
export const MAX_PICTURES = 3;

// The 2 or 3 pictures shown in the video (and used with the story). Uploaded straight to this video: no brand kit needed.
export function StoryImages({ projectId }: { projectId: string }) {
  const qc = useQueryClient();
  const path = { params: { path: { project_id: projectId } } };
  const data = useQuery({ queryKey: ["broll", projectId], queryFn: () => unwrap(api.GET("/v1/projects/{project_id}/broll", path)) });
  const input = useRef<HTMLInputElement>(null);
  const [captions, setCaptions] = useState<Record<string, string>>({});
  const items = data.data?.items ?? [];
  const urlOf = (key: string) => data.data?.candidates.find((c) => c.key === key)?.url ?? "";
  const put = (next: { key: string; caption: string; seconds: number }[]) =>
    unwrap(api.PUT("/v1/projects/{project_id}/broll", { ...path, body: { items: next } })).then((d) => qc.setQueryData(["broll", projectId], d));

  const add = useMutation({
    mutationFn: async (files: File[]) => {
      let next = items.map((i) => ({ key: i.key, caption: captions[i.key] ?? i.caption, seconds: i.seconds }));
      for (const file of files.slice(0, MAX_PICTURES - items.length)) {
        if (!TYPES.includes(file.type)) throw new Error("Please choose PNG, JPEG or WebP pictures.");
        const slot = await unwrap(api.POST("/v1/brand-kit/uploads", { body: { kind: "product_image", content_type: file.type, size_bytes: file.size } }));
        const r = await fetch(slot.upload_url, { method: "PUT", body: file, headers: { "Content-Type": file.type } });
        if (!r.ok) throw new Error("The upload didn't go through. Please try again.");
        const asset = await unwrap(api.POST("/v1/brand-kit/uploads/confirm", { body: { key: slot.key } }));
        next = [...next, { key: asset.key, caption: "", seconds: 4 }];
      }
      await put(next);
    },
  });
  const remove = useMutation({ mutationFn: (key: string) => put(items.filter((i) => i.key !== key).map((i) => ({ key: i.key, caption: i.caption, seconds: i.seconds }))) });
  const saveCaptions = useMutation({ mutationFn: () => put(items.map((i) => ({ key: i.key, caption: (captions[i.key] ?? i.caption).slice(0, 80), seconds: i.seconds }))) });

  return (
    <Card title={`Add ${MIN_PICTURES} or ${MAX_PICTURES} pictures`}>
      <div className="space-y-3">
        <p className="text-sm text-muted">Pictures of your product, team or launch. They appear in your video and are used with your story. Use only pictures you own or have the right to publish.</p>
        <ul className="grid gap-3 sm:grid-cols-3">
          {items.map((i) => (
            <li key={i.key} className="space-y-2 rounded-sm border-2 border-ink p-2">
              <img src={urlOf(i.key)} alt={i.caption || "Your picture"} className="aspect-video w-full rounded object-cover" />
              <input aria-label="Caption (optional)" placeholder="Caption (optional)" maxLength={80} className="w-full rounded border border-ink px-2 py-1 text-sm" value={captions[i.key] ?? i.caption} onChange={(e) => setCaptions({ ...captions, [i.key]: e.target.value })} onBlur={() => saveCaptions.mutate()} />
              <Button variant="secondary" disabled={remove.isPending} onClick={() => remove.mutate(i.key)}>Remove</Button>
            </li>
          ))}
        </ul>
        {items.length < MAX_PICTURES && (
          <div>
            <input ref={input} type="file" accept={TYPES.join(",")} multiple className="sr-only" aria-label="Choose pictures" onChange={(e) => { const f = Array.from(e.target.files ?? []); e.target.value = ""; if (f.length) add.mutate(f); }} />
            <Button variant="secondary" disabled={add.isPending} onClick={() => input.current?.click()}>{add.isPending ? "Uploading…" : items.length ? "Add another picture" : "Choose pictures"}</Button>
          </div>
        )}
        {items.length < MIN_PICTURES && <Notice>Add at least {MIN_PICTURES} pictures to continue.</Notice>}
        <ErrorBox error={add.error ?? remove.error ?? saveCaptions.error} />
      </div>
    </Card>
  );
}
