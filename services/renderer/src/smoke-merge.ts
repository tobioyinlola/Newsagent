// Renders the InterviewMerge composition for real (PiP 16:9 and split 9:16) with stand-in clips.
import { execFileSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";
import { renderOne } from "./render";

fs.mkdirSync("out", { recursive: true });
fs.mkdirSync("public", { recursive: true });
if (!fs.existsSync("public/bench-anchor.webm")) throw new Error("run scripts/make-standin-anchor.sh first");
// A "founder" answer: portrait phone video with speech-like tone.
execFileSync("ffmpeg", ["-y", "-loglevel", "error", "-f", "lavfi", "-i", "testsrc2=s=720x1280:r=30:d=4", "-f", "lavfi", "-i", "sine=frequency=300:d=4", "-c:v", "libx264", "-pix_fmt", "yuv420p", "-c:a", "aac", "public/founder-answer.mp4"]);

const props = {
  channel: { name: "Startup Spotlight Network" }, disclosures: { tag: "Featured", anchor: "AI-generated anchor" },
  brand: { primary: "#0B3D91", accent: "#F5A623" }, tickerLines: ["FEATURED: Acme interview"], layout: "pip", totalSeconds: 11,
  scenes: [
    { type: "anchor", src: "bench-anchor.webm", seconds: 2 },
    { type: "question", src: "bench-anchor.webm", seconds: 2 },
    { type: "answer", src: "founder-answer.mp4", seconds: 4, pipSrc: "bench-anchor.webm", founder: { name: "Ada Obi", title: "CEO, Acme" } },
    { type: "anchor", src: "bench-anchor.webm", seconds: 2 },
  ],
};
const jobs: [string, "16x9" | "9x16", string][] = [["pip", "16x9", "pip"], ["split", "9x16", "split"]];
for (const [name, format, layout] of jobs) {
  const t = Date.now();
  await renderOne({ composition: "InterviewMerge", format, props: { ...props, layout }, outFile: `out/merge-${name}.mp4` });
  console.log(name, format, `${((Date.now() - t) / 1000).toFixed(0)}s`);
  // grab a frame from inside the answer scene (t=5s) to eyeball the layout
  execFileSync("ffmpeg", ["-y", "-loglevel", "error", "-ss", "5", "-i", `out/merge-${name}.mp4`, "-frames:v", "1", `out/merge-${name}.png`]);
}
console.log(execFileSync("ffprobe", ["-v", "error", "-show_entries", "format=duration", "-of", "csv=p=0", "out/merge-pip.mp4"]).toString().trim(), "s");
process.exit(0);
