import { ConnectionState, Room, RoomEvent, Track } from "livekit-client";
import { guest } from "../founder/guestApi";
import { type Speaking, type VoiceLine, speak } from "./voice";

// The interview room on LiveKit, when the server has it set up. The page stays in charge of the interview; the interviewer agent
// in the room only supplies the voice. Everything here degrades to the browser's own voice (voice.ts), so a missing LiveKit, a
// slow connection or a stopped agent can never stall an interview.
const TOPIC = "cf.interview";
const READY_MS = 6000; // how long to wait for the agent to say it is there
const enc = new TextEncoder();
const dec = new TextDecoder();

export type Realtime = { say: (line: VoiceLine, onStart?: () => void) => Speaking; close: () => void };

export async function joinRealtime(token: string, stream: MediaStream): Promise<Realtime | null> {
  const { data, response } = await guest.POST("/v1/interview/{token}/realtime", { params: { path: { token } } });
  if (!response.ok || !data) return null; // 404: LiveKit isn't set up here
  const room = new Room({ adaptiveStream: false });
  const waiters = new Map<string, () => void>();
  let agentUp = false;
  const ready = new Promise<void>((res) => {
    room.on(RoomEvent.DataReceived, (payload, _p, _k, topic) => {
      if (topic !== TOPIC) return;
      try {
        const msg = JSON.parse(dec.decode(payload)) as { t: string; key?: string };
        if (msg.t === "ready") { agentUp = true; res(); }
        if ((msg.t === "said" || msg.t === "refused") && msg.key) waiters.get(msg.key)?.();
      } catch { /* not ours */ }
    });
  });
  // the agent's voice is an audio track: play it
  room.on(RoomEvent.TrackSubscribed, (track) => {
    if (track.kind === Track.Kind.Audio) { const el = track.attach(); el.style.display = "none"; document.body.appendChild(el); }
  });
  const close = () => { void room.disconnect(); document.querySelectorAll("audio[data-lk-agent]").forEach((e) => e.remove()); };
  try {
    await room.connect(data.url, data.token);
    await room.startAudio();
    for (const t of stream.getTracks()) await room.localParticipant.publishTrack(t); // the founder is in the room too
    await Promise.race([ready, new Promise<void>((_, rej) => setTimeout(() => rej(new Error("no agent")), READY_MS))]);
  } catch {
    close();
    return null;
  }
  return {
    close,
    say(line, onStart) {
      // ask the agent to speak it; if the agent or the connection goes quiet, the browser speaks it instead
      if (!agentUp || room.state !== ConnectionState.Connected) return speak(line, onStart);
      let fallback: Speaking | null = null;
      let settled = false;
      const done = new Promise<void>((resolve) => {
        const finish = () => { if (!settled) { settled = true; clearTimeout(guard); waiters.delete(line.key); resolve(); } };
        const words = line.text.trim().split(/\s+/).length;
        const guard = setTimeout(() => { if (!settled) { fallback = speak(line, onStart); void fallback.done.then(finish); } }, Math.max(5000, words * 650 + 3000));
        waiters.set(line.key, finish);
        onStart?.();
        void room.localParticipant.publishData(enc.encode(JSON.stringify({ t: "say", key: line.key })), { reliable: true, topic: TOPIC }).catch(() => { fallback = speak(line, onStart); void fallback.done.then(finish); });
      });
      return { done, cancel: () => { settled = true; fallback?.cancel(); waiters.delete(line.key); } };
    },
  };
}
