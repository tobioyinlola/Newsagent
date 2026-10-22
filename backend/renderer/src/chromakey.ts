import { execFile } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import path from "node:path";
import { promisify } from "node:util";
import { analyzeFile } from "./media";
import { assertAllowedUrl } from "./urlguard";

const run = promisify(execFile);
const MAX_BYTES = 800 * 1024 * 1024;

// Turn a green-screen avatar video into a transparent WebM (VP9 + alpha), the same shape the compositions expect
// from a matted anchor. This is what lets a green-screen provider (e.g. Synthesia) stand in for HeyGen.
export async function chromaKey(opts: { url: string; color?: string; similarity?: number; blend?: number }) {
  const color = /^0x[0-9a-f]{6}$/i.test(opts.color ?? "") ? opts.color! : "0x00FF00";
  const similarity = Math.min(Math.max(opts.similarity ?? 0.28, 0.01), 0.6);
  const blend = Math.min(Math.max(opts.blend ?? 0.08, 0), 0.5);
  assertAllowedUrl(opts.url);
  const res = await fetch(opts.url);
  if (!res.ok) throw new Error(`download failed: ${res.status}`);
  const buf = Buffer.from(await res.arrayBuffer());
  if (buf.length > MAX_BYTES) throw new Error("file too large");
  const dir = fs.mkdtempSync(path.join(os.tmpdir(), "key-"));
  const input = path.join(dir, "in.mp4");
  const output = path.join(dir, "out.webm");
  fs.writeFileSync(input, buf);
  // colorkey, then despill the green fringe left on edges, then encode with alpha
  await run("ffmpeg", ["-y", "-i", input, "-vf", `colorkey=${color}:${similarity}:${blend},despill=type=green,format=yuva420p`, "-c:v", "libvpx-vp9", "-pix_fmt", "yuva420p", "-auto-alt-ref", "0", "-b:v", "2M", "-c:a", "libopus", output], { maxBuffer: 64 * 1024 * 1024 });
  const info = await analyzeFile(output);
  return { dir, path: output, duration_s: info.duration_s, width: info.width, height: info.height };
}
