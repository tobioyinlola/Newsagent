import { readFileSync } from "node:fs";
import { describe, expect, it } from "vitest";

// The cover picture of a video shows the still taken while the founder was composed (during the countdown), not a frame of them
// mid-sentence. Only the cover render asks for it; the video itself keeps playing the founder's recording.
describe("the cover picture", () => {
  const merge = readFileSync(new URL("./InterviewMerge.tsx", import.meta.url), "utf8");
  const render = readFileSync(new URL("../render.ts", import.meta.url), "utf8");
  it("is rendered from the answer's still", () => {
    expect(render).toMatch(/const stillProps = \{ \.\.\.props, coverStill: true \}/);
    expect(render).toMatch(/renderStill\(\{[^}]*inputProps: stillProps/);
    expect(merge).toMatch(/coverStill && scene\.posterSrc \? \(\s*<Img src=\{url\(scene\.posterSrc\)\}/);
  });
  it("is never turned on for the video render", () => {
    expect(render.match(/coverStill/g)?.length).toBe(1);
  });
});
