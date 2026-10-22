import { execFileSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import http from "node:http";
import { AddressInfo } from "node:net";
import { afterAll, describe, expect, it } from "vitest";
import { parseSilences, processTake, speechWindow } from "./process";

const dir = fs.mkdtempSync(path.join(os.tmpdir(), "proc-test-"));
const ff = (args: string[]) => execFileSync("ffmpeg", ["-y", "-loglevel", "error", ...args]);

// A "recording": 2s silence, 4s of tone (stand-in for speech), 2s silence, in WebM like MediaRecorder makes.
function recording(name: string, opts: { color?: string; tone?: boolean; gain?: number } = {}) {
  const f = path.join(dir, name);
  const tone = opts.tone === false ? "anullsrc=r=48000:cl=mono" : "sine=frequency=300:sample_rate=48000";
  ff(["-f", "lavfi", "-i", `color=c=${opts.color ?? "gray"}:s=640x360:r=30:d=8`, "-f", "lavfi", "-i", tone,
    "-af", `volume='if(between(t,2,6),${opts.gain ?? 0.3},0)':eval=frame`, "-t", "8", "-c:v", "libvpx", "-b:v", "500k", "-c:a", "libopus", f]);
  return f;
}

// Split a file into byte chunks served over HTTP, like the presigned chunk URLs.
function serve(file: string, parts = 5) {
  const buf = fs.readFileSync(file);
  const size = Math.ceil(buf.length / parts);
  const chunks = Array.from({ length: parts }, (_, i) => buf.subarray(i * size, (i + 1) * size));
  const server = http.createServer((req, res) => { res.end(chunks[Number(req.url!.slice(1))]); }).listen(0);
  const base = `http://127.0.0.1:${(server.address() as AddressInfo).port}`;
  return { urls: chunks.map((_, i) => `${base}/${i}`), close: () => server.close() };
}
const servers: { close: () => void }[] = [];
afterAll(() => servers.forEach((s) => s.close()));

describe("silence parsing", () => {
  it("finds leading and trailing silence", () => {
    const err = "silence_start: 0.007\nsilence_end: 2.01 | silence_duration: 2.0\nsilence_start: 6.02\nsilence_end: 8.007 | silence_duration: 1.98";
    const w = speechWindow(parseSilences(err), 8);
    expect(w.start).toBeCloseTo(1.71, 1);
    expect(w.end).toBeCloseTo(6.32, 1);
    expect(w.speech_s).toBeCloseTo(4, 0);
  });
});

describe("processTake", () => {
  it("joins chunks, trims silence, normalises loudness and reports no flags for a good take", async () => {
    const s = serve(recording("good.webm"));
    servers.push(s);
    const r = await processTake({ chunkUrls: s.urls, kind: "video", ext: "webm" });
    expect(r.flags).toEqual([]);
    expect(r.duration_s).toBeGreaterThan(3.5);
    expect(r.duration_s).toBeLessThan(5.5); // 8s raw trimmed to ~4.6s
    expect(fs.existsSync(r.video_path!)).toBe(true);
    const loud = execFileSync("ffmpeg", ["-nostats", "-i", r.video_path!, "-af", "ebur128", "-f", "null", "-"], { encoding: "utf8", stdio: ["ignore", "pipe", "pipe"] });
    expect(loud).toBeDefined();
    fs.rmSync(r.dir, { recursive: true, force: true });
  }, 60_000);

  it("flags a silent take as no_speech", async () => {
    const s = serve(recording("silent.webm", { tone: false }));
    servers.push(s);
    const r = await processTake({ chunkUrls: s.urls, kind: "video", ext: "webm" });
    expect(r.flags).toContain("no_speech");
    fs.rmSync(r.dir, { recursive: true, force: true });
  }, 60_000);

  it("flags a black picture as dark_video", async () => {
    const s = serve(recording("dark.webm", { color: "black" }));
    servers.push(s);
    const r = await processTake({ chunkUrls: s.urls, kind: "video", ext: "webm" });
    expect(r.flags).toContain("dark_video");
    fs.rmSync(r.dir, { recursive: true, force: true });
  }, 60_000);

  it("flags clipped audio", async () => {
    const s = serve(recording("clip.webm", { gain: 8 }));
    servers.push(s);
    const r = await processTake({ chunkUrls: s.urls, kind: "video", ext: "webm" });
    expect(r.flags).toContain("clipped_audio");
    fs.rmSync(r.dir, { recursive: true, force: true });
  }, 60_000);

  it("fails clearly when a chunk is missing", async () => {
    await expect(processTake({ chunkUrls: ["http://127.0.0.1:1/x"], kind: "video", ext: "webm" })).rejects.toThrow();
  });
});
