// Pick a MediaRecorder format this browser can actually produce. Chrome/Firefox/Android: WebM. Safari (incl. iOS): MP4.
const VIDEO = ["video/webm;codecs=vp9,opus", "video/webm;codecs=vp8,opus", "video/webm", "video/mp4;codecs=avc1,mp4a.40.2", "video/mp4"];
const AUDIO = ["audio/webm;codecs=opus", "audio/webm", "audio/mp4", "audio/ogg;codecs=opus"];

export function pickMime(kind: "video" | "audio"): string | null {
  if (typeof MediaRecorder === "undefined") return null;
  const list = kind === "video" ? VIDEO : AUDIO;
  return list.find((m) => MediaRecorder.isTypeSupported(m)) ?? null;
}

export const canRecord = () => typeof MediaRecorder !== "undefined" && !!navigator.mediaDevices?.getUserMedia;

export async function openStream(kind: "video" | "audio"): Promise<MediaStream> {
  return navigator.mediaDevices.getUserMedia({
    audio: { echoCancellation: true, noiseSuppression: true, autoGainControl: true },
    video: kind === "video" ? { facingMode: "user", width: { ideal: 1280 }, height: { ideal: 720 } } : false,
  });
}

// Live microphone level 0..1 for the device check.
export function micLevel(stream: MediaStream, onLevel: (v: number) => void): () => void {
  const Ctx = window.AudioContext ?? (window as unknown as { webkitAudioContext: typeof AudioContext }).webkitAudioContext;
  if (!Ctx || !stream.getAudioTracks().length) return () => undefined;
  const ctx = new Ctx();
  const analyser = ctx.createAnalyser();
  analyser.fftSize = 512;
  ctx.createMediaStreamSource(stream).connect(analyser);
  const data = new Uint8Array(analyser.fftSize);
  let raf = 0;
  const tick = () => {
    analyser.getByteTimeDomainData(data);
    let peak = 0;
    for (const v of data) peak = Math.max(peak, Math.abs(v - 128) / 128);
    onLevel(Math.min(1, peak * 2));
    raf = requestAnimationFrame(tick);
  };
  tick();
  return () => { cancelAnimationFrame(raf); void ctx.close(); };
}

export const extFor = (mime: string) => (mime.includes("mp4") ? "mp4" : mime.includes("ogg") ? "ogg" : "webm");
