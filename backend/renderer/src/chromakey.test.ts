import { execFileSync } from "node:child_process";
import fs from "node:fs";
import http from "node:http";
import os from "node:os";
import path from "node:path";
import { AddressInfo } from "node:net";
import { afterAll, describe, expect, it } from "vitest";
import { chromaKey } from "./chromakey";

const dir = fs.mkdtempSync(path.join(os.tmpdir(), "key-test-"));
// A green-screen "avatar": a person-shaped block on pure green, like Synthesia's green_screen background.
const src = path.join(dir, "green.mp4");
execFileSync("ffmpeg", ["-y", "-loglevel", "error", "-f", "lavfi", "-i", "color=c=0x00FF00:s=320x360:r=30:d=2,drawbox=x=60:y=150:w=200:h=210:color=0x1c2b4a:t=fill,drawbox=x=120:y=60:w=80:h=95:color=0xd9c2a7:t=fill", "-f", "lavfi", "-i", "sine=frequency=220:d=2", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", src]);
const server = http.createServer((_, res) => res.end(fs.readFileSync(src))).listen(0);
afterAll(() => server.close());
const url = () => `http://127.0.0.1:${(server.address() as AddressInfo).port}/green.mp4`;

function alphaStats(file: string) {
  const raw = execFileSync("ffmpeg", ["-v", "error", "-c:v", "libvpx-vp9", "-i", file, "-frames:v", "1", "-f", "rawvideo", "-pix_fmt", "rgba", "-"], { maxBuffer: 64 * 1024 * 1024 });
  let opaque = 0, clear = 0, greenOpaque = 0;
  for (let i = 0; i < raw.length; i += 4) {
    const a = raw[i + 3];
    if (a > 200) { opaque++; if (raw[i + 1] > 200 && raw[i] < 60 && raw[i + 2] < 60) greenOpaque++; }
    if (a < 20) clear++;
  }
  return { total: raw.length / 4, opaque, clear, greenOpaque };
}

describe("chromaKey", () => {
  it("keys out the green, keeps the person, and leaves no green fringe", async () => {
    const r = await chromaKey({ url: url() });
    const s = alphaStats(r.path);
    expect(s.clear / s.total).toBeGreaterThan(0.5); // the green background became transparent
    expect(s.opaque / s.total).toBeGreaterThan(0.2); // the person stayed
    expect(s.greenOpaque).toBe(0); // no opaque pure-green pixels left
    expect(r.duration_s).toBeGreaterThan(1.8);
    const tags = execFileSync("ffprobe", ["-v", "error", "-select_streams", "v", "-show_entries", "stream_tags=alpha_mode", "-of", "csv=p=0", r.path], { encoding: "utf8" });
    expect(tags.trim()).toContain("1"); // flagged as having alpha
    fs.rmSync(r.dir, { recursive: true, force: true });
  }, 60_000);
  it("rejects non-http urls and bad downloads", async () => {
    await expect(chromaKey({ url: "file:///etc/passwd" })).rejects.toThrow();
    await expect(chromaKey({ url: "http://127.0.0.1:1/x" })).rejects.toThrow();
  });
});
