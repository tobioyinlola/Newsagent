// Real end-to-end check of the renderer service: POST /renders -> poll -> output on disk -> POST /analyze.
// Uses a stand-in anchor clip (public/bench-anchor.webm, made by ffmpeg) served over HTTP like a presigned URL.
import fs from "node:fs";
import http from "node:http";
import os from "node:os";
import path from "node:path";
import { AddressInfo } from "node:net";
import { createApp } from "./server/app";

const SECONDS = Number(process.env.SMOKE_SECONDS || 5);
const out = fs.mkdtempSync(path.join(os.tmpdir(), "smoke-out-"));
process.env.LOCAL_OUTPUT_DIR = out;

// Serves the anchor and the rendered outputs, standing in for object storage presigned URLs.
const files = http.createServer((req, res) => {
  const p = req.url!.startsWith("/anchor") ? "public/bench-anchor.webm" : path.join(out, decodeURIComponent(req.url!));
  fs.existsSync(p) ? fs.createReadStream(p).pipe(res) : (res.statusCode = 404, res.end());
}).listen(0);
const filesBase = `http://127.0.0.1:${(files.address() as AddressInfo).port}`;

const api = createApp({ secret: "smoke" }).listen(0);
const base = `http://127.0.0.1:${(api.address() as AddressInfo).port}`;
const h = { "x-renderer-secret": "smoke", "content-type": "application/json" };

const outputs = [
  { kind: "video", format: "16x9", name: "preview", scale: 0.5, width: 1920, height: 1080 },
  { kind: "video", format: "9x16", width: 1080, height: 1920 },
  { kind: "thumbnail", format: "16x9", name: "thumbnail", width: 1920, height: 1080 },
];
const t0 = Date.now();
const { render_id } = await (await fetch(`${base}/renders`, { method: "POST", headers: h, body: JSON.stringify({
  composition: "NewsStudio", output_prefix: "projects/smoke/final", outputs, input_urls: { anchor: `${filesBase}/anchor` },
  props: { anchorDurationSeconds: SECONDS, tickerLines: ["FEATURED: Smoke test"], lowerThirds: [{ title: "Smoke", subtitle: "Featured startup" }] } }) })).json();
let st: any;
for (;;) {
  st = await (await fetch(`${base}/renders/${render_id}`, { headers: h })).json();
  if (st.status === "succeeded" || st.status === "failed") break;
  await new Promise((r) => setTimeout(r, 1000));
}
if (st.status !== "succeeded") throw new Error(`render failed: ${st.error}`);
console.log("rendered", st.output_keys, `${((Date.now() - t0) / 1000).toFixed(0)}s`);

const results: Record<string, any> = {};
for (const key of st.output_keys.filter((k: string) => k.endsWith(".mp4"))) {
  const a = await (await fetch(`${base}/analyze`, { method: "POST", headers: h, body: JSON.stringify({ url: `${filesBase}/${key}` }) })).json();
  results[key] = a;
  console.log(key, JSON.stringify(a));
}
const problems: string[] = [];
for (const [k, a] of Object.entries<any>(results)) {
  if (Math.abs(a.duration_s - SECONDS) > 0.5) problems.push(`${k}: duration ${a.duration_s}`);
  if (!a.has_audio) problems.push(`${k}: no audio`);
  if (!k.includes("preview") && (a.loudness_lufs < -18 || a.loudness_lufs > -14)) problems.push(`${k}: loudness ${a.loudness_lufs}`);
  if (a.true_peak_db > -0.1) problems.push(`${k}: clipping`);
}
const thumb = path.join(out, "projects/smoke/final/thumbnail.png");
if (!fs.existsSync(thumb) || fs.statSync(thumb).size < 1000) problems.push("thumbnail missing");
api.close(); files.close();
if (problems.length) { console.error("SMOKE FAILED", problems); process.exit(1); }
console.log("SMOKE OK");
process.exit(0);
