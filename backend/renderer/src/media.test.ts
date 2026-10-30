import { execFileSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { describe, expect, it } from "vitest";
import { analyzeFile, makeLight, normalizeAudio } from "./media";

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
  it("makes a light version that is much smaller with the same length, picture size and sound", async () => {
    const hd = path.join(dir, "hd.mp4");
    // a busy 1280x720 picture encoded at a high bitrate, like a finished HD render
    execFileSync("ffmpeg", ["-y", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc2=s=1280x720:r=30:d=4", "-f", "lavfi", "-i", "sine=frequency=440:d=4", "-c:v", "libx264", "-crf", "12", "-pix_fmt", "yuv420p", "-c:a", "aac", "-b:a", "192k", hd]);
    const light = path.join(dir, "light.mp4");
    await makeLight(hd, light);
    const [a, b] = [await analyzeFile(hd), await analyzeFile(light)];
    expect(fs.statSync(light).size).toBeLessThan(fs.statSync(hd).size * 0.6);
    expect(b).toMatchObject({ width: 1280, height: 720, has_audio: true });
    expect(Math.abs(b.duration_s - a.duration_s)).toBeLessThan(0.2);
  }, 120_000); // a slow-preset x264 encode: about 8 s on a busy machine, so the default 5 s limit made it fail at random
});
