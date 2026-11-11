import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { Link } from "react-router-dom";
import { api, unwrap } from "../api/client";
import { Button, Card, ConfirmDialog, ErrorBox, inputCls, Notice } from "../components/ui";
import { Crumbs, EmptyState, MARKETING, PageIntro, Step, useToast } from "../components/marketingUi";
import { useUrlState } from "../lib/urlState";
import { ago } from "../lib/format";
import { useCan } from "../lib/can";

type Version = { version: number; subject: string; preheader: string; body: string; button_label: string; button_url: string; created_by: string; created_at: string };
type Copy = { id: string; name: string; category: string; current_version: number; updated_at: string; current: Version | null; versions?: Version[] };
type Options = { categories: { key: string; label: string }[]; tags: { key: string; label: string; needs_fallback: boolean; sample: string }[] };
type Draft = { name: string; category: string; subject: string; preheader: string; body: string; button_label: string; button_url: string };
type Rendered = { subject: string; preheader: string; html: string; text: string };

const BLANK: Draft = { name: "", category: "activation", subject: "", preheader: "", body: "", button_label: "", button_url: "" };
const fromVersion = (c: Copy, v: Version): Draft => ({ name: c.name, category: c.category, subject: v.subject, preheader: v.preheader, body: v.body, button_label: v.button_label, button_url: v.button_url });

// A running length with advice: long subjects get cut off in inboxes.
function Length({ id, value, good, what }: { id: string; value: string; good: number; what: string }) {
  const n = value.length;
  return <p id={id} className={`mt-1 text-xs ${n > good ? "font-semibold text-red-700" : "text-muted"}`}>{n} characters{n > good ? `. Over ${good} may be cut off in some inboxes.` : ` (${what})`}</p>;
}

function CopyEditor({ options, copy, onDone }: { options: Options; copy: Copy | null; onDone: () => void }) {
  const qc = useQueryClient();
  const toast = useToast();
  const manage = useCan()("marketing.manage");
  const full = useQuery({ queryKey: ["copy", copy?.id], enabled: !!copy, queryFn: () => unwrap(api.GET("/v1/admin/marketing/copies/{copy_id}", { params: { path: { copy_id: copy!.id } } })) as unknown as Promise<Copy> });
  const [draft, setDraft] = useState<Draft>(copy?.current ? fromVersion(copy, copy.current) : BLANK);
  const [shown, setShown] = useState<Rendered | null>(null);
  const [problem, setProblem] = useState<string | null>(null);
  const [tested, setTested] = useState<string | null>(null);
  const [phone, setPhone] = useState(false);
  const focus = useRef<"subject" | "preheader" | "body">("body");
  const refs = { subject: useRef<HTMLInputElement>(null), preheader: useRef<HTMLInputElement>(null), body: useRef<HTMLTextAreaElement>(null) };
  const set = (patch: Partial<Draft>) => { setTested(null); setDraft((d) => ({ ...d, ...patch })); };

  // The preview rebuilds shortly after typing stops, using example details, exactly as the email will be laid out.
  useEffect(() => {
    if (!draft.subject.trim() || !draft.body.trim()) { setShown(null); setProblem(null); return; }
    const t = setTimeout(() => {
      unwrap(api.POST("/v1/admin/marketing/copies/preview", { body: { ...draft, name: draft.name || "x" } })).then((r) => { setShown(r as unknown as Rendered); setProblem(null); }).catch((e: Error) => { setShown(null); setProblem(e.message); });
    }, 500);
    return () => clearTimeout(t);
  }, [draft]);

  const insert = (tag: string) => {
    const field = focus.current;
    const el = refs[field].current;
    const cur = draft[field];
    const at = el?.selectionStart ?? cur.length;
    const end = el?.selectionEnd ?? at;
    set({ [field]: cur.slice(0, at) + tag + cur.slice(end) } as Partial<Draft>);
    requestAnimationFrame(() => { el?.focus(); el?.setSelectionRange(at + tag.length, at + tag.length); });
  };

  const [brief, setBrief] = useState("");
  const [drafted, setDrafted] = useState(false);
  const write = useMutation({
    mutationFn: () => unwrap(api.POST("/v1/admin/marketing/copies/draft", { body: { brief, category: draft.category } })),
    onSuccess: (r) => { const d = r as unknown as { subject: string; preheader: string; body: string }; set({ subject: d.subject, preheader: d.preheader, body: d.body }); setDrafted(true); },
  });
  const save = useMutation({
    mutationFn: () => (copy ? unwrap(api.PUT("/v1/admin/marketing/copies/{copy_id}", { params: { path: { copy_id: copy.id } }, body: draft })) : unwrap(api.POST("/v1/admin/marketing/copies", { body: draft }))),
    onSuccess: async (r) => { await qc.invalidateQueries({ queryKey: ["copies"] }); await qc.invalidateQueries({ queryKey: ["copy"] }); toast(copy ? `Saved as version ${(r as unknown as Copy).current_version}.` : "Email saved. You can now use it in a campaign or workflow."); onDone(); },
  });
  const test = useMutation({
    mutationFn: () => unwrap(api.POST("/v1/admin/marketing/copies/test", { body: draft })),
    onSuccess: (r) => setTested((r as unknown as { sent_to: string }).sent_to),
  });
  const versions = full.data?.versions ?? [];
  const ready = draft.name.trim() && draft.subject.trim() && draft.body.trim();

  return (
    <div className="space-y-4">
      <Crumbs trail={[["Email copy", `${MARKETING}/copies`], [copy ? copy.name : "New email"]]} />
      <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_minmax(0,26rem)]">
        <Card>
          <div className="space-y-7">
            <Step n={1} title="About this email" hint="Only you see these. They help you find it later.">
              <div className="grid gap-3 sm:grid-cols-2">
                <label className="block text-sm font-semibold">Name<input className={inputCls} value={draft.name} maxLength={120} placeholder="e.g. Day 3: make your first video" onChange={(e) => set({ name: e.target.value })} /></label>
                <label className="block text-sm font-semibold">What kind of email is it?<select className={inputCls} value={draft.category} onChange={(e) => set({ category: e.target.value })}>{options.categories.map((c) => <option key={c.key} value={c.key}>{c.label}</option>)}</select></label>
              </div>
            </Step>
            <Step n={2} title="Write it" hint="What people will read. Not sure where to start? Let the AI write a first draft.">
              {manage && (
                <details className="rounded-xl border border-line bg-paper p-3 text-sm" open={drafted || undefined}>
                  <summary className="cursor-pointer font-semibold">Get a first draft from the AI</summary>
                  <div className="mt-3 space-y-2">
                    <label className="block font-semibold">What is the email for?<textarea rows={2} className={inputCls} value={brief} maxLength={1000} placeholder="e.g. Remind people who signed up last week to make their first video" onChange={(e) => { setBrief(e.target.value); setDrafted(false); }} /></label>
                    <div className="flex flex-wrap items-center gap-2">
                      <Button type="button" variant="secondary" disabled={brief.trim().length < 10 || write.isPending} onClick={() => write.mutate()}>{write.isPending ? "Writing…" : "Write a draft"}</Button>
                      <span className="text-xs text-muted">It replaces the subject, preview line and message below. Always read it and change it before using it.</span>
                    </div>
                    {drafted && <Notice tone="ok">Draft added below. Check the facts and the wording.</Notice>}
                    <ErrorBox error={write.error} />
                  </div>
                </details>
              )}
              <div><label className="block text-sm font-semibold">Subject<input ref={refs.subject} aria-describedby="subject-length" className={inputCls} value={draft.subject} maxLength={200} onFocus={() => (focus.current = "subject")} onChange={(e) => set({ subject: e.target.value })} /></label><Length id="subject-length" value={draft.subject} good={60} what="aim for 60 or fewer" /></div>
              <div><label className="block text-sm font-semibold">Preview line <span className="font-normal text-muted">(optional: the grey text next to the subject in an inbox)</span><input ref={refs.preheader} aria-describedby="preheader-length" className={inputCls} value={draft.preheader} maxLength={200} onFocus={() => (focus.current = "preheader")} onChange={(e) => set({ preheader: e.target.value })} /></label><Length id="preheader-length" value={draft.preheader} good={90} what="aim for 90 or fewer" /></div>
              <label className="block text-sm font-semibold">Message<textarea ref={refs.body} rows={9} className={inputCls} value={draft.body} onFocus={() => (focus.current = "body")} onChange={(e) => set({ body: e.target.value })} placeholder={"Hi {{first_name|there}},\n\nLeave a blank line between paragraphs."} /></label>
              <div>
                <p className="text-sm font-semibold">Make it personal</p>
                <p className="text-xs text-muted">Click to add a detail where your cursor is. Each person sees their own.</p>
                <div className="mt-2 flex flex-wrap gap-2">{options.tags.map((t) => { const tag = t.needs_fallback ? `{{${t.key}|there}}` : `{{${t.key}}}`; return <button key={t.key} type="button" title={`Shows like: ${t.sample}`} className="rounded-lg border border-line px-2.5 py-1.5 text-xs font-semibold hover:border-ink hover:bg-paper" onClick={() => insert(tag)}>+ {t.label}</button>; })}</div>
                <p className="mt-2 text-xs text-muted">The word after the bar, as in {"{{first_name|there}}"}, is what shows when we don’t know that detail for someone (“Hi there”). You can change it.</p>
              </div>
            </Step>
            <Step n={3} title="Add a button" hint="Optional. A button gets more people to act than a link in the text.">
              <div className="grid gap-3 sm:grid-cols-2">
                <label className="block text-sm font-semibold">Button text<input className={inputCls} value={draft.button_label} maxLength={60} placeholder="e.g. Make my video" onChange={(e) => set({ button_label: e.target.value })} /></label>
                <label className="block text-sm font-semibold">Where it goes<input className={inputCls} value={draft.button_url} placeholder="/ai-newsroom/new or https://…" onChange={(e) => set({ button_url: e.target.value })} /><span className="mt-1 block text-xs font-normal text-muted">Use / for a page on our site, like /billing. Other websites must start with https://.</span></label>
              </div>
            </Step>
            <ErrorBox error={save.error} />
            {manage && <div className="flex flex-wrap items-center gap-2">
              <Button disabled={!ready || save.isPending} onClick={() => save.mutate()}>{save.isPending ? "Saving…" : copy ? "Save as a new version" : "Save email"}</Button>
              <Button variant="secondary" onClick={onDone}>Cancel</Button>
              {copy && <span className="text-xs text-muted">Earlier versions are kept, and anything already scheduled keeps the words it was set up with.</span>}
            </div>}
            {versions.length > 1 && (
              <details className="text-sm"><summary className="cursor-pointer font-semibold underline underline-offset-2">Earlier versions ({versions.length - 1})</summary>
                <ul className="mt-2 divide-y divide-line rounded-lg border border-line">{versions.map((v) => <li key={v.version} className="flex flex-wrap items-center justify-between gap-2 px-3 py-2"><span>Version {v.version} · {ago(v.created_at)} · {v.created_by}{v.version === copy?.current_version && " (current)"}</span>{v.version !== copy?.current_version && <Button type="button" variant="secondary" onClick={() => copy && setDraft(fromVersion(copy, v))}>Use these words</Button>}</li>)}</ul>
              </details>
            )}
          </div>
        </Card>
        <aside aria-label="Email preview" className="space-y-3 lg:sticky lg:top-4">
          <Card>
            <div className="flex flex-wrap items-center justify-between gap-2">
              <div><h3 className="font-bold">What people will see</h3><p className="text-xs text-muted">With example details filled in.</p></div>
              <div role="group" aria-label="Preview size" className="flex overflow-hidden rounded-lg border border-line text-xs font-semibold">
                {([["Desktop", false], ["Phone", true]] as const).map(([label, isPhone]) => <button key={label} type="button" aria-pressed={phone === isPhone} onClick={() => setPhone(isPhone)} className={`px-3 py-1.5 ${phone === isPhone ? "bg-brand-green" : "bg-white hover:bg-paper"}`}>{label}</button>)}
              </div>
            </div>
            <div className="mt-3 space-y-2">
              {problem && <Notice tone="warn">{problem}</Notice>}
              {shown ? (
                <>
                  <p className="rounded-lg border border-line bg-paper px-3 py-2 text-sm"><b>{shown.subject}</b>{shown.preheader && <span className="text-muted"> — {shown.preheader}</span>}</p>
                  <div className={phone ? "mx-auto w-[375px] max-w-full" : "w-full"}><iframe title="Email preview" sandbox="" srcDoc={shown.html} className="h-[30rem] w-full rounded-lg border border-line bg-white" /></div>
                </>
              ) : !problem && <p className="text-sm text-muted">Write a subject and a message and the email appears here.</p>}
              {manage && (
                <div className="space-y-2 border-t border-line pt-3">
                  <Button variant="secondary" disabled={!ready || test.isPending} onClick={() => test.mutate()}>{test.isPending ? "Sending…" : "Send a test to me"}</Button>
                  <p className="text-xs text-muted">Emails it to your own address so you can check it in a real inbox. Nobody else gets it.</p>
                  {tested && <Notice tone="ok">Test sent to {tested}. Check your inbox (and spam).</Notice>}
                  <ErrorBox error={test.error} />
                </div>
              )}
            </div>
          </Card>
        </aside>
      </div>
    </div>
  );
}

export function CopiesTab() {
  const qc = useQueryClient();
  const toast = useToast();
  const manage = useCan()("marketing.manage");
  const url = useUrlState();
  const edit = url.get("edit");
  const [removing, setRemoving] = useState<Copy | null>(null);
  const options = useQuery({ queryKey: ["copy-options"], queryFn: () => unwrap(api.GET("/v1/admin/marketing/copy-options")) as unknown as Promise<Options> });
  const list = useQuery({ queryKey: ["copies"], queryFn: () => unwrap(api.GET("/v1/admin/marketing/copies")).then((r) => (r as unknown as { items: Copy[] }).items) });
  const remove = useMutation({
    mutationFn: (id: string) => unwrap(api.DELETE("/v1/admin/marketing/copies/{copy_id}", { params: { path: { copy_id: id } } })),
    onSuccess: async () => { setRemoving(null); await qc.invalidateQueries({ queryKey: ["copies"] }); toast("Email deleted."); },
  });
  const label = (k: string) => options.data?.categories.find((c) => c.key === k)?.label ?? k;
  const editing = edit && edit !== "new" ? list.data?.find((c) => c.id === edit) : null;
  const done = () => url.set({ edit: null });

  if (edit && options.data && (edit === "new" || editing)) return <CopyEditor key={edit} options={options.data} copy={editing ?? null} onDone={done} />;
  if (edit && edit !== "new" && list.isLoading) return <p aria-busy="true">Loading…</p>;

  return (
    <div className="space-y-5">
      <PageIntro
        title="Email copy"
        how={["Write the email once: a subject, a message and an optional button. Add details like the person’s name so each email feels personal.", "Check how it looks in the preview, and send a test to yourself.", "Use it in a campaign or a workflow. Every change is saved as a new version, so emails already scheduled keep the words they were set up with."]}
        actions={manage && <Button onClick={() => url.set({ edit: "new" })}>Write a new email</Button>}
      >The emails you write, kept here to use again. Write one, then choose who gets it and when.</PageIntro>
      <ErrorBox error={options.error ?? list.error ?? remove.error} />
      {list.isLoading ? <p aria-busy="true">Loading…</p> : list.data && list.data.length === 0 ? (
        <Card><EmptyState title="You haven’t written an email yet" actions={manage && <Button onClick={() => url.set({ edit: "new" })}>Write your first email</Button>}>It only takes a minute, and you can ask the AI for a first draft.</EmptyState></Card>
      ) : (
        <ul className="space-y-3">
          {list.data?.map((c) => (
            <li key={c.id} className="rounded-xl border border-line bg-white p-4 text-sm shadow-sm">
              <div className="flex flex-wrap items-start justify-between gap-3">
                <div className="min-w-0"><p className="text-base font-bold">{c.name} <span className="ml-1 rounded-sm bg-lime-tint px-1.5 py-0.5 align-middle text-xs font-semibold">{label(c.category)}</span></p><p>{c.current?.subject}</p>{c.current?.preheader && <p className="text-muted">{c.current.preheader}</p>}<p className="mt-1 text-xs text-muted">Version {c.current_version} · updated {ago(c.updated_at)}</p></div>
                <div className="flex flex-wrap gap-2">
                  <Button variant="secondary" onClick={() => url.set({ edit: c.id })}>{manage ? "Open and edit" : "View"}</Button>
                  {manage && <Link className="inline-flex items-center rounded-lg border border-ink bg-brand-green px-4 py-2.5 text-sm font-semibold" to={`${MARKETING}/campaigns?new=1&copy=${c.id}`}>Send it in a campaign</Link>}
                  {manage && <Button variant="danger" onClick={() => setRemoving(c)}>Delete</Button>}
                </div>
              </div>
            </li>
          ))}
        </ul>
      )}
      {removing && <ConfirmDialog title="Delete this email?" confirmLabel="Delete" onConfirm={() => remove.mutate(removing.id)} onCancel={() => setRemoving(null)}>“{removing.name}” will be removed from your list. Emails already sent are not affected, and campaigns or workflows already set up with it keep working.</ConfirmDialog>}
    </div>
  );
}
