// Load test: N concurrent renders against the real service. Usage:
//   pnpm loadtest <jobs> <seconds> <jobConcurrency> [maxQueue]
// Reports queue wait, render time, wall time, throughput, peak memory, errors and 429s. Needs scripts/make-standin-anchor.sh.
import { execSync } from "node:child_process";
import fs from "node:fs";
import http from "node:http";
import os from "node:os";
import path from "node:path";
import { AddressInfo } from "node:net";
import { createApp } from "./server/app";
import { getBundle } from "./render";

const [jobs, seconds, conc, maxQueue] = [Number(process.argv[2] || 6), Number(process.argv[3] || 5), Number(process.argv[4] || 1), Number(process.argv[5] || 50)];
const out = fs.mkdtempSync(path.join(os.tmpdir(), "load-out-"));
process.env.LOCAL_OUTPUT_DIR = out;

const files = http.createServer((_q, res) => fs.createReadStream("public/bench-anchor.webm").pipe(res)).listen(0);
const anchor = `http://127.0.0.1:${(files.address() as AddressInfo).port}/a.webm`;
const api = createApp({ secret: "load", maxConcurrent: conc, maxQueue }).listen(0);
const base = `http://127.0.0.1:${(api.address() as AddressInfo).port}`;
const h = { "x-renderer-secret": "load", "content-type": "application/json" };

const rss = () => { try { return Number(execSync(`ps -eo rss,comm | grep -E "node|chrom|headless|ffmpeg" | awk '{s+=$1} END {print s}'`).toString().trim()) / 1024; } catch { return 0; } };
let peak = 0;
const sampler = setInterval(() => { peak = Math.max(peak, rss()); }, 500);

await getBundle(); // bundle once so it isn't counted against the first job
const t0 = Date.now();
type R = { submitted: number; done?: number; status?: string; rejected?: boolean; error?: string };
const results: R[] = await Promise.all(Array.from({ length: jobs }, async (_v, i) => {
  const r: R = { submitted: Date.now() - t0 };
  const res = await fetch(`${base}/renders`, { method: "POST", headers: h, body: JSON.stringify({
    composition: "NewsStudio", output_prefix: `load/${i}`, input_urls: { anchor },
    outputs: [{ kind: "video", format: "16x9", width: 1920, height: 1080 }],
    props: { anchorDurationSeconds: seconds, tickerLines: ["LOAD TEST"], lowerThirds: [{ title: `Job ${i}`, subtitle: "Featured" }] } }) });
  if (res.status === 429) { r.rejected = true; return r; }
  const { render_id } = await res.json();
  for (;;) {
    const s = await (await fetch(`${base}/renders/${render_id}`, { headers: h })).json();
    if (s.status === "succeeded" || s.status === "failed") { r.status = s.status; r.error = s.error; r.done = Date.now() - t0; return r; }
    await new Promise((x) => setTimeout(x, 500));
  }
}));
clearInterval(sampler);
const wall = (Date.now() - t0) / 1000;
const done = results.filter((r) => r.status === "succeeded");
const times = done.map((r) => r.done! / 1000).sort((a, b) => a - b);
const pct = (p: number) => times.length ? times[Math.min(times.length - 1, Math.floor(p * times.length))] : null;
console.log(JSON.stringify({
  cpus: os.cpus().length, jobs, videoSeconds: seconds, jobConcurrency: conc, maxQueue,
  succeeded: done.length, failed: results.filter((r) => r.status === "failed").length, rejected429: results.filter((r) => r.rejected).length,
  wallSeconds: Number(wall.toFixed(1)), videosPerMinute: Number((done.length / (wall / 60)).toFixed(2)),
  completionSeconds: { first: pct(0), median: pct(0.5), p90: pct(0.9), last: times[times.length - 1] ?? null },
  peakRssMb: Math.round(peak), errors: [...new Set(results.filter((r) => r.error).map((r) => r.error))],
}, null, 2));
api.close(); files.close();
process.exit(0);
