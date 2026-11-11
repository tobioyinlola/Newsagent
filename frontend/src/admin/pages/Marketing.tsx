import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { api, unwrap } from "../api/client";
import { Button, Card, ConfirmDialog, ErrorBox, inputCls, Notice } from "../components/ui";
import { ago, num } from "../lib/format";
import { useCan } from "../lib/can";
import { CampaignsTab } from "./MarketingCampaigns";
import { ActivityTab } from "./MarketingActivity";
import { CopiesTab } from "./MarketingCopies";
import { OptoutsTab } from "./MarketingOptouts";
import { WorkflowsTab } from "./MarketingWorkflows";
import { blankCondition, cleanRules, type Condition, countRules, describe, describeRules, type FieldDef, isGroup, MAX_DEPTH, OP_LABEL, type Preview, type Rules, type Segment } from "../lib/segments";

type Status = { engine: "off" | "on" | "dry_run"; config: { paused: boolean; min_gap_days: number; daily_cap: number; per_minute: number; track: boolean }; sent_today: number; opted_out: number; suppressed: number; bounce_events: boolean };
const ENGINE: Record<Status["engine"], string> = { off: "Off: nothing is sent", dry_run: "Dry run: logged, not sent", on: "On" };
const EMPTY: Rules = { match: "all", conditions: [] };

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
      <p><b className="text-lg tabular-nums">{num(p.reachable)}</b> people can be emailed{p.excluded > 0 && <span className="text-muted"> ({num(p.excluded)} more match but are unsubscribed, bounced or suspended and will be skipped)</span>}.</p>
      {p.sample.length > 0 && <ul className="divide-y divide-line rounded-lg border border-line">{p.sample.map((s) => <li key={s.user_id} className="flex flex-wrap justify-between gap-x-4 px-3 py-1.5"><span className="break-all">{s.email}</span><span className="text-muted">{s.company} · joined {ago(s.joined)}</span></li>)}</ul>}
      {p.reachable > p.sample.length && <p className="text-xs text-muted">Showing the {p.sample.length} newest.</p>}
    </div>
  );
}

function Editor({ fields, seg, onDone }: { fields: FieldDef[]; seg: Segment | null; onDone: () => void }) {
  const qc = useQueryClient();
  const [name, setName] = useState(seg?.name ?? "");
  const [description, setDescription] = useState(seg?.description ?? "");
  const [rules, setRules] = useState<Rules>(seg?.rules ?? EMPTY);
  const [preview, setPreview] = useState<Preview | null>(null);
  const [previewErr, setPreviewErr] = useState<string | null>(null);

  // The count updates itself shortly after the rules stop changing, so nobody saves a segment blind.
  useEffect(() => {
    if (countRules(rules) === 0) { setPreview(null); setPreviewErr(null); return; }
    const t = setTimeout(() => {
      unwrap(api.POST("/v1/admin/marketing/segments/preview", { body: { rules: cleanRules(rules) } })).then((p) => { setPreview(p as unknown as Preview); setPreviewErr(null); }).catch((e: Error) => { setPreview(null); setPreviewErr(e.message); });
    }, 500);
    return () => clearTimeout(t);
  }, [rules]);

  const save = useMutation({
    mutationFn: () => {
      const body = { name, description, rules: cleanRules(rules) };
      return seg ? unwrap(api.PUT("/v1/admin/marketing/segments/{segment_id}", { params: { path: { segment_id: seg.id } }, body })) : unwrap(api.POST("/v1/admin/marketing/segments", { body }));
    },
    onSuccess: async () => { await qc.invalidateQueries({ queryKey: ["segments"] }); onDone(); },
  });

  return (
    <Card title={seg ? "Edit segment" : "New segment"} actions={<Button variant="secondary" onClick={onDone}>Cancel</Button>}>
      <div className="space-y-4">
        <label className="block text-sm font-semibold">Name<input className={inputCls} value={name} maxLength={120} placeholder="e.g. Joined this week, no video yet" onChange={(e) => setName(e.target.value)} /></label>
        <label className="block text-sm font-semibold">Note (optional)<input className={inputCls} value={description} onChange={(e) => setDescription(e.target.value)} /></label>
        <RuleGroup fields={fields} group={rules} depth={1} onChange={setRules} />
        {previewErr && <Notice tone="warn">{previewErr}</Notice>}
        {preview && <Who p={preview} />}
        {!preview && !previewErr && <p className="text-sm text-muted">Add a rule to see who it picks.</p>}
        <ErrorBox error={save.error} />
        <Button disabled={!name.trim() || countRules(rules) === 0 || save.isPending} onClick={() => save.mutate()}>{save.isPending ? "Saving…" : "Save segment"}</Button>
      </div>
    </Card>
  );
}

export function MarketingAdmin() {
  const qc = useQueryClient();
  const can = useCan();
  const manage = can("marketing.manage");
  const [tab, setTab] = useState<"segments" | "copies" | "campaigns" | "workflows" | "activity" | "optouts">("segments");
  const [editing, setEditing] = useState<Segment | "new" | null>(null);
  const [viewing, setViewing] = useState<string | null>(null);
  const [removing, setRemoving] = useState<Segment | null>(null);
  const status = useQuery({ queryKey: ["marketing-status"], queryFn: () => unwrap(api.GET("/v1/admin/marketing/status")) as unknown as Promise<Status> });
  const fields = useQuery({ queryKey: ["segment-fields"], queryFn: () => unwrap(api.GET("/v1/admin/marketing/segment-fields")).then((r) => (r as unknown as { fields: FieldDef[] }).fields) });
  const list = useQuery({ queryKey: ["segments"], queryFn: () => unwrap(api.GET("/v1/admin/marketing/segments")).then((r) => (r as unknown as { items: Segment[] }).items) });
  const detail = useQuery({ queryKey: ["segment", viewing], enabled: !!viewing, queryFn: () => unwrap(api.GET("/v1/admin/marketing/segments/{segment_id}", { params: { path: { segment_id: viewing! } } })) as unknown as Promise<Segment> });
  const pause = useMutation({
    mutationFn: (change: Partial<Status["config"]>) => unwrap(api.PUT("/v1/admin/marketing/config", { body: { ...status.data!.config, ...change } })),
    onSuccess: () => qc.invalidateQueries({ queryKey: ["marketing-status"] }),
  });
  const remove = useMutation({
    mutationFn: (id: string) => unwrap(api.DELETE("/v1/admin/marketing/segments/{segment_id}", { params: { path: { segment_id: id } } })),
    onSuccess: async () => { setRemoving(null); await qc.invalidateQueries({ queryKey: ["segments"] }); },
  });
  const s = status.data;
  return (
    <>
      <h1 className="text-2xl font-bold">Marketing</h1>
      <ErrorBox error={status.error ?? fields.error ?? list.error ?? pause.error ?? remove.error} />
      {s && (
        <Card title="Sending">
          <div className="flex flex-wrap items-center justify-between gap-3 text-sm">
            <div className="space-y-1">
              <p><b>{ENGINE[s.engine]}</b>{s.config.paused && <span className="ml-2 rounded-sm bg-brand-red px-1.5 py-0.5 text-xs font-bold">Paused</span>}</p>
              <p className="text-muted">{num(s.sent_today)} sent today (limit {num(s.config.daily_cap)}) · at most one email per person every {s.config.min_gap_days} days · up to {num(s.config.per_minute)} a minute · {num(s.opted_out)} unsubscribed · {num(s.suppressed)} blocked addresses</p>
              <label className="flex items-center gap-2 text-muted"><input type="checkbox" checked={s.config.track} disabled={!manage || pause.isPending} onChange={(e) => pause.mutate({ track: e.target.checked })} /> Count opens and clicks (adds a tiny picture, and sends the button through our site)</label>
              {s.engine !== "off" && !s.bounce_events && <p className="rounded-lg border border-brand-peach bg-peach-tint px-3 py-2">Bounces and spam complaints aren’t being reported to us yet, so bad addresses won’t block themselves. Set RESEND_EVENTS_SECRET and add the webhook in Resend (see docs/marketing-email-setup.md).</p>}
              {s.engine === "off" && <p className="text-muted">Marketing email is switched off on the server (MARKETING_EMAIL). Segments still work.</p>}
            </div>
            {manage && <Button variant={s.config.paused ? "primary" : "danger"} disabled={pause.isPending} onClick={() => pause.mutate({ paused: !s.config.paused })}>{s.config.paused ? "Resume sending" : "Pause all marketing"}</Button>}
          </div>
        </Card>
      )}
      <div role="tablist" aria-label="Marketing sections" className="flex gap-2">
        {([["segments", "Segments"], ["copies", "Email copy"], ["campaigns", "Campaigns"], ["workflows", "Workflows"], ["activity", "Activity"], ["optouts", "Opt-outs"]] as const).map(([k, label]) => <button key={k} role="tab" aria-selected={tab === k} type="button" onClick={() => setTab(k)} className={`rounded-lg border px-4 py-2 text-sm font-semibold ${tab === k ? "border-ink bg-brand-green" : "border-line bg-white hover:border-ink"}`}>{label}</button>)}
      </div>
      {tab === "copies" ? <CopiesTab /> : tab === "campaigns" ? <CampaignsTab engine={s?.engine ?? "off"} /> : tab === "workflows" ? <WorkflowsTab engine={s?.engine ?? "off"} /> : tab === "activity" ? <ActivityTab /> : tab === "optouts" ? <OptoutsTab /> : editing && fields.data ? <Editor fields={fields.data} seg={editing === "new" ? null : editing} onDone={() => { setEditing(null); setViewing(null); }} /> : (
        <Card title="Segments" actions={manage && <Button onClick={() => setEditing("new")}>New segment</Button>}>
          {list.isLoading ? <p aria-busy="true">Loading…</p> : list.data && list.data.length === 0 ? <p className="text-sm text-muted">No segments yet. A segment is a saved group of people, for example “joined 3 to 7 days ago and has made no video”.</p> : (
            <ul className="space-y-3">
              {list.data?.map((g) => (
                <li key={g.id} className="rounded-xl border border-line p-3 text-sm">
                  <div className="flex flex-wrap items-start justify-between gap-2">
                    <div><p className="font-bold">{g.name}</p>{g.description && <p className="text-muted">{g.description}</p>}</div>
                    <div className="flex gap-2">
                      <Button variant="secondary" onClick={() => setViewing(viewing === g.id ? null : g.id)}>{viewing === g.id ? "Hide" : "Who’s in it"}</Button>
                      {manage && <Button variant="secondary" onClick={() => setEditing(g)}>Edit</Button>}
                      {manage && <Button variant="danger" onClick={() => setRemoving(g)}>Delete</Button>}
                    </div>
                  </div>
                  {fields.data && <p className="mt-2 text-xs text-muted">{describeRules(g.rules, fields.data)}</p>}
                  {viewing === g.id && <div className="mt-3 border-t border-line pt-3">{detail.isLoading ? <p aria-busy="true">Counting…</p> : detail.data?.preview && <Who p={detail.data.preview} />}</div>}
                </li>
              ))}
            </ul>
          )}
        </Card>
      )}
      {removing && <ConfirmDialog title="Delete this segment?" confirmLabel="Delete" onConfirm={() => remove.mutate(removing.id)} onCancel={() => setRemoving(null)}>“{removing.name}” will be removed. Nothing that was already sent is affected.</ConfirmDialog>}
    </>
  );
}
