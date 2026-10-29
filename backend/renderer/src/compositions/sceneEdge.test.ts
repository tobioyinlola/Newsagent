import { describe, expect, it } from "vitest";
import { EDGE_FRAMES, edgeGain } from "./SceneEdge";

describe("scene edges", () => {
  it("start silent-ish, reach full gain, and end silent-ish, never jumping", () => {
    const d = 90;
    const gains = Array.from({ length: d }, (_, f) => edgeGain(f, d));
    expect(gains[0]).toBeLessThan(0.3);
    expect(gains[Math.floor(d / 2)]).toBe(1);
    expect(gains[d - 1]).toBeLessThan(0.3);
    for (let f = 1; f < d; f++) expect(Math.abs(gains[f] - gains[f - 1])).toBeLessThanOrEqual(1 / (EDGE_FRAMES - 1) + 1e-9); // no step: a ramp
    expect(Math.min(...gains)).toBeGreaterThan(0); // the picture never goes fully black
  });
  it("gives a very short scene a shorter dip rather than never reaching full", () => {
    expect(edgeGain(1, 6)).toBe(1);
    expect(edgeGain(0, 1)).toBeGreaterThan(0);
  });
});
