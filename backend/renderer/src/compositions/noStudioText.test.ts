import fs from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";

const code = (f: string) => fs.readFileSync(path.resolve(__dirname, f), "utf8").replace(/\/\/.*$/gm, "").replace(/\/\*[\s\S]*?\*\//g, "");

// The studio set and the boards over a presenter video's own screens carry no words: a "FEATURED / STARTUP NEWS" plate showing
// through the presenter at a cut (or around a narrow picture) is exactly what a finished video must never show.
describe("no studio plates in the picture", () => {
  it.each(["BlueStudio.tsx", "FullFrameAnchor.tsx", "NewsSet.tsx", "InterviewMerge.tsx", "NewsStudio.tsx"])("%s prints no FEATURED / STARTUP NEWS plate", (f) => {
    expect(code(f)).not.toMatch(/STARTUP NEWS/);
    expect(code(f)).not.toMatch(/>\s*FEATURED\s*</);
  });
  it("behind the scenes of a presenter video with its own studio there is only plain ink, never our set", () => {
    expect(code("InterviewMerge.tsx")).toMatch(/anchorFullFrame \? <AbsoluteFill style=\{\{ background: CF\.ink \}\} \/> : <Backdrop \/>/);
  });
});
