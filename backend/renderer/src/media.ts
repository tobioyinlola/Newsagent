import { execFile } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { assertAllowedUrl } from "./urlguard";
import { promisify } from "node:util";

const run = promisify(execFile);
const MAX_BYTES = 1024 ** 3; // 1 GB cap on anything we download for analysis

export type Analysis = {
  duration_s: number;
  video_duration_s: number | null;
  audio_duration_s: number | null;
  width: number | null;
  height: number | null;
  has_audio: boolean;
  loudness_lufs: number | null;
  true_peak_db: number | null;
};

export async function analyzeFile(file: string): Promise<Analysis> {
  const probe = JSON.parse((await run("ffprobe", ["-v", "error", "-show_streams", "-show_format", "-of", "json", file])).stdout);
  const v = probe.streams.find((s: any) => s.codec_type === "video");
  const a = probe.streams.find((s: any) => s.codec_type === "audio");
  const num = (x: any) => (x === undefined || x === "N/A" ? null : Number(x));
  let loudness: number | null = null;
  let peak: number | null = null;
  if (a) {
    // EBU R128 measurement; the summary is printed on stderr.
    const { stderr } = await run("ffmpeg", ["-nostats", "-i", file, "-vn", "-af", "ebur128=peak=true", "-f", "null", "-"], { maxBuffer: 64 * 1024 * 1024 });
    const summary = stderr.slice(stderr.lastIndexOf("Summary:"));
    loudness = num(/I:\s+(-?[\d.]+) LUFS/.exec(summary)?.[1]);
    peak = num(/Peak:\s+(-?[\d.]+) dBFS/.exec(summary)?.[1]);
  }
  return {
    duration_s: Number(probe.format.duration),
    video_duration_s: num(v?.duration),
    audio_duration_s: num(a?.duration),
    width: v?.width ?? null,
    height: v?.height ?? null,
    has_audio: !!a,
    loudness_lufs: loudness,
    true_peak_db: peak,
  };
}

// Broadcast-style loudness (-16 LUFS, -1.5 dBTP). Video is stream-copied, so this is fast.
export async function normalizeAudio(file: string): Promise<void> {
  const tmp = `${file}.norm.mp4`;
  await run("ffmpeg", ["-y", "-i", file, "-c:v", "copy", "-af", "loudnorm=I=-16:TP=-1.5:LRA=11", "-c:a", "aac", "-b:a", "192k", tmp], { maxBuffer: 64 * 1024 * 1024 });
  fs.renameSync(tmp, file);
}

// The "light" download: the same video and sound, re-encoded for a much smaller file. Same picture size and frame rate; a
// constant-quality encode (CRF 24, slow preset) with a bitrate ceiling, which keeps a talking-head broadcast looking the same
// to the eye at a fraction of the bytes. Made from the finished HD file (already loudness-normalised), never from a new render.
export async function makeLight(input: string, output: string): Promise<void> {
  await run("ffmpeg", ["-y", "-i", input, "-c:v", "libx264", "-preset", "slow", "-profile:v", "high", "-crf", "24", "-maxrate", "4M", "-bufsize", "8M", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "128k", "-movflags", "+faststart", output], { maxBuffer: 64 * 1024 * 1024 });
}

export async function analyzeUrl(url: string): Promise<Analysis> {
  assertAllowedUrl(url);
  const res = await fetch(url);
  if (!res.ok || !res.body) throw new Error(`download failed: ${res.status}`);
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "analyze-"));
  const file = path.join(dir, "media");
  try {
    let n = 0;
    const out = fs.createWriteStream(file);
    for await (const chunk of res.body as any) {
      n += chunk.length;
      if (n > MAX_BYTES) throw new Error("file too large");
      if (!out.write(chunk)) await new Promise<void>((r) => out.once("drain", () => r()));
    }
    await new Promise<void>((r) => out.end(() => r()));
    return await analyzeFile(file);
  } finally {
    fs.rmSync(dir, { recursive: true, force: true });
  }
}
