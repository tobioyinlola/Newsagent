import fs from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import { rule } from "../videoRules";
import { URL_SHOWN_S } from "./InterviewMerge";

const code = (f: string) => fs.readFileSync(path.resolve(__dirname, f), "utf8").replace(/\/\/.*$/gm, "").replace(/\/\*[\s\S]*?\*\//g, "");

describe("Video Rulebook rules drawn by the renderer", () => {
  it("draws no AI-anchor or Featured label over a business interview video", () => {
    // covers: BIV-GFX-001
    for (const f of ["Chrome.tsx", "InterviewMerge.tsx", "LowerThird.tsx"]) {
      expect(code(f)).not.toMatch(/disclosures\.(tag|anchor)/);
      expect(code(f)).not.toMatch(/>\s*(AI-generated anchor|Featured)\s*</i);
    }
  });
  it("shows the product's web address for the rulebook's time at the sign-off", () => {
    // covers: BIV-GFX-006
    expect(URL_SHOWN_S).toBe(rule<number>("BIV-GFX-006"));
    expect(code("InterviewMerge.tsx")).toMatch(/durationInFrames=\{Math\.round\(URL_SHOWN_S \* fps\)\}/);
  });
});

describe("no label wording around the video", () => {
  it.each(["Chrome.tsx", "InterviewMerge.tsx", "NewsStudio.tsx", "types.ts"])("%s carries no Featured / AI-generated anchor wording", (f) => {
    // covers: BIV-GFX-009
    expect(code(f)).not.toMatch(/disclosures/);
    expect(code(f)).not.toMatch(/Featured startup|AI-generated anchor/);
  });
});
