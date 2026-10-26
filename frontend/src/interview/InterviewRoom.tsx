import { useCallback, useEffect, useRef, useState } from "react";
import { CFSymbol } from "../components/Logo";
import { CHUNK_MS, guest, must } from "../founder/guestApi";
import { pickMime } from "../founder/media";
import { ChunkStore } from "../founder/store";
import { TakeUploader } from "../founder/uploader";
import { grabFrame, uploadSnapshot } from "./snapshot";
import { MAX_TOTAL_S, answerWindow, mmss } from "./timing";
import { type VoiceLine, speak } from "./voice";
import { VoiceWave } from "./VoiceWave";

const store = new ChunkStore();
const sleep = (ms: number) => new Promise<void>((r) => setTimeout(r, ms));
const FAST = import.meta.env.VITE_INTERVIEW_FAST === "1"; // test builds only

type TakeState = { takeId: string; status: "uploading" | "processing" | "ready" | "needs_retake" | "failed"; messages: string[] };
type Phase = "starting" | "greeting" | "asking" | "answering" | "between" | "closing" | "finishing" | "attention" | "done";

export type RoomProps = {
  token: string;
  questions: string[];
  indices: number[]; // which questions to ask now: all of them, or just the ones being redone
  lines: VoiceLine[]; // greeting, q0.., thanks, closing
  stream: MediaStream;
  founderName: string;
  limits: { maxAnswer: number; minAnswer: number };
  intro: boolean; // say the greeting (not for a redo)
  onFinished: () => void;
  onCancel: () => void;
  reacquire: () => Promise<MediaStream>;
};

// The AI interviewer's room: it greets the person by name, asks each question aloud, records the answer on camera,
// keeps the whole thing inside about 5 minutes, and submits when every answer has been checked.
export function InterviewRoom(p: RoomProps) {
  const [phase, setPhase] = useState<Phase>("starting");
  const [pos, setPos] = useState(0);
  const [caption, setCaption] = useState("");
  const [speaking, setSpeaking] = useState(false);
  const [elapsed, setElapsed] = useState(0);
  const [ansElapsed, setAnsElapsed] = useState(0);
  const [ansWindow, setAnsWindow] = useState(0);
  const [takes, setTakes] = useState<Record<number, TakeState>>({});
  const [cameraLost, setCameraLost] = useState(false);
  const [error, setError] = useState<string | null>(null);
  const [overtime, setOvertime] = useState(false);

  const video = useRef<HTMLVideoElement>(null);
  const stream = useRef(p.stream);
  const t0 = useRef(0);
  const doneNow = useRef<(() => void) | null>(null); // "Done answering" pressed
  const recorder = useRef<MediaRecorder | null>(null);
  const lost = useRef(false);
  const takesRef = useRef<Record<number, TakeState>>({});
  const ctl = useRef<{ aborted: boolean }>({ aborted: false });
  const speakingNow = useRef<{ cancel: () => void } | null>(null);
  const redo = useRef<((q: number) => void) | null>(null);
  const [needsAttention, setNeedsAttention] = useState<number[]>([]);
  const keepAll = useRef<(() => void) | null>(null);

  const setTake = useCallback((q: number, t: TakeState) => {
    takesRef.current = { ...takesRef.current, [q]: t };
    setTakes(takesRef.current);
  }, []);

  const lineFor = (key: string): VoiceLine => p.lines.find((l) => l.key === key) ?? { key, text: key.startsWith("q") ? p.questions[Number(key.slice(1))] ?? "" : "" };
  const elapsedNow = () => (Date.now() - t0.current) / 1000;

  // the interviewer says a line; captions show it so the interview works even with the sound off
  const say = async (key: string, show = true) => {
    const line = lineFor(key);
    if (!line.text) return;
    if (show) setCaption(line.text);
    const s = speak(line, () => setSpeaking(true));
    speakingNow.current = s;
    await s.done;
    setSpeaking(false);
    speakingNow.current = null;
  };

  // ---- camera must stay on ----
  useEffect(() => {
    if (video.current) video.current.srcObject = stream.current;
    const tracks = stream.current.getVideoTracks();
    const check = () => {
      const ok = tracks.length > 0 && tracks.every((t) => t.readyState === "live" && !t.muted && t.enabled);
      lost.current = !ok;
      setCameraLost(!ok);
      if (!ok && recorder.current?.state === "recording") recorder.current.stop();
    };
    tracks.forEach((t) => { t.addEventListener("ended", check); t.addEventListener("mute", check); t.addEventListener("unmute", check); });
    const id = window.setInterval(check, 1000);
    return () => { tracks.forEach((t) => { t.removeEventListener("ended", check); t.removeEventListener("mute", check); t.removeEventListener("unmute", check); }); clearInterval(id); };
  }, [cameraLost]);

  const turnCameraBackOn = async () => {
    try {
      stream.current.getTracks().forEach((t) => t.stop());
      stream.current = await p.reacquire();
      if (video.current) video.current.srcObject = stream.current;
      lost.current = false;
      setCameraLost(false);
    } catch { setError("We still can't see your camera. Allow it in your browser, then try again."); }
  };

  // ---- one answer ----
  const answer = async (q: number, left: number): Promise<"ok" | "camera"> => {
    const mime = pickMime("video");
    if (!mime) throw new Error("This browser can't record video. Please use Chrome, Edge or Safari.");
    const win = answerWindow(elapsedNow(), left, p.limits.maxAnswer, p.limits.minAnswer);
    setAnsWindow(win); setAnsElapsed(0); setPhase("answering"); setCaption(lineFor(`q${q}`).text); // the question stays on screen while they answer
    const take = await must(guest.POST("/v1/interview/{token}/takes", { params: { path: { token: p.token } }, body: { question_index: q, kind: "video", mime } }));
    await store.setMeta({ takeId: take.id, question: q, kind: "video", mime });
    const up = new TakeUploader(p.token, take.id, store, () => undefined);
    const chunks: Blob[] = [];
    const rec = new MediaRecorder(stream.current, { mimeType: mime, videoBitsPerSecond: 1_200_000, audioBitsPerSecond: 96_000 });
    recorder.current = rec;
    let n = 0;
    rec.ondataavailable = (e) => { if (e.data.size > 0) { const i = n++; chunks[i] = e.data; void up.add(i, e.data); } };
    const stopped = new Promise<void>((r) => { rec.onstop = () => r(); });
    rec.start(CHUNK_MS);
    const started = Date.now();
    let snapped = false;
    const tick = window.setInterval(async () => {
      const s = (Date.now() - started) / 1000;
      setAnsElapsed(s);
      setElapsed(elapsedNow());
      if (!snapped && s >= Math.min(6, win / 2) && video.current) { // a still from the middle of the answer
        snapped = true;
        const b = await grabFrame(video.current);
        if (b) void uploadSnapshot(p.token, take.id, b).catch(() => undefined);
      }
      if ((s >= win || elapsedNow() >= MAX_TOTAL_S + 30) && rec.state === "recording") rec.stop();
    }, 250);
    doneNow.current = () => { if (rec.state === "recording" && Date.now() - started > (FAST ? 0 : 3000)) rec.stop(); };
    await stopped;
    window.clearInterval(tick);
    doneNow.current = null;
    recorder.current = null;
    if (ctl.current.aborted) { // the person stopped the interview: nothing half-finished is kept
      up.dispose();
      await guest.DELETE("/v1/interview/{token}/takes/{take_id}", { params: { path: { token: p.token, take_id: take.id } } }).catch(() => undefined);
      await store.deleteTake(take.id);
      return "ok";
    }
    if (lost.current) { // the camera went off mid-answer: this recording is dropped and the question is asked again
      up.dispose();
      await guest.DELETE("/v1/interview/{token}/takes/{take_id}", { params: { path: { token: p.token, take_id: take.id } } }).catch(() => undefined);
      await store.deleteTake(take.id);
      return "camera";
    }
    setTake(q, { takeId: take.id, status: "uploading", messages: [] });
    void finishTake(q, take.id, up, chunks.length);
    return "ok";
  };

  // upload, then wait for the server to check the recording, without holding up the next question
  const finishTake = async (q: number, takeId: string, up: TakeUploader, count: number) => {
    try {
      await up.drained(count);
      await must(guest.POST("/v1/interview/{token}/takes/{take_id}/complete", { params: { path: { token: p.token, take_id: takeId } }, body: { chunk_count: count } }));
      setTake(q, { takeId, status: "processing", messages: [] });
      for (let i = 0; i < 240 && !ctl.current.aborted; i++) {
        const t = await must(guest.GET("/v1/interview/{token}/takes/{take_id}", { params: { path: { token: p.token, take_id: takeId } } }));
        if (t.status === "ready") { await up.clearLocal(); setTake(q, { takeId, status: "ready", messages: [] }); return; }
        if (t.status === "needs_retake") { await up.clearLocal(); setTake(q, { takeId, status: "needs_retake", messages: t.messages }); return; }
        if (t.status === "failed") { setTake(q, { takeId, status: "failed", messages: t.messages.length ? t.messages : ["We couldn't process that recording."] }); return; }
        await sleep(1200);
      }
      setTake(q, { takeId, status: "failed", messages: ["That took too long to process."] });
    } catch (e) {
      setTake(q, { takeId, status: "failed", messages: [(e as Error).message] });
    } finally {
      up.dispose();
    }
  };

  // ---- after the last question: wait for the checks, sort out any flagged answers, then submit ----
  const finish = async () => {
    setPhase("finishing");
    setCaption("Checking your answers…");
    for (;;) {
      while (!ctl.current.aborted && p.indices.some((q) => ["uploading", "processing", undefined].includes(takesRef.current[q]?.status))) await sleep(500);
      if (ctl.current.aborted) return;
      const bad = p.indices.filter((q) => ["needs_retake", "failed"].includes(takesRef.current[q]?.status ?? ""));
      if (bad.length) {
        setNeedsAttention(bad); setPhase("attention"); setCaption("");
        const choice = await new Promise<{ q: number } | "keep">((res) => {
          redo.current = (q) => res({ q });
          keepAll.current = () => res("keep");
        });
        setNeedsAttention([]);
        if (choice !== "keep") {
          setError(null);
          await say(`q${choice.q}`);
          for (;;) { const r = await answer(choice.q, 1); if (r === "ok") break; await waitCamera(); }
          setPhase("finishing");
          continue;
        }
        // "use it anyway": the server still accepts a flagged answer
        for (const q of bad) if (takesRef.current[q]?.status === "failed") setError("One answer couldn't be processed. Please record it again.");
        if (p.indices.some((q) => takesRef.current[q]?.status === "failed")) continue;
      }
      break;
    }
    try {
      await must(guest.POST("/v1/interview/{token}/submit", { params: { path: { token: p.token } } }));
      setPhase("done");
      p.onFinished();
    } catch (e) {
      setError((e as Error).message);
      setPhase("attention");
    }
  };
  const waitCamera = async () => { while (lost.current && !ctl.current.aborted) await sleep(300); };

  // ---- the interview itself ----
  useEffect(() => {
    const c = { aborted: false };
    ctl.current = c;
    const start = window.setTimeout(async () => {
      try {
        t0.current = Date.now();
        const clock = window.setInterval(() => { const e = elapsedNow(); setElapsed(e); setOvertime(e > MAX_TOTAL_S); }, 500);
        const q0 = lineFor("greeting");
        if (p.intro && q0.text) { setPhase("greeting"); await say("greeting"); }
        for (let n = 0; n < p.indices.length && !c.aborted; n++) {
          const q = p.indices[n];
          setPos(n);
          for (;;) {
            await waitCamera();
            if (c.aborted) return;
            setPhase("asking");
            await say(`q${q}`);
            const r = await answer(q, p.indices.length - n);
            if (r === "ok") break;
          }
          if (n < p.indices.length - 1) { setPhase("between"); await say("thanks", false); }
        }
        if (c.aborted) return;
        setPhase("closing");
        if (p.intro) await say("closing");
        window.clearInterval(clock);
        await finish();
      } catch (e) {
        setError((e as Error).message);
        setPhase("attention");
      }
    }, 0);
    return () => { c.aborted = true; clearTimeout(start); speakingNow.current?.cancel(); if (recorder.current?.state === "recording") recorder.current.stop(); };
  }, []);

  const remaining = MAX_TOTAL_S - elapsed;
  const ansLeft = Math.max(0, ansWindow - ansElapsed);
  const total = p.indices.length;
  const status =
    phase === "answering" ? "Your turn: answer now"
    : phase === "greeting" || phase === "asking" || phase === "closing" ? "The interviewer is speaking…"
    : phase === "finishing" ? "Checking your answers…" : phase === "between" ? "Thank you" : "";

  return (
    <div className="fixed inset-0 z-50 flex flex-col bg-ink text-white md:flex-row" role="dialog" aria-modal="true" aria-label="AI interview">
      <section className="relative min-h-0 flex-1 bg-black">
        <video ref={video} autoPlay muted playsInline className="h-full w-full object-cover [transform:scaleX(-1)]" aria-label="Your camera" />
        <div className="absolute left-3 top-3 flex items-center gap-2 rounded-sm bg-ink px-3 py-1.5 text-sm font-bold">
          {phase === "answering" ? <><span className="inline-block h-3 w-3 animate-pulse rounded-full bg-brand-red" aria-hidden /> Recording {mmss(ansElapsed)}</> : <><span className="inline-block h-3 w-3 rounded-full bg-brand-green" aria-hidden /> Camera on</>}
        </div>
        <div className={`absolute right-3 top-3 rounded-sm px-3 py-1.5 font-mono text-sm font-bold ${overtime ? "bg-brand-red text-ink" : "bg-ink text-brand-green"}`} aria-label="Time left in the interview">
          {overtime ? "Time's up" : `${mmss(remaining)} left`}
        </div>
        {phase === "answering" && (
          <div className="absolute inset-x-0 bottom-0 h-2 bg-ink" role="progressbar" aria-label="Time left for this answer" aria-valuemin={0} aria-valuemax={ansWindow} aria-valuenow={Math.round(ansLeft)}>
            <div className="h-full bg-brand-green transition-[width] duration-300" style={{ width: `${ansWindow ? (ansLeft / ansWindow) * 100 : 0}%` }} />
          </div>
        )}
        {cameraLost && (
          <div className="absolute inset-0 flex flex-col items-center justify-center gap-4 bg-ink/95 p-6 text-center" role="alert">
            <h2 className="font-mono text-2xl font-bold text-white">Your camera is off</h2>
            <p className="max-w-sm">This interview needs your camera. Turn it back on and we’ll ask the question again.</p>
            <button type="button" onClick={turnCameraBackOn} className="rounded-sm border-2 border-ink bg-brand-green px-5 py-3 font-bold text-ink">Turn my camera on</button>
            {error && <p className="text-brand-peach">{error}</p>}
          </div>
        )}
      </section>

      <aside className="flex w-full flex-col gap-4 border-t-8 border-brand-green bg-ink p-5 md:w-[26rem] md:border-l-8 md:border-t-0" aria-live="polite">
        <div className="flex items-center gap-3">
          <span className="text-brand-green"><CFSymbol className="h-10 w-auto" title="Cover Founder interviewer" /></span>
          <div>
            <p className="font-mono text-sm font-bold uppercase tracking-widest text-brand-green">AI interviewer</p>
            <p className="text-sm text-white">{status}</p>
          </div>
        </div>
        <VoiceWave speaking={speaking} />
        {phase !== "attention" && phase !== "done" && (
          <p className="font-mono text-xs font-bold uppercase tracking-widest text-brand-green">
            {phase === "greeting" || phase === "starting" ? `${total} question${total === 1 ? "" : "s"}` : `Question ${Math.min(pos + 1, total)} of ${total}`}
          </p>
        )}
        <p className="min-h-[6rem] font-mono text-xl font-bold leading-snug text-white md:text-2xl" data-testid="caption">{caption}</p>

        {phase === "answering" && (
          <div className="mt-auto space-y-2">
            <p className="text-sm text-white">Answer in your own words. You have up to {mmss(ansWindow)}.</p>
            <button type="button" onClick={() => doneNow.current?.()} className="w-full rounded-sm border-2 border-ink bg-brand-green px-5 py-4 text-lg font-bold text-ink">I’m done answering</button>
          </div>
        )}
        {phase === "finishing" && <p className="mt-auto text-sm text-white" aria-busy="true">Hold on while we check your recordings. This takes a moment.</p>}
        {phase === "attention" && (
          <div className="space-y-3">
            {needsAttention.map((q) => (
              <div key={q} className="rounded-sm border-2 border-brand-peach bg-peach-tint p-3 text-sm text-ink">
                <p className="font-bold">Question {p.indices.indexOf(q) + 1}: {p.questions[q]}</p>
                <p className="mt-1">{takes[q]?.messages.join(" ") || "Please record this answer again."}</p>
                <div className="mt-2 flex gap-2">
                  <button type="button" className="rounded-sm border-2 border-ink bg-brand-green px-3 py-2 font-bold" onClick={() => redo.current?.(q)}>Record it again</button>
                  {takes[q]?.status === "needs_retake" && <button type="button" className="rounded-sm border-2 border-ink bg-white px-3 py-2 font-bold" onClick={() => keepAll.current?.()}>Use it anyway</button>}
                </div>
              </div>
            ))}
            {error && <p role="alert" className="rounded-sm border-2 border-brand-red bg-red-tint p-3 text-sm text-ink">{error}</p>}
          </div>
        )}
        <button
          type="button"
          className="mt-auto self-start text-sm font-bold text-white underline"
          onClick={() => { if (confirm("Stop the interview? Your answers so far are kept.")) { ctl.current.aborted = true; speakingNow.current?.cancel(); p.onCancel(); } }}
        >
          Stop the interview
        </button>
      </aside>
    </div>
  );
}
