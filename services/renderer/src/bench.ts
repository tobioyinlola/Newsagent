// Usage: pnpm bench [seconds] ; renders both formats and prints timing + peak RSS (renderer + children).
import { execSync } from "node:child_process";
import fs from "node:fs";
import os from "node:os";
import { defaultProps } from "./compositions/types";
import { getBundle, renderOne } from "./render";

const seconds = Number(process.argv[2] || 30);
const withAnchor = process.argv[3] !== "noanchor";
fs.mkdirSync("out", { recursive: true });

function rssMb(): number {
  try {
    const kb = execSync(`ps -eo rss,comm | grep -E "node|chrom|headless|ffmpeg" | awk '{s+=$1} END {print s}'`).toString().trim();
    return Number(kb) / 1024;
  } catch { return 0; }
}

let peak = 0;
const sampler = setInterval(() => { peak = Math.max(peak, rssMb()); }, 500);

const props = { ...defaultProps, anchorDurationSeconds: seconds, anchorSrc: withAnchor ? "bench-anchor.webm" : null };
const t0 = Date.now();
await getBundle();
const bundleS = (Date.now() - t0) / 1000;
const results: Record<string, number> = {};
for (const format of ["16x9", "9x16"] as const) {
  const t = Date.now();
  await renderOne({ format, props, outFile: `out/bench-${format}-${seconds}s.mp4` });
  results[format] = (Date.now() - t) / 1000;
}
clearInterval(sampler);
console.log(JSON.stringify({
  cpus: os.cpus().length, memGb: Math.round(os.totalmem() / 2 ** 30), videoSeconds: seconds, withAnchor,
  bundleS, renderS: results, totalS: (Date.now() - t0) / 1000, peakRssMb: Math.round(peak),
}, null, 2));
