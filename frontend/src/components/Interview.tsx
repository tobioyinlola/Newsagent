import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useState } from "react";
import { api, type Schemas, unwrap } from "../api/client";
import { Button, Card, ErrorBox, Field, inputCls, Notice } from "./ui";

type Status = Schemas["InterviewStatusOut"];
type Take = Schemas["TakeOut"];
const statusText: Record<string, string> = { ready: "Answered ✓", needs_retake: "Needs another take", processing: "Processing…", uploaded: "Processing…", failed: "Couldn't process", recording: "Recording…" };

export function useInterview(projectId: string, refetchMs?: number) {
  return useQuery({
    queryKey: ["interview", projectId],
    queryFn: () => unwrap(api.GET("/v1/projects/{project_id}/interview", { params: { path: { project_id: projectId } } })),
    refetchInterval: refetchMs,
  });
}

const copyText = async (t: string) => { try { await navigator.clipboard.writeText(t); return true; } catch { return false; } };

// Shown while the project waits for the founder (state: awaiting_founder).
export function InterviewPanel({ projectId }: { projectId: string }) {
  const qc = useQueryClient();
  const path = { params: { path: { project_id: projectId } } };
  const st = useInterview(projectId, 5000);
  const [f, setF] = useState({ name: "", title: "", email: "" });
  const [link, setLink] = useState<{ url: string; emailed: boolean } | null>(null);
  const [copied, setCopied] = useState(false);
  const refresh = () => { qc.invalidateQueries({ queryKey: ["interview", projectId] }); qc.invalidateQueries({ queryKey: ["project", projectId] }); };
  const invite = useMutation({
    mutationFn: () => unwrap(api.POST("/v1/projects/{project_id}/interview", { ...path, body: { founder_name: f.name, founder_title: f.title, founder_email: f.email || null } })),
    onSuccess: (d) => { setLink({ url: d.url, emailed: d.emailed }); refresh(); },
  });
  const revoke = useMutation({ mutationFn: () => unwrap(api.DELETE("/v1/projects/{project_id}/interview", path)), onSuccess: () => { setLink(null); refresh(); } });
  const skip = useMutation({ mutationFn: () => unwrap(api.POST("/v1/projects/{project_id}/interview/merge", path)), onSuccess: refresh });
  const s = st.data;

  return (
    <Card title="Founder interview">
      <div className="space-y-4">
        {link && (
          <Notice tone="ok">
            <p className="font-semibold">Private link created{link.emailed ? " and emailed to your founder" : ""}.</p>
            <p className="mt-1">It is shown once. Copy it to send it yourself:</p>
            <div className="mt-2 flex gap-2">
              <input readOnly aria-label="Founder link" className="w-full rounded-md border border-ink bg-white px-3 py-2 text-sm" value={link.url} onFocus={(e) => e.currentTarget.select()} />
              <Button variant="secondary" onClick={async () => { setCopied(await copyText(link.url)); }}>{copied ? "Copied" : "Copy"}</Button>
            </div>
          </Notice>
        )}
        {s?.active ? (
          <div className="space-y-3">
            <p><strong>{s.founder_name}</strong>{s.founder_title ? `, ${s.founder_title}` : ""} · link expires {s.expires_at ? new Date(s.expires_at).toLocaleDateString() : ""}</p>
            <p className="text-sm text-muted">{s.consented ? "They have read how their recording will be used." : "They haven't opened the link yet."} {s.reminders_sent > 0 && `Reminders sent: ${s.reminders_sent}.`}</p>
            <ul className="divide-y divide-line text-sm" aria-label="Interview progress">
              {s.questions.map((q, i) => {
                const t = s.takes.find((x) => x.question_index === i);
                return <li key={i} className="flex justify-between gap-3 py-2"><span>{q}</span><span className="whitespace-nowrap text-muted">{t ? statusText[t.status] ?? t.status : "Waiting"}</span></li>;
              })}
            </ul>
            <p className="text-sm text-muted">We'll email you when they submit. Reminders go out automatically if they haven't.</p>
            <div className="flex flex-wrap gap-2">
              <Button variant="secondary" onClick={() => revoke.mutate()} disabled={revoke.isPending}>Revoke link</Button>
            </div>
          </div>
        ) : (
          <form className="grid gap-3 sm:grid-cols-2" onSubmit={(e) => { e.preventDefault(); invite.mutate(); }}>
            <p className="sm:col-span-2 text-sm text-muted">Create a private link for your founder. No account is needed; it works on a phone and expires in 14 days.</p>
            <Field label="Founder's name">{(id) => <input id={id} required className={inputCls} value={f.name} onChange={(e) => setF({ ...f, name: e.target.value })} />}</Field>
            <Field label="Title (shown on screen)">{(id) => <input id={id} className={inputCls} placeholder="CEO, Acme" value={f.title} onChange={(e) => setF({ ...f, title: e.target.value })} />}</Field>
            <div className="sm:col-span-2"><Field label="Email (optional)" hint="We'll email the link and send gentle reminders. Or copy the link and send it yourself.">{(id) => <input id={id} type="email" className={inputCls} value={f.email} onChange={(e) => setF({ ...f, email: e.target.value })} />}</Field></div>
            <div className="sm:col-span-2"><Button type="submit" disabled={invite.isPending}>Create link</Button></div>
          </form>
        )}
        <ErrorBox error={invite.error ?? revoke.error ?? skip.error} />
        <div className="border-t border-line pt-3">
          <p className="mb-2 text-sm text-muted">Don't need the interview? Make the anchor-only video instead.</p>
          <Button variant="secondary" disabled={skip.isPending} onClick={() => { if (confirm("Skip the interview and make the anchor-only video?")) skip.mutate(); }}>Skip the interview</Button>
        </div>
      </div>
    </Card>
  );
}

type Plan = { layout: string; order: number[]; answers: { question_index: number; include: boolean; trim_start_s: number; trim_end_s: number }[] };

// Shown once the founder has submitted (state: processing_founder): review, arrange, then make the final video.
export function ReviewPanel({ projectId, keepRaw }: { projectId: string; keepRaw: boolean }) {
  const qc = useQueryClient();
  const path = { params: { path: { project_id: projectId } } };
  const st = useInterview(projectId);
  const [plan, setPlan] = useState<Plan | null>(null);
  const [keep, setKeep] = useState(keepRaw);
  const [retake, setRetake] = useState<{ q: number; note: string } | null>(null);
  useEffect(() => { if (st.data?.plan && !plan) setPlan(st.data.plan as Plan); }, [st.data, plan]);
  const refresh = () => { qc.invalidateQueries({ queryKey: ["interview", projectId] }); qc.invalidateQueries({ queryKey: ["project", projectId] }); };
  const make = useMutation({
    mutationFn: async () => {
      await unwrap(api.PUT("/v1/projects/{project_id}/interview/plan", { ...path, body: plan! }));
      await unwrap(api.PUT("/v1/projects/{project_id}/keep-raw-takes", { ...path, body: { keep } }));
      return unwrap(api.POST("/v1/projects/{project_id}/interview/merge", path));
    },
    onSuccess: refresh,
  });
  const askRetake = useMutation({
    mutationFn: () => unwrap(api.POST("/v1/projects/{project_id}/interview/retake", { ...path, body: { question_index: retake!.q, note: retake!.note } })),
    onSuccess: () => { setRetake(null); refresh(); },
  });
  const s: Status | undefined = st.data;
  if (!s || !plan) return <Card title="Review the answers"><p aria-busy="true">Loading…</p></Card>;

  const update = (q: number, patch: Partial<Plan["answers"][number]>) => setPlan({ ...plan, answers: plan.answers.map((a) => (a.question_index === q ? { ...a, ...patch } : a)) });
  const move = (pos: number, dir: -1 | 1) => { const o = [...plan.order]; const j = pos + dir; if (j < 0 || j >= o.length) return; [o[pos], o[j]] = [o[j], o[pos]]; setPlan({ ...plan, order: o }); };
  const takeFor = (q: number): Take | undefined => s.takes.find((t) => t.question_index === q);

  return (
    <Card title="Review the answers">
      <div className="space-y-4">
        <Notice>{s.founder_name} has submitted. Check each answer, choose a layout, then make the final video. You can trim, reorder or drop answers.</Notice>
        <Field label="Layout">
          {(id) => (
            <select id={id} className={inputCls} value={plan.layout} onChange={(e) => setPlan({ ...plan, layout: e.target.value })}>
              <option value="pip">Founder large, anchor in a small window</option>
              <option value="split">Split screen</option>
              <option value="full">Founder full screen</option>
            </select>
          )}
        </Field>
        <ol className="space-y-4">
          {plan.order.map((q, pos) => {
            const t = takeFor(q);
            const a = plan.answers.find((x) => x.question_index === q)!;
            return (
              <li key={q} className="space-y-2 rounded-md border border-line p-3">
                <div className="flex items-start justify-between gap-2">
                  <p className="font-medium">{pos + 1}. {s.questions[q]}</p>
                  <span className="flex gap-1"><Button variant="secondary" aria-label={`Move question ${q + 1} up`} disabled={pos === 0} onClick={() => move(pos, -1)}>↑</Button><Button variant="secondary" aria-label={`Move question ${q + 1} down`} disabled={pos === plan.order.length - 1} onClick={() => move(pos, 1)}>↓</Button></span>
                </div>
                {t?.video_url ? <video controls playsInline className="max-h-72 rounded bg-black" src={t.video_url} aria-label={`Answer to question ${q + 1}`} /> : t?.audio_url ? <audio controls src={t.audio_url} aria-label={`Answer to question ${q + 1}`} /> : <p className="text-sm text-muted">No answer.</p>}
                {t?.transcript && <p className="text-sm text-muted">“{t.transcript}”</p>}
                {t && t.messages.length > 0 && <Notice tone="warn">{t.messages.join(" ")}</Notice>}
                <div className="flex flex-wrap items-end gap-3 text-sm">
                  <label className="flex items-center gap-2"><input type="checkbox" checked={a.include} onChange={(e) => update(q, { include: e.target.checked })} /> Include</label>
                  <label className="flex items-center gap-1">Cut from start (s)<input type="number" min={0} step={0.5} className="w-20 rounded border border-ink px-2 py-1" value={a.trim_start_s} onChange={(e) => update(q, { trim_start_s: Number(e.target.value) })} /></label>
                  <label className="flex items-center gap-1">Cut from end (s)<input type="number" min={0} step={0.5} className="w-20 rounded border border-ink px-2 py-1" value={a.trim_end_s} onChange={(e) => update(q, { trim_end_s: Number(e.target.value) })} /></label>
                  {t?.duration_s != null && <span className="text-muted">length {Number(t.duration_s).toFixed(1)}s</span>}
                  <Button variant="secondary" onClick={() => setRetake({ q, note: "" })}>Ask for a retake</Button>
                </div>
                {retake?.q === q && (
                  <div className="flex gap-2"><input aria-label="Note to your founder" placeholder="What should they change? (optional)" className={inputCls} value={retake.note} onChange={(e) => setRetake({ q, note: e.target.value })} /><Button onClick={() => askRetake.mutate()} disabled={askRetake.isPending}>Send request</Button></div>
                )}
              </li>
            );
          })}
        </ol>
        <label className="flex items-start gap-2 text-sm"><input type="checkbox" className="mt-1" checked={keep} onChange={(e) => setKeep(e.target.checked)} /><span>Keep the founder's original recordings after 90 days. Otherwise they're deleted 90 days after this video is finished.</span></label>
        <ErrorBox error={make.error ?? askRetake.error} />
        <Button onClick={() => make.mutate()} disabled={make.isPending}>Make the final video</Button>
      </div>
    </Card>
  );
}
