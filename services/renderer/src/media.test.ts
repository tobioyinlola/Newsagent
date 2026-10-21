import { execFileSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { describe, expect, it } from "vitest";
import { analyzeFile, normalizeAudio } from "./media";

const dir = fs.mkdtempSync(path.join(os.tmpdir(), "media-test-"));
function make(name: string, audioFilter: string, seconds = 3) {
  const f = path.join(dir, name);
  execFileSync("ffmpeg", ["-y", "-loglevel", "error", "-f", "lavfi", "-i", `color=c=blue:s=320x180:r=30:d=${seconds}`, "-f", "lavfi", "-i", `sine=frequency=440:d=${seconds}`, "-af", audioFilter, "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", f]);
  return f;
}

describe("media analysis", () => {
  it("reports duration, dimensions, audio and loudness", async () => {
    const a = await analyzeFile(make("quiet.mp4", "volume=0.1"));
    expect(a.duration_s).toBeGreaterThan(2.9);
    expect(a).toMatchObject({ width: 320, height: 180, has_audio: true });
    expect(a.loudness_lufs!).toBeLessThan(-20);
  });
  it("normalizes quiet audio to about -16 LUFS without changing duration", async () => {
    const f = make("quiet2.mp4", "volume=0.05", 6);
    await normalizeAudio(f);
    const a = await analyzeFile(f);
    expect(a.loudness_lufs!).toBeGreaterThan(-18);
    expect(a.loudness_lufs!).toBeLessThan(-14);
    expect(a.true_peak_db!).toBeLessThan(0);
    expect(Math.abs(a.duration_s - 6)).toBeLessThan(0.3);
  });
  it("detects a video with no audio", async () => {
    const f = path.join(dir, "silent.mp4");
    execFileSync("ffmpeg", ["-y", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=red:s=160x90:r=30:d=1", "-c:v", "libx264", "-pix_fmt", "yuv420p", f]);
    expect((await analyzeFile(f)).has_audio).toBe(false);
  });
});
