import { describe, expect, it } from "vitest";
import { breakingCutaways, breakingFrames, defaultBreakingProps, validateBreakingProps, PRESENTER_ZOOM, SETBACK_BOTTOM, setbackFocus } from "./NewsBreaking";
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

describe("News Desk presenter framing", () => {
  it("sets the presenter back so her whole face sits above the headline, resting on it with no gap", () => {
    expect(PRESENTER_ZOOM).toBe(0.6);
    const focus = (zoom: number) => Number(setbackFocus(zoom).split(" ")[1].replace("%", "")) / 100;
    for (const zoom of [0.5, 0.6, 0.7]) {
      const o = focus(zoom);
      expect(o + zoom * (1 - o)).toBeCloseTo(SETBACK_BOTTOM, 3); // its bottom edge rests on the headline
    }
    for (const zoom of [0.78, 0.85]) expect(focus(zoom)).toBe(0); // too tall to fit above the headline: kept at the top
  });
});
