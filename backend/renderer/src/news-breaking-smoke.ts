/** Standalone composition verification with local fixture media; no paid provider calls. */
import { renderOne, getBundle } from "./render";
import { renderStill, selectComposition } from "@remotion/renderer";
import fs from "node:fs";
import { breakingFrames, type BreakingProps } from "./compositions/NewsBreaking";
const output = process.env.NEWS_SMOKE_DIR || "/tmp/news-breaking-preview";
fs.mkdirSync(output, { recursive: true });
const props: BreakingProps = {
  headline: "Technology update: a new chapter for small businesses across Africa",
  summary: "Cover Founder News · standalone breaking-news format",
  anchorSrc: "http://127.0.0.1:5200/presenter.mp4",
  presenterFrames: 900,
  pictures: [
    { src: "http://127.0.0.1:5200/editorial-image.webp", caption: "Editorial picture · fixture for motion verification", motion: "slow_zoom_in", duration_s: 5 },
    { src: "http://127.0.0.1:5200/editorial-image.webp", caption: "Return to the presenter between images", motion: "pan_right", duration_s: 5 },
  ],
};
const serveUrl = await getBundle();
const comp = await selectComposition({ serveUrl, id: "NewsBreaking-16x9", inputProps: props, browserExecutable: process.env.CHROMIUM_PATH });
if (comp.durationInFrames !== breakingFrames(props) || comp.durationInFrames > 1800) throw new Error("Duration contract failed");
for (const [name, frame] of [["breaking-sting", 180], ["presenter", 300], ["moving-image", 420], ["outro", 1200]] as const) {
  await renderStill({ composition: comp, serveUrl, output: `${output}/${name}.png`, frame, inputProps: props, browserExecutable: process.env.CHROMIUM_PATH, scale: 0.5 });
}
await renderOne({ composition: "NewsBreaking", format: "16x9", props, outFile: `${output}/news-breaking-preview.mp4`, scale: 0.5 });
console.log(JSON.stringify({ durationSeconds: comp.durationInFrames / comp.fps, output }));
