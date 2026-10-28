import { useMutation, useQuery, useQueryClient } from "@tanstack/react-query";
import { useEffect, useRef, useState } from "react";
import { api, type Schemas, unwrap } from "../api/client";
import { Button, Card, ErrorBox, Field, Notice, inputCls } from "../components/ui";
import { guest, must } from "../founder/guestApi";
import { micLevel, openStream } from "../founder/media";
import { InterviewRoom } from "./InterviewRoom";
import { type Realtime, joinRealtime } from "./realtime";
import { mmss } from "./timing";
import type { VoiceLine } from "./voice";

type Status = Schemas["InterviewStatusOut"];
type Start = Schemas["LiveStartOut"];
type Plan = { layout: string; order: number[]; answers: { question_index: number; include: boolean; trim_start_s: number; trim_end_s: number }[] };

const useStatus = (projectId: string) =>
  useQuery({ queryKey: ["interview", projectId], queryFn: () => unwrap(api.GET("/v1/projects/{project_id}/interview", { params: { path: { project_id: projectId } } })) });

type Session = { start: Start; lines: VoiceLine[]; stream: MediaStream; indices: number[]; intro: boolean; realtime: Realtime | null };

// Everything about the AI interview on the dashboard (project state: interviewing).
export function LiveInterviewPanel({ projectId, founderName, founderTitle, guided = false }: { projectId: string; founderName: string; founderTitle: string; guided?: boolean }) {
  const qc = useQueryClient();
  const path = { params: { path: { project_id: projectId } } };
  const status = useStatus(projectId);
  const understanding = useQuery({ queryKey: ["understanding", projectId], queryFn: () => unwrap(api.GET("/v1/projects/{project_id}/understanding", path)) });
  const [name, setName] = useState(founderName);
  const [title, setTitle] = useState(founderTitle);
  const [agree, setAgree] = useState(false);
  const [session, setSession] = useState<Session | null>(null); // prepared: camera on, voice ready
  const [inRoom, setInRoom] = useState(false);
  const [busy, setBusy] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const refresh = () => { qc.invalidateQueries({ queryKey: ["interview", projectId] }); qc.invalidateQueries({ queryKey: ["project", projectId] }); };

  const s: Status | undefined = status.data;
  const answered = new Set((s?.takes ?? []).filter((t) => ["ready", "needs_retake"].includes(t.status)).map((t) => t.question_index));
  const unanswered = (s?.questions ?? []).map((_, i) => i).filter((i) => !answered.has(i));
  const finished = (s?.questions.length ?? 0) > 0 && unanswered.length === 0; // every answer recorded: review them

  // Turn the camera on (this must happen on a click), open the room, and ready the interviewer's voice.
  const prepare = async (indices: number[], intro: boolean) => {
    setError(null);
    try {
      setBusy("Turning on your camera…");
      let stream: MediaStream;
      try { stream = await openStream("video"); } catch (e) {
        throw new Error((e as DOMException).name === "NotAllowedError"
          ? "Your camera was blocked. Click the camera icon in your browser's address bar, allow the camera and microphone, then try again. This interview needs your camera."
          : "We couldn't find a camera. Plug one in or use a device with a camera, then try again.");
      }
      if (!stream.getVideoTracks().length) throw new Error("This interview needs your camera to be on.");
      setBusy("Opening your interview…");
      const start = await unwrap(api.POST("/v1/projects/{project_id}/interview/live", { ...path, body: { founder_name: name.trim(), founder_title: title.trim(), consent: true } }));
      setBusy("Getting your interviewer ready…");
      const voice = await must(guest.POST("/v1/interview/{token}/voice", { params: { path: { token: start.token } } }));
      setBusy("Joining the interview room…");
      const realtime = await joinRealtime(start.token, stream).catch(() => null); // null: the browser runs the interview on its own
      setSession({ start, lines: voice.lines, stream, indices, intro, realtime });
    } catch (e) {
      setError((e as Error).message);
    } finally {
      setBusy(null);
    }
  };

  const closeSession = () => { session?.realtime?.close(); session?.stream.getTracks().forEach((t) => t.stop()); setSession(null); setInRoom(false); refresh(); };

  useEffect(() => () => { session?.realtime?.close(); session?.stream.getTracks().forEach((t) => t.stop()); }, [session]);

  if (session && inRoom) {
    return (
      <InterviewRoom
        token={session.start.token}
        questions={session.start.questions}
        indices={session.indices}
        lines={session.lines}
        stream={session.stream}
        realtime={session.realtime}
        founderName={session.start.founder_name}
        limits={{ maxAnswer: session.start.max_answer_s, minAnswer: session.start.min_answer_s }}
        intro={session.intro}
        onFinished={closeSession}
        onCancel={closeSession}
        reacquire={() => openStream("video")}
      />
    );
  }
  if (session) return <GetReady session={session} onStart={() => setInRoom(true)} onBack={closeSession} />;

  if (finished && s) return <Review projectId={projectId} status={s} guided={guided} onRedo={(q) => void prepare([q], false)} busy={busy} error={error} />;

  const resuming = (s?.takes.length ?? 0) > 0 && unanswered.length > 0;
  const facts = understanding.data;
  return (
    <Card title="Your AI interview">
      <div className="space-y-4">
        <Notice tone="ok">
          {guided ? "Our AI interviewer will talk with you on camera: up to" : "Your script is approved. Before we make your video, our AI interviewer will talk with you on camera: up to"} {s?.questions.length ?? 4} questions, about 4 minutes, no more than 5.
          {" "}Your answers are woven into the video next to the AI presenter.
        </Notice>
        {facts && (facts.announcement || facts.key_facts.length > 0) && (
          <section className="rounded-md border-2 border-ink p-3 text-sm" aria-labelledby="understood">
            <h3 id="understood" className="mb-1 font-mono text-sm font-bold">What we understood from your announcement</h3>
            {facts.company && <p><strong>{facts.company}</strong>{facts.announcement ? `: ${facts.announcement}` : ""}</p>}
            {facts.key_facts.length > 0 && <ul className="mt-1 list-disc pl-5 text-muted">{facts.key_facts.slice(0, 5).map((f) => <li key={f}>{f}</li>)}</ul>}
          </section>
        )}
        <div>
          <h3 className="mb-1 font-mono text-sm font-bold">The questions</h3>
          <ol className="list-decimal space-y-1 pl-5 text-sm">{(s?.questions ?? []).map((q, i) => <li key={i} className={answered.has(i) ? "text-muted line-through" : ""}>{q}</li>)}</ol>
        </div>
        <ul className="list-disc space-y-1 pl-5 text-sm">
          <li><strong>Your camera must be on.</strong> We use stills and video of you answering in the final video.</li>
          <li>Find a quiet spot with light on your face. The interviewer speaks out loud: use headphones if you can.</li>
          <li>You can stop at any time. You'll review every answer before anything is made.</li>
        </ul>
        {resuming ? (
          <p className="text-sm">You answered {answered.size} of {s?.questions.length} questions earlier. We'll carry on with the rest.</p>
        ) : (
          <div className="grid gap-3 sm:grid-cols-2">
            <Field label="Your name" hint="The interviewer greets you by name.">{(id) => <input id={id} required className={inputCls} value={name} onChange={(e) => setName(e.target.value)} />}</Field>
            <Field label="Your role (shown on screen)">{(id) => <input id={id} className={inputCls} placeholder="CEO, Acme" value={title} onChange={(e) => setTitle(e.target.value)} />}</Field>
          </div>
        )}
        <section className="rounded-md border-2 border-ink bg-paper p-3 text-sm" aria-labelledby="consent-h">
          <h3 id="consent-h" className="mb-1 font-mono text-sm font-bold">How your recording will be used</h3>
          <p>{s?.consent_text ?? "Your recording will be used only in this video."}</p>
          <label className="mt-2 flex items-start gap-2"><input type="checkbox" className="mt-1" checked={agree} onChange={(e) => setAgree(e.target.checked)} /> <span>I understand and agree.</span></label>
        </section>
        <ErrorBox error={error ? new Error(error) : null} />
        <div className="flex flex-wrap items-center gap-3">
          <Button disabled={!agree || !name.trim() || !!busy || !s} onClick={() => void prepare(resuming ? unanswered : (s?.questions ?? []).map((_, i) => i), !resuming)}>
            {busy ?? (resuming ? "Continue the interview" : "Get ready for the interview")}
          </Button>
          {!guided && <SkipButton projectId={projectId} />}
        </div>
      </div>
    </Card>
  );
}

function SkipButton({ projectId }: { projectId: string }) {
  const qc = useQueryClient();
  const skip = useMutation({
    mutationFn: () => unwrap(api.POST("/v1/projects/{project_id}/interview/live/skip", { params: { path: { project_id: projectId } } })),
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["project", projectId] }); },
  });
  return (
    <>
      <Button variant="secondary" disabled={skip.isPending} onClick={() => { if (confirm("Skip the interview and make the presenter-only video?")) skip.mutate(); }}>Skip the interview</Button>
      <ErrorBox error={skip.error} />
    </>
  );
}

// Device check before the interview begins: the camera must be showing, the microphone must hear you.
function GetReady({ session, onStart, onBack }: { session: Session; onStart: () => void; onBack: () => void }) {
  const video = useRef<HTMLVideoElement>(null);
  const [level, setLevel] = useState(0);
  const [heard, setHeard] = useState(false);
  const greeting = session.lines.find((l) => l.key === "greeting")?.text ?? "";
  useEffect(() => { if (video.current) video.current.srcObject = session.stream; }, [session.stream]);
  useEffect(() => micLevel(session.stream, (l) => { setLevel(l); if (l > 0.08) setHeard(true); }), [session.stream]);
  const live = session.stream.getVideoTracks().some((t) => t.readyState === "live");
  return (
    <Card title="Check your camera and microphone">
      <div className="grid gap-4 md:grid-cols-2">
        <div className="relative overflow-hidden rounded-md bg-black">
          <video ref={video} autoPlay muted playsInline className="aspect-video w-full object-cover [transform:scaleX(-1)]" aria-label="Your camera preview" />
          <div aria-hidden className="pointer-events-none absolute inset-0 flex items-center justify-center"><div className="h-3/4 w-1/3 rounded-[50%] border-4 border-dashed border-white/70" /></div>
        </div>
        <div className="space-y-3 text-sm">
          <p className={live ? "font-bold" : "font-bold text-ink"}>{live ? "✓ Your camera is on" : "✗ Your camera is off"}</p>
          <div>
            <p className="mb-1 font-bold">{heard ? "✓ We can hear you" : "Say something to test your microphone…"}</p>
            <div className="h-3 overflow-hidden rounded bg-line" role="meter" aria-valuenow={Math.round(level * 100)} aria-valuemin={0} aria-valuemax={100} aria-label="Microphone level"><div className="h-full bg-brand-green transition-all" style={{ width: `${level * 100}%` }} /></div>
          </div>
          <p className="text-muted">Keep your face inside the oval. The interviewer will say:</p>
          <blockquote className="border-l-4 border-brand-green pl-3 font-mono text-sm">“{greeting}”</blockquote>
          <p className="text-muted">The whole interview is about {mmss(240)}, never more than {mmss(300)}.</p>
          <div className="flex flex-wrap gap-2 pt-1">
            <Button disabled={!live} onClick={onStart}>Start the interview</Button>
            <Button variant="secondary" onClick={onBack}>Back</Button>
          </div>
        </div>
      </div>
    </Card>
  );
}

// After the interview: check every answer, choose the layout, redo any answer, then make the video.
function Review({ projectId, status, guided, onRedo, busy, error }: { projectId: string; status: Status; guided: boolean; onRedo: (q: number) => void; busy: string | null; error: string | null }) {
  const qc = useQueryClient();
  const path = { params: { path: { project_id: projectId } } };
  const [plan, setPlan] = useState<Plan | null>(null);
  useEffect(() => {
    if (!status.plan || plan) return;
    const p = status.plan as Plan;
    setPlan(p); // every answer is in the video unless the owner leaves one out
  }, [status.plan, plan, guided]);
  const make = useMutation({
    mutationFn: async () => {
      await unwrap(api.PUT("/v1/projects/{project_id}/interview/plan", { ...path, body: plan! }));
      return unwrap(api.POST("/v1/projects/{project_id}/interview/merge", path));
    },
    onSuccess: () => { qc.invalidateQueries({ queryKey: ["project", projectId] }); qc.invalidateQueries({ queryKey: ["interview", projectId] }); qc.invalidateQueries({ queryKey: ["script", projectId] }); },
  });
  if (!plan) return <Card title="Review your interview"><p aria-busy="true">Loading…</p></Card>;
  const update = (q: number, patch: Partial<Plan["answers"][number]>) => setPlan({ ...plan, answers: plan.answers.map((a) => (a.question_index === q ? { ...a, ...patch } : a)) });
  const total = status.takes.reduce((n, t) => n + Number(t.duration_s ?? 0), 0);
  return (
    <Card title="Review your interview">
      <div className="space-y-4">
        <Notice tone="ok">Great interview{status.founder_name ? `, ${status.founder_name.split(" ")[0]}` : ""}. You spoke for {mmss(total)}. {guided ? `Every answer goes into your video; untick any you would rather leave out. Next we write your story from everything you said, and you check it before anything is made.` : "Check your answers, then we'll create your AI presenter and weave your answers into the video."}</Notice>
        <Field label="How your answers appear in the video">
          {(id) => (
            <select id={id} className={inputCls} value={plan.layout} onChange={(e) => setPlan({ ...plan, layout: e.target.value })}>
              <option value="column">Your video with a column showing your question and your words</option>
              <option value="pip">Your video large, the presenter in a small window</option>
              <option value="split">Split screen</option>
              <option value="full">Your video full screen</option>
            </select>
          )}
        </Field>
        <ol className="space-y-3">
          {plan.order.map((q, pos) => {
            const t = status.takes.find((x) => x.question_index === q);
            const a = plan.answers.find((x) => x.question_index === q)!;
            return (
              <li key={q} className="grid gap-3 rounded-md border-2 border-ink p-3 md:grid-cols-[14rem_1fr]">
                {t?.video_url ? <video controls playsInline preload="metadata" poster={t.snapshot_url ?? undefined} className="aspect-video w-full rounded-sm bg-black object-cover" src={t.video_url} aria-label={`Your answer to question ${pos + 1}`} /> : <div className="grid aspect-video place-items-center rounded-sm bg-paper text-sm text-muted">No video</div>}
                <div className="space-y-2">
                  <p className="font-bold">{pos + 1}. {status.questions[q]}</p>
                  {t?.transcript && <p className="text-sm text-muted">“{t.transcript}”</p>}
                  {t && t.messages.length > 0 && <Notice tone="warn">{t.messages.join(" ")}</Notice>}
                  <div className="flex flex-wrap items-center gap-3 text-sm">
                    <label className="flex items-center gap-2"><input type="checkbox" checked={a.include} onChange={(e) => update(q, { include: e.target.checked })} /> {guided ? "Feature this answer in the video" : "Use this answer"}</label>
                    {t?.duration_s != null && <span className="text-muted">{Number(t.duration_s).toFixed(0)}s</span>}
                    <Button variant="secondary" disabled={!!busy} onClick={() => onRedo(q)}>{busy ?? "Record this one again"}</Button>
                  </div>
                </div>
              </li>
            );
          })}
        </ol>
        {!guided && <p className="text-sm text-muted">Next: the AI presenter is created from your script, then your answers are merged in. This takes a few minutes and uses credits.</p>}
        <ErrorBox error={make.error ?? (error ? new Error(error) : null)} />
        <div className="flex flex-wrap gap-3">
          <Button onClick={() => make.mutate()} disabled={make.isPending || !plan.answers.some((a) => a.include)}>{make.isPending ? (guided ? "Writing your story…" : "Starting…") : guided ? "Write my story" : "Make my video"}</Button>
          {!guided && <SkipButton projectId={projectId} />}
        </div>
      </div>
    </Card>
  );
}
