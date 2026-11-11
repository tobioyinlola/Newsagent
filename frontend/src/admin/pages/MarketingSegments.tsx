import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { Link } from "react-router-dom";
import { api, unwrap } from "../api/client";
import { Button, Card, ConfirmDialog, ErrorBox, inputCls, Notice } from "../components/ui";
import { Crumbs, EmptyState, MARKETING, PageIntro, Step, useToast } from "../components/marketingUi";
import { useUrlState } from "../lib/urlState";
import { ago, num } from "../lib/format";
import { useCan } from "../lib/can";
import { blankCondition, cleanRules, type Condition, countRules, describe, describeRules, type FieldDef, isGroup, MAX_DEPTH, OP_LABEL, type Preview, type Rules, type Segment } from "../lib/segments";

const EMPTY: Rules = { match: "all", conditions: [] };
const rule = (field: string, op: string, value: unknown): Condition => ({ field, op, value });

// Ready-made starting points, so nobody has to begin from a blank page.
export const EXAMPLES: { name: string; note: string; rules: Rules }[] = [
  { name: "Joined this week", note: "People who signed up in the last 7 days.", rules: { match: "all", conditions: [rule("joined_days_ago", "lte", 7)] } },
  { name: "No video yet", note: "Signed up, but haven’t started a video.", rules: { match: "all", conditions: [rule("videos_started", "eq", 0)] } },
  { name: "Never bought credits", note: "Haven’t bought any credits so far.", rules: { match: "all", conditions: [rule("has_bought_credits", "is", false)] } },
  { name: "Gone quiet", note: "Haven’t signed in for 30 days or more.", rules: { match: "all", conditions: [rule("last_seen_days_ago", "gte", 30)] } },
  { name: "Running low on credits", note: "Two credits or fewer left.", rules: { match: "all", conditions: [rule("credits_left", "lte", 2)] } },
];

function ValueInput({ f, c, onChange }: { f: FieldDef; c: Condition; onChange: (v: unknown) => void }) {
  if (f.kind === "bool") return <select aria-label={f.label} className={inputCls} value={c.value ? "yes" : "no"} onChange={(e) => onChange(e.target.value === "yes")}><option value="yes">Yes</option><option value="no">No</option></select>;
  if (f.kind === "choice" && f.options.length) {
    const on = (c.value as string[]) ?? [];
    return <div className="flex flex-wrap gap-2">{f.options.map((o) => <label key={o.value} className="flex items-center gap-1.5 rounded-lg border border-line px-2.5 py-1.5 text-sm"><input type="checkbox" checked={on.includes(o.value)} onChange={(e) => onChange(e.target.checked ? [...on, o.value] : on.filter((v) => v !== o.value))} />{o.label}</label>)}</div>;
  }
  if (f.kind === "choice") return <input aria-label={f.label} className={inputCls} placeholder="Type one or more, separated by commas" value={((c.value as string[]) ?? []).join(", ")} onChange={(e) => onChange(e.target.value.split(",").map((s) => s.trim()).filter(Boolean))} />;
  if (f.kind === "dates" || c.op === "between") {
    const [a, b] = (c.value as string[]) ?? ["", ""];
    const t = f.kind === "dates" ? "date" : "number";
    return <div className="flex items-center gap-2"><input aria-label={`${f.label} from`} type={t} min={0} className={inputCls} value={a ?? ""} onChange={(e) => onChange([e.target.value, b])} /><span className="text-sm text-muted">and</span><input aria-label={`${f.label} to`} type={t} min={0} className={inputCls} value={b ?? ""} onChange={(e) => onChange([a, e.target.value])} /></div>;
  }
  return <input aria-label={f.label} type="number" min={0} className={inputCls} value={String(c.value ?? "")} onChange={(e) => onChange(e.target.value)} />;
}

// One group of rules: single rules and, below the top level, groups of their own ("A and (B or C)").
function RuleGroup({ fields, group, depth, onChange, onRemove }: { fields: FieldDef[]; group: Rules; depth: number; onChange: (g: Rules) => void; onRemove?: () => void }) {
  const cats = [...new Set(fields.map((f) => f.group))];
  const setAt = (i: number, next: Condition | Rules) => onChange({ ...group, conditions: group.conditions.map((c, j) => (j === i ? next : c)) });
  const removeAt = (i: number) => onChange({ ...group, conditions: group.conditions.filter((_, j) => j !== i) });
  return (
    <div className={depth > 1 ? "space-y-3 rounded-xl border-2 border-dashed border-line bg-paper p-3" : "space-y-3"}>
      <div className="flex flex-wrap items-center gap-2 text-sm font-semibold">
        {depth === 1 ? "Include people who match" : "Match"}
        <select aria-label={depth === 1 ? "Match all or any" : `Match all or any in group ${depth}`} className={`${inputCls} !w-auto`} value={group.match} onChange={(e) => onChange({ ...group, match: e.target.value as Rules["match"] })}><option value="all">all</option><option value="any">any</option></select>
        of these rules:
        {depth === 1 && <span className="basis-full text-xs font-normal text-muted"><b>all</b> means every rule must be true. <b>any</b> means at least one must be true.</span>}
        {onRemove && <Button type="button" variant="secondary" className="ml-auto" onClick={onRemove}>Remove group</Button>}
      </div>
      <ul className="space-y-3">
        {group.conditions.map((c, i) => {
          if (isGroup(c)) return <li key={i}><RuleGroup fields={fields} group={c} depth={depth + 1} onChange={(g) => setAt(i, g)} onRemove={() => removeAt(i)} /></li>;
          const f = fields.find((x) => x.key === c.field);
          if (!f) return null;
          return (
            <li key={i} className="space-y-2 rounded-xl border border-line bg-white p-3">
              <div className="flex flex-wrap gap-2">
                <select aria-label="Rule" className={`${inputCls} min-w-52 flex-1`} value={c.field} onChange={(e) => { const nf = fields.find((x) => x.key === e.target.value); if (nf) setAt(i, blankCondition(nf)); }}>
                  {cats.map((g) => <optgroup key={g} label={g}>{fields.filter((x) => x.group === g).map((x) => <option key={x.key} value={x.key}>{x.label}</option>)}</optgroup>)}
                </select>
                {f.ops.length > 1 && <select aria-label="Comparison" className={`${inputCls} !w-auto`} value={c.op} onChange={(e) => setAt(i, { ...c, op: e.target.value, value: e.target.value === "between" ? ["", ""] : Array.isArray(c.value) ? "" : c.value })}>{f.ops.map((o) => <option key={o} value={o}>{OP_LABEL[o]}</option>)}</select>}
                <Button type="button" variant="secondary" aria-label={`Remove rule: ${describe(c, fields)}`} onClick={() => removeAt(i)}>Remove</Button>
              </div>
              <ValueInput f={f} c={c} onChange={(v) => setAt(i, { ...c, value: v })} />
            </li>
          );
        })}
      </ul>
      <div className="flex flex-wrap gap-2">
        <Button type="button" variant="secondary" onClick={() => onChange({ ...group, conditions: [...group.conditions, blankCondition(fields[0])] })}>Add a rule</Button>
        {depth < MAX_DEPTH && <Button type="button" variant="secondary" onClick={() => onChange({ ...group, conditions: [...group.conditions, { match: "any", conditions: [blankCondition(fields[0])] }] })}>Add a group</Button>}
      </div>
    </div>
  );
}

function Who({ p }: { p: Preview }) {
  return (
    <div className="space-y-2 text-sm" aria-live="polite">
      {p.reachable === 0 && p.matched === 0 && <p className="rounded-lg border border-brand-peach bg-peach-tint px-3 py-2">Nobody matches these rules yet. Try loosening a rule, or check the numbers.</p>}
      <p><b className="text-lg tabular-nums">{num(p.reachable)}</b> {p.reachable === 1 ? "person" : "people"} can be emailed{p.excluded > 0 && <span className="text-muted"> ({num(p.excluded)} more match but are unsubscribed, bounced or suspended and will be skipped)</span>}.</p>
      {p.sample.length > 0 && <ul className="divide-y divide-line rounded-lg border border-line">{p.sample.map((s) => <li key={s.user_id} className="flex flex-wrap justify-between gap-x-4 px-3 py-1.5"><span className="break-all">{s.email}</span><span className="text-muted">{s.company} · joined {ago(s.joined)}</span></li>)}</ul>}
      {p.reachable > p.sample.length && <p className="text-xs text-muted">Showing the {p.sample.length} newest.</p>}
    </div>
  );
}

function Editor({ fields, seg, example, onDone }: { fields: FieldDef[]; seg: Segment | null; example: number | null; onDone: () => void }) {
  const qc = useQueryClient();
  const toast = useToast();
  const ex = example !== null ? EXAMPLES[example] : undefined;
  const [name, setName] = useState(seg?.name ?? ex?.name ?? "");
  const [description, setDescription] = useState(seg?.description ?? ex?.note ?? "");
  const [rules, setRules] = useState<Rules>(seg?.rules ?? ex?.rules ?? EMPTY);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [previewErr, setPreviewErr] = useState<string | null>(null);
  const [checking, setChecking] = useState(false);

  // The count updates itself shortly after the rules stop changing, so nobody saves a segment blind.
  useEffect(() => {
    if (countRules(rules) === 0) { setPreview(null); setPreviewErr(null); setChecking(false); return; }
    setChecking(true);
    const t = setTimeout(() => {
      unwrap(api.POST("/v1/admin/marketing/segments/preview", { body: { rules: cleanRules(rules) } }))
        .then((p) => { setPreview(p as unknown as Preview); setPreviewErr(null); })
        .catch((e: Error) => { setPreview(null); setPreviewErr(e.message); })
        .finally(() => setChecking(false));
    }, 500);
    return () => clearTimeout(t);
  }, [rules]);

  const save = useMutation({
    mutationFn: () => {
      const body = { name, description, rules: cleanRules(rules) };
      return seg ? unwrap(api.PUT("/v1/admin/marketing/segments/{segment_id}", { params: { path: { segment_id: seg.id } }, body })) : unwrap(api.POST("/v1/admin/marketing/segments", { body }));
    },
    onSuccess: async () => { await qc.invalidateQueries({ queryKey: ["segments"] }); toast(seg ? "Segment saved." : "Segment created. You can now send an email to it."); onDone(); },
  });

  return (
    <div className="space-y-4">
      <Crumbs trail={[["Segments", `${MARKETING}/segments`], [seg ? `Edit “${seg.name}”` : "New segment"]]} />
      <div className="grid items-start gap-6 lg:grid-cols-[minmax(0,1fr)_22rem]">
        <Card>
          <div className="space-y-6">
            <Step n={1} title="Name it" hint="Something that will make sense to you in a list.">
              <label className="block text-sm font-semibold">Name<input className={inputCls} value={name} maxLength={120} placeholder="e.g. Joined this week, no video yet" onChange={(e) => setName(e.target.value)} /></label>
              <label className="block text-sm font-semibold">Note <span className="font-normal text-muted">(optional)</span><input className={inputCls} value={description} onChange={(e) => setDescription(e.target.value)} /></label>
            </Step>
            <Step n={2} title="Choose who’s in it" hint="Add rules. The panel beside this shows who they pick as you go.">
              <RuleGroup fields={fields} group={rules} depth={1} onChange={setRules} />
            </Step>
            <ErrorBox error={save.error} />
            <div className="flex flex-wrap gap-2">
              <Button disabled={!name.trim() || countRules(rules) === 0 || save.isPending} onClick={() => save.mutate()}>{save.isPending ? "Saving…" : seg ? "Save changes" : "Save segment"}</Button>
              <Button variant="secondary" onClick={onDone}>Cancel</Button>
            </div>
          </div>
        </Card>
        <aside aria-label="Who this picks" className="lg:sticky lg:top-4">
          <Card title="Who this picks">
            {previewErr && <Notice tone="warn">{previewErr}</Notice>}
            {!previewErr && !preview && <p className="text-sm text-muted">{countRules(rules) === 0 ? "Add a rule and you’ll see how many people it picks, and who." : "Counting…"}</p>}
            {preview && <div className={checking ? "opacity-60" : ""}><Who p={preview} /></div>}
          </Card>
        </aside>
      </div>
    </div>
  );
}

export function SegmentsTab() {
  const qc = useQueryClient();
  const toast = useToast();
  const manage = useCan()("marketing.manage");
  const url = useUrlState();
  const edit = url.get("edit");
  const exampleIdx = url.get("example") !== null ? Number(url.get("example")) : null;
  const [viewing, setViewing] = useState<string | null>(null);
  const [removing, setRemoving] = useState<Segment | null>(null);
  const fields = useQuery({ queryKey: ["segment-fields"], queryFn: () => unwrap(api.GET("/v1/admin/marketing/segment-fields")).then((r) => (r as unknown as { fields: FieldDef[] }).fields) });
  const list = useQuery({ queryKey: ["segments"], queryFn: () => unwrap(api.GET("/v1/admin/marketing/segments")).then((r) => (r as unknown as { items: Segment[] }).items) });
  const detail = useQuery({ queryKey: ["segment", viewing], enabled: !!viewing, queryFn: () => unwrap(api.GET("/v1/admin/marketing/segments/{segment_id}", { params: { path: { segment_id: viewing! } } })) as unknown as Promise<Segment> });
  const remove = useMutation({
    mutationFn: (id: string) => unwrap(api.DELETE("/v1/admin/marketing/segments/{segment_id}", { params: { path: { segment_id: id } } })),
    onSuccess: async () => { setRemoving(null); await qc.invalidateQueries({ queryKey: ["segments"] }); toast("Segment deleted."); },
  });
  const done = () => url.set({ edit: null, example: null });
  const editing = edit && edit !== "new" ? list.data?.find((g) => g.id === edit) : null;

  if (edit && fields.data && (edit === "new" || editing)) return <Editor key={edit + String(exampleIdx)} fields={fields.data} seg={editing ?? null} example={edit === "new" ? exampleIdx : null} onDone={done} />;
  if (edit && edit !== "new" && list.isLoading) return <p aria-busy="true">Loading…</p>;

  return (
    <div className="space-y-5">
      <PageIntro
        title="Segments"
        how={["Add rules, like “joined in the last 7 days” or “has made no video”. Rules can be combined with all/any, and grouped.", "You’ll see how many people the rules pick, and who, before you save.", "Use a saved segment in a campaign (send once) or a workflow (emails over time). The people in it are worked out fresh each time, so it stays up to date."]}
        actions={manage && <Button onClick={() => url.set({ edit: "new", example: null })}>New segment</Button>}
      >A segment is a saved group of people you want to email, picked by rules. Make the group first, then choose what to send to it.</PageIntro>
      <ErrorBox error={fields.error ?? list.error ?? remove.error} />
      {list.isLoading ? <p aria-busy="true">Loading…</p> : list.data && list.data.length === 0 ? (
        <Card>
          <EmptyState title="You haven’t made a segment yet" actions={manage && <Button onClick={() => url.set({ edit: "new", example: null })}>Make your own</Button>}>
            Start from an example below, or make your own from scratch.
          </EmptyState>
          {manage && <Examples onPick={(i) => url.set({ edit: "new", example: String(i) })} />}
        </Card>
      ) : (
        <>
          <ul className="space-y-3">
            {list.data?.map((g) => (
              <li key={g.id} className="rounded-xl border border-line bg-white p-4 text-sm shadow-sm">
                <div className="flex flex-wrap items-start justify-between gap-3">
                  <div className="min-w-0"><p className="text-base font-bold">{g.name}</p>{g.description && <p className="text-muted">{g.description}</p>}{fields.data && <p className="mt-1 text-xs text-muted">{describeRules(g.rules, fields.data)}</p>}<p className="mt-1 text-xs text-muted">Made {ago(g.created_at)} by {g.created_by}</p></div>
                  <div className="flex flex-wrap gap-2">
                    <Button variant="secondary" aria-expanded={viewing === g.id} onClick={() => setViewing(viewing === g.id ? null : g.id)}>{viewing === g.id ? "Hide people" : "See who’s in it"}</Button>
                    {manage && <Link className="inline-flex items-center rounded-lg border border-ink bg-brand-green px-4 py-2.5 text-sm font-semibold" to={`${MARKETING}/campaigns?new=1&segment=${g.id}`}>Send an email to it</Link>}
                    {manage && <Button variant="secondary" onClick={() => url.set({ edit: g.id })}>Edit</Button>}
                    {manage && <Button variant="danger" onClick={() => setRemoving(g)}>Delete</Button>}
                  </div>
                </div>
                {viewing === g.id && <div className="mt-3 border-t border-line pt-3">{detail.isLoading ? <p aria-busy="true">Counting…</p> : detail.data?.preview && <Who p={detail.data.preview} />}</div>}
              </li>
            ))}
          </ul>
          {manage && <details className="text-sm"><summary className="cursor-pointer font-semibold underline underline-offset-2">Start a new one from an example</summary><Examples onPick={(i) => url.set({ edit: "new", example: String(i) })} /></details>}
        </>
      )}
      {removing && <ConfirmDialog title="Delete this segment?" confirmLabel="Delete" onConfirm={() => remove.mutate(removing.id)} onCancel={() => setRemoving(null)}>“{removing.name}” will be removed. Emails already sent are not affected. Campaigns and workflows already using it keep working from the rules they were set up with.</ConfirmDialog>}
    </div>
  );
}

function Examples({ onPick }: { onPick: (i: number) => void }) {
  return (
    <ul className="mt-4 grid gap-3 sm:grid-cols-2" aria-label="Example segments">
      {EXAMPLES.map((e, i) => (
        <li key={e.name}><button type="button" onClick={() => onPick(i)} className="h-full w-full rounded-xl border border-line bg-white p-3 text-left text-sm transition hover:border-ink hover:bg-paper"><b className="block">{e.name}</b><span className="text-muted">{e.note}</span></button></li>
      ))}
    </ul>
  );
}
