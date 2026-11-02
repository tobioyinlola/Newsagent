import fs from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import { LEGACY_URL_SECONDS, urlBadgeOut } from "./InterviewMerge";

const code = (f: string) => fs.readFileSync(path.resolve(__dirname, f), "utf8").replace(/\/\/.*$/gm, "").replace(/\/\*[\s\S]*?\*\//g, "");

describe("Video Rulebook rules drawn by the renderer", () => {
  it("draws no AI-anchor or Featured label over a business interview video", () => {
    // covers: BIV-GFX-001
    for (const f of ["Chrome.tsx", "InterviewMerge.tsx", "LowerThird.tsx"]) {
      expect(code(f)).not.toMatch(/disclosures\.(tag|anchor)/);
      expect(code(f)).not.toMatch(/>\s*(AI-generated anchor|Featured)\s*</i);
    }
  });
  it("the web address card stays still for the whole closing remark (v4); older videos keep their short slide-out", () => {
    // covers: BIV-GFX-011
    const fps = 30, line = 7; // a 7 s closing remark
    for (let f = 0; f < line * fps; f++) expect(urlBadgeOut(f, fps, line, true)).toBe(0); // never leaves while the line plays
    expect(urlBadgeOut(Math.round(4.9 * fps), fps, LEGACY_URL_SECONDS, false)).toBeGreaterThan(0); // older videos still slide out
    expect(code("InterviewMerge.tsx")).toMatch(/durationInFrames=\{Math\.max\(1, Math\.round\(\(p\.productUrlSeconds \?\? LEGACY_URL_SECONDS\) \* fps\)\)\}/);
  });
});

describe("no label wording around the video", () => {
  it.each(["Chrome.tsx", "InterviewMerge.tsx", "NewsStudio.tsx", "types.ts"])("%s carries no Featured / AI-generated anchor wording", (f) => {
    // covers: BIV-GFX-009
    expect(code(f)).not.toMatch(/disclosures/);
    expect(code(f)).not.toMatch(/Featured startup|AI-generated anchor/);
  });
});
