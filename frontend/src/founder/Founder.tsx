import { useQuery, useQueryClient } from "@tanstack/react-query";
import { type ReactNode, useCallback, useEffect, useRef, useState } from "react";
import { useParams } from "react-router-dom";
import { CHUNK_MS, HARD_CAP_S, type GuestQuestion, type GuestTake, type GuestView, guest, must } from "./guestApi";
import { canRecord, extFor, micLevel, openStream, pickMime } from "./media";
import { ChunkStore } from "./store";
import { type UploadState, TakeUploader } from "./uploader";

const store = new ChunkStore();
const btn = "w-full rounded-xl px-5 py-4 text-lg font-semibold focus:outline-none focus-visible:ring-4 focus-visible:ring-brand-purple disabled:opacity-50";
const primary = `${btn} border-2 border-ink bg-brand-green text-ink active:bg-ink active:text-brand-green`;
const secondary = `${btn} border-2 border-ink bg-white text-ink`;

function Shell({ company, children, onErase }: { company?: string; children: ReactNode; onErase?: () => void }) {
  return (
    <div className="mx-auto flex min-h-screen max-w-md flex-col gap-4 bg-white p-4 text-ink">
      <header>
        <p className="text-xs font-bold uppercase tracking-widest text-ink">Cover Founder</p>
        {company && <h1 className="text-2xl font-extrabold">Interview for {company}</h1>}
      </header>
      <main className="flex flex-1 flex-col gap-4" aria-live="polite">{children}</main>
      <footer className="space-y-2 border-t border-line pt-3 text-xs text-muted">
        <span className="mr-2 rounded bg-brand-peach px-1.5 py-0.5 font-extrabold uppercase text-ink">Featured</span>
        The anchor in this video is AI-generated. Your answers are used only in this video.
        {onErase && <button type="button" className="mt-1 block underline" onClick={onErase}>Delete all of my recordings</button>}
      </footer>
    </div>
  );
}

const Note = ({ tone = "info", children }: { tone?: "info" | "warn" | "ok"; children: ReactNode }) => (
  <p role="status" className={`rounded-lg border p-3 text-base ${{ info: "border-brand-purple bg-lilac", warn: "border-brand-peach bg-peach-tint", ok: "border-ink bg-lime-tint" }[tone]}`}>{children}</p>
);

type Phase = "welcome" | "devices" | "hub" | "answer" | "done";

export default function Founder() {
  const { token = "" } = useParams();
  const qc = useQueryClient();
  const view = useQuery({ queryKey: ["guest", token], queryFn: () => must(guest.GET("/v1/interview/{token}", { params: { path: { token } } })), retry: false, refetchOnWindowFocus: false, refetchOnReconnect: false });
  const [phase, setPhase] = useState<Phase | null>(null);
  const [kind, setKind] = useState<"video" | "audio">("video");
  const [stream, setStream] = useState<MediaStream | null>(null);
  const [qi, setQi] = useState(0);
  const [erased, setErased] = useState(false);
  const refresh = useCallback(() => qc.invalidateQueries({ queryKey: ["guest", token] }), [qc, token]);

  useEffect(() => () => stream?.getTracks().forEach((t) => t.stop()), [stream]);
  useEffect(() => {
    const v = view.data;
    if (!v || phase !== null) return;
    setPhase(v.submitted ? "done" : !v.consented ? "welcome" : "devices");
  }, [view.data, phase]);

  if (erased) return <Shell><Note tone="ok">Your recordings have been permanently deleted. You can close this page.</Note></Shell>;
  if (view.isLoading) return <Shell><p aria-busy="true">Loading…</p></Shell>;
  if (view.error || !view.data) return <Shell><Note tone="warn">This link is no longer valid. Please ask the person who invited you to send a new one.</Note></Shell>;
  const v = view.data;
  if (!canRecord()) {
    return <Shell company={v.company}><Note tone="warn">This browser can't record video. Please open this link in Chrome or Safari (not inside another app such as Instagram or WhatsApp).</Note></Shell>;
  }

  const nextQuestion = (from: number) => {
    const needs = (q: GuestQuestion) => !q.take || ["failed", "recording", "superseded"].includes(q.take.status);
    const i = v.questions.findIndex((q, idx) => idx >= from && needs(q));
    return i;
  };
  const open = (i: number) => { setQi(i); setPhase("answer"); };

  return (
    <Shell
      company={v.company}
      onErase={async () => {
        if (!confirm("Delete all of your recordings and photos? This can't be undone.")) return;
        await guest.DELETE("/v1/interview/{token}/data", { params: { path: { token } } });
        stream?.getTracks().forEach((t) => t.stop());
        setErased(true);
      }}
    >
      {phase === "welcome" && (
        <Welcome name={v.founder_name} text={v.consent_text} onAccept={async () => { await must(guest.POST("/v1/interview/{token}/consent", { params: { path: { token } } })); await refresh(); setPhase("devices"); }} />
      )}
      {phase === "devices" && (
        <Devices token={token} onReady={(s, k) => { setStream(s); setKind(k); const i = nextQuestion(0); if (i >= 0) open(i); else setPhase("hub"); }} />
      )}
      {phase === "hub" && stream && <Hub token={token} view={v} kind={kind} onOpen={open} onSubmitted={() => { void refresh(); setPhase("done"); }} />}
      {phase === "answer" && stream && v.questions[qi] && (
        <Answer
          key={qi}
          token={token} q={v.questions[qi]} total={v.questions.length} stream={stream} kind={kind}
          onFinished={async () => { await refresh(); const fresh = (await qc.fetchQuery({ queryKey: ["guest", token], queryFn: () => must(guest.GET("/v1/interview/{token}", { params: { path: { token } } })) })); const i = fresh.questions.findIndex((q, idx) => idx > qi && (!q.take || ["failed", "recording"].includes(q.take.status))); if (i >= 0) open(i); else setPhase("hub"); }}
          onBack={() => setPhase("hub")}
        />
      )}
      {phase === "done" && <Note tone="ok">Thank you, {v.founder_name || "all done"}! Your answers have been sent. The team will review them and make the final video. You can close this page.</Note>}
    </Shell>
  );
}

function Welcome({ name, text, onAccept }: { name: string; text: string; onAccept: () => Promise<void> }) {
  const [ok, setOk] = useState(false);
  const [busy, setBusy] = useState(false);
  return (
    <>
      <p className="text-lg">Hi {name || "there"}! You've been asked to answer a few questions on camera. It takes about 10 minutes.</p>
      <section className="rounded-lg border border-ink bg-paper p-3 text-base" aria-labelledby="consent-h">
        <h2 id="consent-h" className="mb-1 font-bold">How your recording will be used</h2>
        <p>{text}</p>
      </section>
      <label className="flex items-start gap-3 text-base">
        <input type="checkbox" className="mt-1 h-6 w-6" checked={ok} onChange={(e) => setOk(e.target.checked)} />
        <span>I understand and agree to this.</span>
      </label>
      <button className={primary} disabled={!ok || busy} onClick={async () => { setBusy(true); try { await onAccept(); } finally { setBusy(false); } }}>Continue</button>
    </>
  );
}

function Devices({ token, onReady }: { token: string; onReady: (s: MediaStream, k: "video" | "audio") => void }) {
  const [stream, setStream] = useState<MediaStream | null>(null);
  const [kind, setKind] = useState<"video" | "audio">("video");
  const [level, setLevel] = useState(0);
  const [heardSound, setHeardSound] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [speed, setSpeed] = useState<number | null>(null);
  const video = useRef<HTMLVideoElement>(null);

  const start = async (k: "video" | "audio") => {
    setErr(null);
    try {
      const s = await openStream(k);
      setStream(s); setKind(k);
    } catch (e) {
      const name = (e as DOMException).name;
      if (k === "video") { // no camera or camera blocked: offer sound only
        try { const s = await openStream("audio"); setStream(s); setKind("audio"); setErr("We couldn't use your camera, so we'll record sound only. You can add a photo at the end."); return; } catch { /* fall through */ }
      }
      setErr(name === "NotAllowedError" ? "Permission was blocked. Tap the lock or camera icon in your browser's address bar, allow the camera and microphone, then try again." : "We couldn't find a microphone. Please check your device and try again.");
    }
  };

  useEffect(() => { if (video.current && stream) video.current.srcObject = stream; }, [stream]);
  useEffect(() => {
    if (!stream) return;
    return micLevel(stream, (l) => { setLevel(l); if (l > 0.08) setHeardSound(true); });
  }, [stream]);
  useEffect(() => {
    if (!stream) return;
    let dead = false;
    (async () => { // connection test: upload ~256 KB and time it
      try {
        const slot = await must(guest.POST("/v1/interview/{token}/speedtest", { params: { path: { token } } }));
        const body = new Blob([new Uint8Array(256 * 1024)]);
        const t0 = performance.now();
        const r = await fetch(slot.upload_url, { method: "PUT", body });
        const s = (performance.now() - t0) / 1000;
        if (r.ok && !dead) setSpeed((body.size * 8) / s / 1e6);
        await guest.POST("/v1/interview/{token}/speedtest/done", { params: { path: { token } }, body: { key: slot.key } });
      } catch { if (!dead) setSpeed(0); }
    })();
    return () => { dead = true; };
  }, [stream, token]);

  const slow = speed !== null && speed < 1;
  return (
    <>
      <h2 className="text-xl font-bold">Check your camera and microphone</h2>
      {!stream ? (
        <>
          <p>Tap below and allow camera and microphone access when your browser asks.</p>
          <button className={primary} onClick={() => start("video")}>Turn on camera and microphone</button>
          <button className={secondary} onClick={() => start("audio")}>Use sound only instead</button>
        </>
      ) : (
        <>
          {kind === "video" && (
            <div className="relative overflow-hidden rounded-xl bg-black">
              <video ref={video} autoPlay muted playsInline className="aspect-[3/4] w-full object-cover [transform:scaleX(-1)]" aria-label="Your camera preview" />
              <div aria-hidden className="pointer-events-none absolute inset-0 flex items-center justify-center"><div className="h-3/4 w-1/2 rounded-[50%] border-4 border-dashed border-white/70" /></div>
            </div>
          )}
          <div><p className="mb-1 font-medium">Microphone: {heardSound ? "we can hear you ✓" : "say something…"}</p>
            <div className="h-3 overflow-hidden rounded bg-line" role="meter" aria-valuenow={Math.round(level * 100)} aria-valuemin={0} aria-valuemax={100} aria-label="Microphone level"><div className="h-full bg-brand-green transition-all" style={{ width: `${level * 100}%` }} /></div></div>
          <p>{kind === "video" ? "Keep your face inside the oval, with light on your face and a quiet room." : "Find a quiet room."}</p>
          <p aria-live="polite">Connection: {speed === null ? "testing…" : speed === 0 ? "couldn't test" : `${speed.toFixed(1)} Mbps ${slow ? "(slow)" : "(good)"}`}</p>
          {slow && kind === "video" && <Note tone="warn">Your connection looks slow. Video still works (it saves on your phone while it uploads), but sound-only is faster.</Note>}
          {err && <Note tone="warn">{err}</Note>}
          <button className={primary} onClick={() => onReady(stream, kind)}>Looks good, continue</button>
          {kind === "video" && <button className={secondary} onClick={() => { stream.getTracks().forEach((t) => t.stop()); void start("audio"); }}>Use sound only instead</button>}
        </>
      )}
      {!stream && err && <Note tone="warn">{err}</Note>}
    </>
  );
}

type Sub = "prompt" | "countdown" | "recording" | "review" | "checking" | "flagged" | "failed";

function Answer({ token, q, total, stream, kind, onFinished, onBack }: { token: string; q: GuestQuestion; total: number; stream: MediaStream; kind: "video" | "audio"; onFinished: () => void | Promise<void>; onBack: () => void }) {
  const [sub, setSub] = useState<Sub>("prompt");
  const [count, setCount] = useState(3);
  const [elapsed, setElapsed] = useState(0);
  const [up, setUp] = useState<UploadState | null>(null);
  const [blobUrl, setBlobUrl] = useState<string | null>(null);
  const [error, setError] = useState<string | null>(null);
  const [flag, setFlag] = useState<GuestTake | null>(null);
  const [resumed, setResumed] = useState(false);
  const rec = useRef<MediaRecorder | null>(null);
  const uploader = useRef<TakeUploader | null>(null);
  const takeId = useRef<string | null>(null);
  const chunks = useRef<Blob[]>([]);
  const mimeRef = useRef<string>("");
  const timer = useRef<number>(0);
  const live = useRef<HTMLVideoElement>(null);
  const mime = pickMime(kind);

  useEffect(() => { if (live.current && kind === "video") live.current.srcObject = stream; }, [stream, kind, sub]);
  // Two separate cleanups: stopping the uploader must happen only on unmount, never when the preview URL changes.
  useEffect(() => () => { window.clearInterval(timer.current); uploader.current?.dispose(); }, []);
  useEffect(() => () => { if (blobUrl) URL.revokeObjectURL(blobUrl); }, [blobUrl]);

  // An unfinished recording from before a reload or crash: its chunks are still on this device.
  // Runs once, when this screen opens: later server refreshes must never hijack a recording in progress.
  useEffect(() => {
    const t = q.take;
    if (!t || t.status !== "recording") return;
    (async () => {
      const metas = await store.allMeta();
      const m = metas.find((x) => x.takeId === t.id);
      const idxs = m ? await store.indexes(t.id) : [];
      if (!m || !idxs.length) return;
      takeId.current = t.id; mimeRef.current = m.mime;
      chunks.current = await Promise.all(idxs.map(async (i) => (await store.get(t.id, i)) as Blob));
      const u = new TakeUploader(token, t.id, store, setUp);
      uploader.current = u;
      await u.resume();
      setBlobUrl(URL.createObjectURL(new Blob(chunks.current, { type: m.mime })));
      setResumed(true); setSub("review");
    })().catch(() => undefined);
  }, []);

  const begin = () => {
    setError(null); setSub("countdown"); setCount(3);
    let n = 3;
    const id = window.setInterval(() => { n -= 1; setCount(n); if (n <= 0) { window.clearInterval(id); void startRecording(); } }, 1000);
  };

  const startRecording = async () => {
    try {
      if (!mime) throw new Error("This browser can't record in a supported format.");
      const take = await must(guest.POST("/v1/interview/{token}/takes", { params: { path: { token } }, body: { question_index: q.index, kind, mime } }));
      takeId.current = take.id; mimeRef.current = mime; chunks.current = [];
      await store.setMeta({ takeId: take.id, question: q.index, kind, mime });
      const u = new TakeUploader(token, take.id, store, setUp);
      uploader.current = u;
      const r = new MediaRecorder(stream, { mimeType: mime, videoBitsPerSecond: 1_200_000, audioBitsPerSecond: 96_000 });
      rec.current = r;
      let n = 0;
      r.ondataavailable = (e) => { if (e.data.size > 0) { const i = n++; chunks.current[i] = e.data; void u.add(i, e.data); } };
      r.onstop = () => {
        window.clearInterval(timer.current);
        setBlobUrl(URL.createObjectURL(new Blob(chunks.current, { type: mime })));
        setSub("review");
      };
      r.start(CHUNK_MS);
      setElapsed(0); setSub("recording");
      const t0 = Date.now();
      timer.current = window.setInterval(() => { const s = Math.floor((Date.now() - t0) / 1000); setElapsed(s); if (s >= HARD_CAP_S && r.state === "recording") r.stop(); }, 250);
    } catch (e) {
      setError((e as Error).message); setSub("prompt");
    }
  };

  const stop = () => { if (rec.current?.state === "recording") rec.current.stop(); };

  const discard = async () => {
    uploader.current?.dispose();
    if (takeId.current) await store.deleteTake(takeId.current);
    if (blobUrl) URL.revokeObjectURL(blobUrl);
    setBlobUrl(null); setUp(null); setResumed(false); setFlag(null); setError(null); setSub("prompt");
  };

  const poll = async (id: string) => {
    for (let i = 0; i < 180; i++) {
      const t = await must(guest.GET("/v1/interview/{token}/takes/{take_id}", { params: { path: { token, take_id: id } } }));
      if (t.status === "ready") { await uploader.current?.clearLocal(); await onFinished(); return; }
      if (t.status === "needs_retake") { await uploader.current?.clearLocal(); setFlag(t); setSub("flagged"); return; }
      if (t.status === "failed") { setSub("failed"); return; }
      await new Promise((r) => setTimeout(r, 1500));
    }
    setSub("failed");
  };

  const keep = async () => {
    const u = uploader.current; const id = takeId.current;
    if (!u || !id) return;
    setError(null); setSub("checking");
    try {
      const n = chunks.current.length;
      await u.drained(n, setUp);
      await must(guest.POST("/v1/interview/{token}/takes/{take_id}/complete", { params: { path: { token, take_id: id } }, body: { chunk_count: n } }));
      await poll(id);
    } catch (e) {
      setError((e as Error).message); setSub("review");
    }
  };

  const retryProcessing = async () => {
    if (!takeId.current) return;
    setSub("checking");
    try { await must(guest.POST("/v1/interview/{token}/takes/{take_id}/reprocess", { params: { path: { token, take_id: takeId.current } } })); await poll(takeId.current); } catch (e) { setError((e as Error).message); setSub("failed"); }
  };

  const mm = (s: number) => `${Math.floor(s / 60)}:${String(s % 60).padStart(2, "0")}`;
  const waiting = up && up.pending > 0;

  return (
    <>
      <p className="text-sm font-semibold text-muted">Question {q.index + 1} of {total}</p>
      <h2 className="text-2xl font-bold">{q.text}</h2>

      {sub === "prompt" && (
        <>
          {q.clip_url && <video className="w-full rounded-xl bg-black" src={q.clip_url} controls playsInline aria-label="The anchor asks this question" />}
          <p className="text-muted">Answer in about 30 to 60 seconds. You can record again as many times as you like.</p>
          {q.attempts_left <= 0 && <Note tone="warn">You've used all your takes for this question. Please keep your best one.</Note>}
          {error && <Note tone="warn">{error}</Note>}
          <button className={primary} onClick={begin} disabled={q.attempts_left <= 0}>I'm ready, start recording</button>
          <button className={secondary} onClick={onBack}>Back to all questions</button>
        </>
      )}
      {sub === "countdown" && <p className="py-12 text-center text-8xl font-extrabold text-ink" aria-live="assertive">{count > 0 ? count : "Go"}</p>}
      {sub === "recording" && (
        <>
          {kind === "video" && <video ref={live} autoPlay muted playsInline className="aspect-[3/4] w-full rounded-xl bg-black object-cover [transform:scaleX(-1)]" aria-label="Your camera" />}
          <p className="text-center text-3xl font-bold tabular-nums" aria-live="off"><span className="mr-2 inline-block h-4 w-4 animate-pulse rounded-full bg-brand-red align-middle" aria-hidden />{mm(elapsed)} <span className="text-base font-normal text-muted">/ {mm(HARD_CAP_S)} max</span></p>
          {up && up.pending > 3 && <Note tone="warn">Your connection is slow. Keep going: your answer is saved on this device while it uploads.</Note>}
          <button className={`${btn} bg-brand-red text-white`} onClick={stop}>Stop recording</button>
        </>
      )}
      {sub === "review" && (
        <>
          {resumed && <Note tone="info">We found a recording you hadn't finished. It's saved on this device.</Note>}
          {blobUrl && (kind === "video" ? <video src={blobUrl} controls playsInline className="aspect-[3/4] w-full rounded-xl bg-black object-cover" aria-label="Review your answer" /> : <audio src={blobUrl} controls className="w-full" aria-label="Review your answer" />)}
          <p aria-live="polite" className="text-sm text-muted">{up ? (waiting ? (up.online ? `Uploading… ${up.confirmed} of ${up.confirmed + up.pending} parts sent` : "No connection. Your answer is safe on this device and will send when you're back online.") : "Saved ✓") : ""}</p>
          {error && <Note tone="warn">{error}</Note>}
          <button className={primary} onClick={keep}>Keep this answer</button>
          <button className={secondary} onClick={discard}>Record again</button>
        </>
      )}
      {sub === "checking" && (
        <>
          <p aria-busy="true" className="text-lg">{waiting ? (up!.online ? "Sending your answer…" : "Waiting for your connection to come back…") : "Checking your recording…"}</p>
          {waiting && <p className="text-sm text-muted">{up!.confirmed} of {up!.confirmed + up!.pending} parts sent. Please keep this page open.</p>}
        </>
      )}
      {sub === "flagged" && flag && (
        <>
          <Note tone="warn">{flag.messages.length ? flag.messages.join(" ") : "Please record this answer again."}</Note>
          <button className={primary} onClick={discard}>Record again</button>
          <button className={secondary} onClick={() => void onFinished()}>Use this answer anyway</button>
        </>
      )}
      {sub === "failed" && (
        <>
          <Note tone="warn">We couldn't process that recording. {error}</Note>
          <button className={primary} onClick={retryProcessing}>Try again</button>
          <button className={secondary} onClick={discard}>Record again</button>
        </>
      )}
      <span className="sr-only">{extFor(mimeRef.current || mime || "")}</span>
    </>
  );
}

function Hub({ token, view, kind, onOpen, onSubmitted }: { token: string; view: GuestView; kind: "video" | "audio"; onOpen: (i: number) => void; onSubmitted: () => void }) {
  const [busy, setBusy] = useState(false);
  const [err, setErr] = useState<string | null>(null);
  const [photoOk, setPhotoOk] = useState(view.has_photo);
  const audioTakes = view.questions.some((q) => q.take?.kind === "audio") || kind === "audio";
  const label = (t: GuestTake | null | undefined) => (!t ? "Not answered" : t.status === "ready" ? "Answered ✓" : t.status === "needs_retake" ? "Needs another take" : t.status === "failed" ? "Couldn't process" : "Processing…");

  const upload = async (file: File) => {
    setErr(null); setBusy(true);
    try {
      const ct = file.type;
      const slot = await must(guest.POST("/v1/interview/{token}/photo", { params: { path: { token } }, body: { content_type: ct } }));
      const put = await fetch(slot.upload_url, { method: "PUT", body: file });
      if (!put.ok) throw new Error("The upload didn't go through. Please try again.");
      await must(guest.POST("/v1/interview/{token}/photo/confirm", { params: { path: { token } }, body: { key: slot.key } }));
      setPhotoOk(true);
    } catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  };
  const submit = async () => {
    setBusy(true); setErr(null);
    try { await must(guest.POST("/v1/interview/{token}/submit", { params: { path: { token } } })); onSubmitted(); } catch (e) { setErr((e as Error).message); } finally { setBusy(false); }
  };
  return (
    <>
      <h2 className="text-xl font-bold">Your answers</h2>
      <ul className="divide-y divide-line rounded-lg border border-line">
        {view.questions.map((q) => (
          <li key={q.index} className="flex items-center justify-between gap-3 p-3">
            <div><p className="font-medium">{q.text}</p><p className="text-sm text-muted">{label(q.take)}</p></div>
            <button className="rounded-lg border-2 border-ink px-3 py-2 text-sm font-semibold" onClick={() => onOpen(q.index)}>{q.take ? "Re-record" : "Record"}</button>
          </li>
        ))}
      </ul>
      {audioTakes && (
        <div className="space-y-2"><p className="font-medium">Add a photo of yourself {photoOk && "✓"}</p>
          <p className="text-sm text-muted">Because some answers are sound only, we show a photo of you while your voice plays.</p>
          <input aria-label="Choose a photo" type="file" accept="image/png,image/jpeg" disabled={busy} onChange={(e) => { const f = e.target.files?.[0]; if (f) void upload(f); }} /></div>
      )}
      {err && <Note tone="warn">{err}</Note>}
      <button className={primary} disabled={busy} onClick={submit}>Submit my answers</button>
    </>
  );
}
