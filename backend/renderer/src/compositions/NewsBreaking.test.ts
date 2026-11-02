import fs from "node:fs";
import path from "node:path";
import { describe, expect, it } from "vitest";
import { breakingCutaways, breakingFrames, defaultBreakingProps, validateBreakingProps, SCREEN_TEXT } from "./NewsBreaking";
describe("isolated breaking-news duration contract", () => {
  it("includes the five-second intro, two-second sting and six-second outro", () => {
    expect(breakingFrames({ ...defaultBreakingProps, presenterFrames: 1410 })).toBe(1800);
    expect(breakingFrames({ ...defaultBreakingProps, presenterFrames: 900 })).toBe(1290);
    for (const presenterFrames of [1411, 0, -1, 3.5, NaN, Infinity]) expect(() => breakingFrames({ ...defaultBreakingProps, presenterFrames })).toThrow();
  });
  it("returns to the presenter between and after images without extending the video", () => {
    const scenes = breakingCutaways(1410, 10);
    expect(scenes.length).toBeGreaterThan(1);
    scenes.forEach((scene, i) => {
      expect(scene.from).toBeGreaterThanOrEqual(150);
      expect(scene.from + scene.duration).toBeLessThan(1410 - 30);
      if (i) expect(scene.from).toBeGreaterThan(scenes[i - 1].from + scenes[i - 1].duration);
    });
  });
  it("rejects missing presenter footage or images before rendering", () => {
    expect(() => validateBreakingProps(defaultBreakingProps)).toThrow();
    expect(() => validateBreakingProps({ ...defaultBreakingProps, anchorSrc: "https://example.com/clip.mp4", pictures: [{ src: "https://example.com/image.png", caption: "", motion: "slow_zoom_in" }] })).not.toThrow();
  });
});

describe("News Desk presenter screens", () => {
  it("covers a presenter's own studio screens with correctly spelled boards when asked", () => {
    expect(SCREEN_TEXT).toBe("Breaking News");
    const code = fs.readFileSync(path.resolve(__dirname, "NewsBreaking.tsx"), "utf8");
    expect(code).toMatch(/p\.anchorCovers \? <FullFrameAnchor src=\{p\.anchorSrc\} covers screenText=\{SCREEN_TEXT\} \/>/);
  });
});
