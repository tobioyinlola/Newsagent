// Renders public/bench-anchor.webm: the illustrated stand-in presenter (compositions/AnchorFigure.tsx) as a 30 s VP9 clip
// WITH A REAL ALPHA CHANNEL plus a tone, playing the part of the avatar vendor's transparent anchor in local runs.
import { bundle } from "@remotion/bundler";
import { renderMedia, selectComposition } from "@remotion/renderer";
import { execFileSync } from "node:child_process";
import fs from "node:fs";
import path from "node:path";

fs.mkdirSync("public", { recursive: true });
const browserExecutable = process.env.CHROMIUM_PATH || undefined;
const serveUrl = await bundle({ entryPoint: path.resolve("src/index.ts"), publicDir: path.resolve("public") });
const composition = await selectComposition({ serveUrl, id: "StandInAnchor", browserExecutable });
const silent = "public/.standin-anchor.silent.webm";
await renderMedia({ composition, serveUrl, codec: "vp9", imageFormat: "png", pixelFormat: "yuva420p", outputLocation: silent, browserExecutable });
execFileSync("ffmpeg", ["-y", "-loglevel", "error", "-i", silent, "-f", "lavfi", "-i", "sine=frequency=220:d=30", "-c:v", "copy", "-c:a", "libopus", "-shortest", "public/bench-anchor.webm"]);
fs.rmSync(silent);
process.exit(0);
