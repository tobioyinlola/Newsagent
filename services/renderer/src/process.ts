import { execFile } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { promisify } from "node:util";
import { analyzeFile } from "./media";

const run = promisify(execFile);
const BUF = { maxBuffer: 128 * 1024 * 1024 };
const MAX_TOTAL_BYTES = 300 * 1024 * 1024;
const PAD_S = 0.3;

export type Flag = "no_speech" | "clipped_audio" | "dark_video" | "too_short";
export type ProcessResult = {
  video_path: string | null;
  audio_path: string;
  duration_s: number;
  width: number | null;
  height: number | null;
  flags: Flag[];
  stats: { mean_volume_db: number | null; max_volume_db: number | null; brightness: number | null; speech_s: number };
};

// Chunks from MediaRecorder concatenate byte-for-byte into one valid stream (each chunk continues the previous).
export async function downloadChunks(urls: string[], dest: string): Promise<void> {
  let total = 0;
  const out = fs.createWriteStream(dest);
  try {
    for (const u of urls) {
      const res = await fetch(u);
      if (!res.ok) throw new Error(`chunk download failed: ${res.status}`);
      const buf = Buffer.from(await res.arrayBuffer());
      total += buf.length;
      if (total > MAX_TOTAL_BYTES) throw new Error("recording too large");
      if (!out.write(buf)) await new Promise<void>((r) => out.once("drain", () => r()));
    }
  } finally {
    await new Promise<void>((r) => out.end(() => r()));
  }
}

type Silence = { start: number; end: number | null };

export function parseSilences(stderr: string): Silence[] {
  const out: Silence[] = [];
  for (const line of stderr.split("\n")) {
    const s = /silence_start: (-?[\d.]+)/.exec(line);
    if (s) out.push({ start: Math.max(0, Number(s[1])), end: null });
    const e = /silence_end: (-?[\d.]+)/.exec(line);
    if (e && out.length) out[out.length - 1].end = Number(e[1]);
  }
  return out;
}

// Work out where speech starts and ends (trimming leading/trailing silence) and how much speech there is.
export function speechWindow(silences: Silence[], total: number): { start: number; end: number; speech_s: number } {
  let start = 0;
  let end = total;
  if (silences.length && silences[0].start <= 0.05 && silences[0].end !== null) start = silences[0].end;
  const last = silences[silences.length - 1];
  // silence that runs to the end of the file (ffmpeg reports its end as the file duration)
  if (last && (last.end === null || last.end >= total - 0.2) && last.start > start) end = last.start;
  let silent = 0;
  for (const s of silences) silent += Math.max(0, Math.min(s.end ?? total, total) - s.start);
  return { start: Math.max(0, start - PAD_S), end: Math.min(total, end + PAD_S), speech_s: Math.max(0, total - silent) };
}

async function analyzeAudio(file: string) {
  const { stderr } = await run("ffmpeg", ["-nostats", "-i", file, "-vn", "-af", "silencedetect=noise=-38dB:d=0.7,volumedetect", "-f", "null", "-"], BUF);
  const mean = /mean_volume: (-?[\d.]+) dB/.exec(stderr)?.[1];
  const max = /max_volume: (-?[\d.]+) dB/.exec(stderr)?.[1];
  const times = [...stderr.matchAll(/time=(\d+):(\d+):([\d.]+)/g)].pop();
  const decoded = times ? Number(times[1]) * 3600 + Number(times[2]) * 60 + Number(times[3]) : 0;
  return { silences: parseSilences(stderr), mean: mean ? Number(mean) : null, max: max ? Number(max) : null, decoded };
}

async function brightness(file: string): Promise<number | null> {
  try {
    const { stderr } = await run("ffmpeg", ["-nostats", "-i", file, "-an", "-vf", "fps=2,signalstats,metadata=print:key=lavfi.signalstats.YAVG", "-f", "null", "-"], BUF);
    const vals = [...stderr.matchAll(/YAVG=([\d.]+)/g)].map((m) => Number(m[1]));
    return vals.length ? vals.reduce((a, b) => a + b, 0) / vals.length : null;
  } catch {
    return null;
  }
}

export async function processTake(opts: { chunkUrls: string[]; kind: "video" | "audio"; ext: string }): Promise<ProcessResult & { dir: string }> {
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "take-"));
  const raw = path.join(dir, `raw.${opts.ext.replace(/[^a-z0-9]/gi, "")}`);
  await downloadChunks(opts.chunkUrls, raw);
  const audio = await analyzeAudio(raw);
  const probe = await analyzeFile(raw).catch(() => null);
  const total = audio.decoded || probe?.duration_s || 0;
  const win = speechWindow(audio.silences, total);
  const dark = opts.kind === "video" ? await brightness(raw) : null;

  const flags: Flag[] = [];
  if (win.speech_s < 1.0 || (audio.mean !== null && audio.mean < -50)) flags.push("no_speech");
  if (audio.max !== null && audio.max >= -0.1) flags.push("clipped_audio");
  if (dark !== null && dark < 25) flags.push("dark_video");
  if (win.end - win.start < 2) flags.push("too_short");

  // Clean-up chain: remove rumble, denoise, then loudness-normalise to -16 LUFS. Trim applies to audio AND video.
  const af = "highpass=f=80,afftdn=nf=-30,loudnorm=I=-16:TP=-1.5:LRA=11";
  const trim = ["-ss", win.start.toFixed(2), "-to", win.end.toFixed(2)];
  const videoPath = opts.kind === "video" ? path.join(dir, "answer.mp4") : null;
  if (videoPath) {
    await run("ffmpeg", ["-y", "-i", raw, ...trim, "-af", af, "-vf", "scale='min(1280,iw)':-2,format=yuv420p", "-r", "30", "-c:v", "libx264", "-preset", "veryfast", "-crf", "23", "-c:a", "aac", "-b:a", "128k", "-ar", "48000", "-movflags", "+faststart", videoPath], BUF);
  }
  // Audio-only copy for transcription (small, mono) - and the answer itself for audio-only takes.
  const audioPath = path.join(dir, "answer.mp3");
  await run("ffmpeg", ["-y", "-i", raw, ...trim, "-vn", "-af", af, "-ac", "1", "-ar", "16000", "-b:a", "64k", audioPath], BUF);

  const outInfo = await analyzeFile(videoPath ?? audioPath);
  return {
    dir, video_path: videoPath, audio_path: audioPath,
    duration_s: outInfo.duration_s, width: outInfo.width, height: outInfo.height, flags,
    stats: { mean_volume_db: audio.mean, max_volume_db: audio.max, brightness: dark, speech_s: Number(win.speech_s.toFixed(2)) },
  };
}
