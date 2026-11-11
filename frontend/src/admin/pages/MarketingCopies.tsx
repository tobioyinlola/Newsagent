import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { api, unwrap } from "../api/client";
import { Button, Card, ConfirmDialog, ErrorBox, inputCls, Notice } from "../components/ui";
import { ago } from "../lib/format";
import { useCan } from "../lib/can";

type Version = { version: number; subject: string; preheader: string; body: string; button_label: string; button_url: string; created_by: string; created_at: string };
type Copy = { id: string; name: string; category: string; current_version: number; updated_at: string; current: Version | null; versions?: Version[] };
type Options = { categories: { key: string; label: string }[]; tags: { key: string; label: string; needs_fallback: boolean; sample: string }[] };
type Draft = { name: string; category: string; subject: string; preheader: string; body: string; button_label: string; button_url: string };
type Rendered = { subject: string; preheader: string; html: string; text: string };

const BLANK: Draft = { name: "", category: "activation", subject: "", preheader: "", body: "", button_label: "", button_url: "" };
const fromVersion = (c: Copy, v: Version): Draft => ({ name: c.name, category: c.category, subject: v.subject, preheader: v.preheader, body: v.body, button_label: v.button_label, button_url: v.button_url });

function CopyEditor({ options, copy, onDone }: { options: Options; copy: Copy | null; onDone: () => void }) {
  const qc = useQueryClient();
  const can = useCan();
  const manage = can("marketing.manage");
  const full = useQuery({ queryKey: ["copy", copy?.id], enabled: !!copy, queryFn: () => unwrap(api.GET("/v1/admin/marketing/copies/{copy_id}", { params: { path: { copy_id: copy!.id } } })) as unknown as Promise<Copy> });
  const [draft, setDraft] = useState<Draft>(copy?.current ? fromVersion(copy, copy.current) : BLANK);
  const [shown, setShown] = useState<Rendered | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [tested, setTested] = useState<string | null>(null);
  const focus = useRef<"subject" | "preheader" | "body">("body");
  const refs = { subject: useRef<HTMLInputElement>(null), preheader: useRef<HTMLInputElement>(null), body: useRef<HTMLTextAreaElement>(null) };
  const set = (patch: Partial<Draft>) => { setTested(null); setDraft((d) => ({ ...d, ...patch })); };

  // The preview rebuilds shortly after typing stops, using sample values, exactly as the email will be laid out.
  useEffect(() => {
    if (!draft.subject.trim() || !draft.body.trim()) { setShown(null); setProblem(null); return; }
    const t = setTimeout(() => {
      unwrap(api.POST("/v1/admin/marketing/copies/preview", { body: { ...draft, name: draft.name || "x" } })).then((r) => { setShown(r as unknown as Rendered); setProblem(null); }).catch((e: Error) => { setShown(null); setProblem(e.message); });
    }, 500);
    return () => clearTimeout(t);
  }, [draft]);

  const insert = (tag: string) => {
    const el = refs[focus.current].current;
    const field = focus.current;
    const cur = draft[field];
    const at = el?.selectionStart ?? cur.length;
    const end = el?.selectionEnd ?? at;
    set({ [field]: cur.slice(0, at) + tag + cur.slice(end) } as Partial<Draft>);
    requestAnimationFrame(() => { el?.focus(); el?.setSelectionRange(at + tag.length, at + tag.length); });
  };

  const save = useMutation({
    mutationFn: () => copy ? unwrap(api.PUT("/v1/admin/marketing/copies/{copy_id}", { params: { path: { copy_id: copy.id } }, body: draft })) : unwrap(api.POST("/v1/admin/marketing/copies", { body: draft })),
    onSuccess: async () => { await qc.invalidateQueries({ queryKey: ["copies"] }); await qc.invalidateQueries({ queryKey: ["copy"] }); onDone(); },
  });
  const test = useMutation({
    mutationFn: () => unwrap(api.POST("/v1/admin/marketing/copies/test", { body: draft })),
    onSuccess: (r) => setTested((r as unknown as { sent_to: string }).sent_to),
  });
  const versions = full.data?.versions ?? [];
  const ready = draft.name.trim() && draft.subject.trim() && draft.body.trim();

  return (
    <Card title={copy ? `Edit copy (version ${copy.current_version})` : "New copy"} actions={<Button variant="secondary" onClick={onDone}>Close</Button>}>
      <div className="grid gap-6 lg:grid-cols-2">
        <div className="space-y-4">
          <div className="grid gap-3 sm:grid-cols-2">
            <label className="block text-sm font-semibold">Name<input className={inputCls} value={draft.name} maxLength={120} placeholder="Day 3: make your first video" onChange={(e) => set({ name: e.target.value })} /></label>
            <label className="block text-sm font-semibold">Kind<select className={inputCls} value={draft.category} onChange={(e) => set({ category: e.target.value })}>{options.categories.map((c) => <option key={c.key} value={c.key}>{c.label}</option>)}</select></label>
          </div>
          <label className="block text-sm font-semibold">Subject<input ref={refs.subject} className={inputCls} value={draft.subject} maxLength={200} onFocus={() => (focus.current = "subject")} onChange={(e) => set({ subject: e.target.value })} /></label>
          <label className="block text-sm font-semibold">Preview line <span className="font-normal text-muted">(the grey text beside the subject)</span><input ref={refs.preheader} className={inputCls} value={draft.preheader} maxLength={200} onFocus={() => (focus.current = "preheader")} onChange={(e) => set({ preheader: e.target.value })} /></label>
          <label className="block text-sm font-semibold">Message<textarea ref={refs.body} rows={9} className={inputCls} value={draft.body} onFocus={() => (focus.current = "body")} onChange={(e) => set({ body: e.target.value })} placeholder={"Hi {{first_name|there}},\n\nLeave a blank line between paragraphs."} /></label>
          <div>
            <p className="text-sm font-semibold">Add a personal detail</p>
            <div className="mt-1 flex flex-wrap gap-2">{options.tags.map((t) => { const tag = t.needs_fallback ? `{{${t.key}|there}}` : `{{${t.key}}}`; return <button key={t.key} type="button" className="rounded-lg border border-line px-2.5 py-1.5 text-xs font-semibold hover:border-ink hover:bg-paper" onClick={() => insert(tag)}>{t.label}</button>; })}</div>
            <p className="mt-1 text-xs text-muted">The word after the bar, as in {"{{first_name|there}}"}, is used when we don’t have that detail for someone. Change it if you like.</p>
          </div>
          <div className="grid gap-3 sm:grid-cols-2">
            <label className="block text-sm font-semibold">Button text (optional)<input className={inputCls} value={draft.button_label} maxLength={60} onChange={(e) => set({ button_label: e.target.value })} /></label>
            <label className="block text-sm font-semibold">Button link<input className={inputCls} value={draft.button_url} placeholder="/dashboard or https://…" onChange={(e) => set({ button_url: e.target.value })} /></label>
          </div>
          <ErrorBox error={save.error ?? test.error} />
          {tested && <Notice tone="ok">Test sent to {tested}. Check your inbox (and spam).</Notice>}
          {manage && <div className="flex flex-wrap gap-2">
            <Button disabled={!ready || save.isPending} onClick={() => save.mutate()}>{save.isPending ? "Saving…" : copy ? "Save as a new version" : "Save copy"}</Button>
            <Button variant="secondary" disabled={!ready || test.isPending} onClick={() => test.mutate()}>{test.isPending ? "Sending…" : "Send a test to me"}</Button>
          </div>}
          {versions.length > 1 && (
            <details className="text-sm"><summary className="cursor-pointer font-semibold">Earlier versions ({versions.length - 1})</summary>
              <ul className="mt-2 divide-y divide-line rounded-lg border border-line">{versions.map((v) => <li key={v.version} className="flex flex-wrap items-center justify-between gap-2 px-3 py-2"><span>Version {v.version} · {ago(v.created_at)} · {v.created_by}{v.version === copy?.current_version && " (current)"}</span>{v.version !== copy?.current_version && <Button type="button" variant="secondary" onClick={() => copy && setDraft(fromVersion(copy, v))}>Use these words</Button>}</li>)}</ul>
            </details>
          )}
        </div>
        <div className="space-y-2">
          <p className="text-sm font-semibold">Preview <span className="font-normal text-muted">(with example details)</span></p>
          {problem && <Notice tone="warn">{problem}</Notice>}
          {shown ? (
            <>
              <p className="rounded-lg border border-line bg-paper px-3 py-2 text-sm"><b>{shown.subject}</b>{shown.preheader && <span className="text-muted"> — {shown.preheader}</span>}</p>
              <iframe title="Email preview" sandbox="" srcDoc={shown.html} className="h-[34rem] w-full rounded-lg border border-line bg-white" />
            </>
          ) : !problem && <p className="text-sm text-muted">Write a subject and a message to see the email.</p>}
        </div>
      </div>
    </Card>
  );
}

export function CopiesTab() {
  const qc = useQueryClient();
  const manage = useCan()("marketing.manage");
  const [editing, setEditing] = useState<Copy | "new" | null>(null);
  const [removing, setRemoving] = useState<Copy | null>(null);
  const options = useQuery({ queryKey: ["copy-options"], queryFn: () => unwrap(api.GET("/v1/admin/marketing/copy-options")) as unknown as Promise<Options> });
  const list = useQuery({ queryKey: ["copies"], queryFn: () => unwrap(api.GET("/v1/admin/marketing/copies")).then((r) => (r as unknown as { items: Copy[] }).items) });
  const remove = useMutation({
    mutationFn: (id: string) => unwrap(api.DELETE("/v1/admin/marketing/copies/{copy_id}", { params: { path: { copy_id: id } } })),
    onSuccess: async () => { setRemoving(null); await qc.invalidateQueries({ queryKey: ["copies"] }); },
  });
  const label = (k: string) => options.data?.categories.find((c) => c.key === k)?.label ?? k;
  return (
    <>
      <ErrorBox error={options.error ?? list.error ?? remove.error} />
      {editing && options.data ? <CopyEditor key={editing === "new" ? "new" : editing.id} options={options.data} copy={editing === "new" ? null : editing} onDone={() => setEditing(null)} /> : (
        <Card title="Email copy" actions={manage && <Button onClick={() => setEditing("new")}>New copy</Button>}>
          {list.isLoading ? <p aria-busy="true">Loading…</p> : list.data && list.data.length === 0 ? <p className="text-sm text-muted">No copy yet. Write an email once here, then use it in campaigns and workflows.</p> : (
            <ul className="space-y-3">
              {list.data?.map((c) => (
                <li key={c.id} className="flex flex-wrap items-start justify-between gap-2 rounded-xl border border-line p-3 text-sm">
                  <div><p className="font-bold">{c.name} <span className="ml-1 rounded-sm bg-lime-tint px-1.5 py-0.5 text-xs font-semibold">{label(c.category)}</span></p><p className="text-muted">{c.current?.subject}</p><p className="text-xs text-muted">Version {c.current_version} · updated {ago(c.updated_at)}</p></div>
                  <div className="flex gap-2"><Button variant="secondary" onClick={() => setEditing(c)}>{manage ? "Open" : "View"}</Button>{manage && <Button variant="danger" onClick={() => setRemoving(c)}>Delete</Button>}</div>
                </li>
              ))}
            </ul>
          )}
        </Card>
      )}
      {removing && <ConfirmDialog title="Delete this copy?" confirmLabel="Delete" onConfirm={() => remove.mutate(removing.id)} onCancel={() => setRemoving(null)}>“{removing.name}” will be removed. Emails already sent are not affected.</ConfirmDialog>}
    </>
  );
}
