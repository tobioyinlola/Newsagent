import { describe, expect, it } from "vitest";
import { cardMotion, speakerOf, turnCard, turnStarts } from "./broadcastMotion";
import { broadcastClock } from "./broadcastClock";

describe("broadcast graphics", () => {
  it("brings cards in and out smoothly without shifting scene timing", () => {
    // covers: BIV-GFX-007
    const values = Array.from({ length: 240 }, (_, f) => cardMotion(f, 240, 30, .5, 6));
    expect(values[0]).toBe(0); expect(values[60]).toBe(1); expect(values[239]).toBe(0);
    expect(values.every(v => Number.isFinite(v) && v >= 0 && v <= 1)).toBe(true);
    expect(Math.max(...values.map((v, i) => Math.abs(v - (values[i - 1] ?? 0))))).toBeLessThan(.15);
    for (const duration of [1, 2, 8, 20]) expect(cardMotion(0, duration, 30, .5, 6)).not.toBeNaN();
  });
  it("updates seconds, minute and noon rollover without changing the zone label", () => {
    expect(broadcastClock("OCT 31, 2026 · 11:59 AM EDT", 61)).toBe("OCT 31, 2026 · 12:00:01 PM EDT");
    expect(broadcastClock("OCT 31, 2026 · 11:59 PM EDT", 60)).toBe("OCT 31, 2026 · 12:00:00 AM EDT");
    expect(broadcastClock("A supplied label without a time", 15)).toBe("A supplied label without a time");
  });
  it("a turn's card comes in once, then stays fully on screen and still to the turn's very last frame", () => {
    // covers: BIV-GFX-010
    const fps = 30, scene = 20 * fps; // a 20 s answer: far longer than the old 6 s hold
    const v = Array.from({ length: scene }, (_, f) => turnCard(f, scene, fps, true, .5, .4));
    expect(v[0]).toBe(0);
    const full = v.findIndex(x => x === 1);
    expect(full).toBeGreaterThan(0); expect(full).toBeLessThanOrEqual(Math.ceil(fps * .9)); // in by about 0.9 s
    expect(v.slice(full).every(x => x === 1)).toBe(true); // still and fully visible, no fade-out, to the last frame
    for (let f = 1; f < full; f++) expect(v[f]).toBeGreaterThanOrEqual(v[f - 1]); // only ever comes in
  });
  it("a scene that continues the same speaker's turn shows the card fully from its first frame", () => {
    // covers: BIV-GFX-010
    for (const d of [1, 5, 90, 600]) for (const f of [0, Math.floor(d / 2), d - 1]) expect(turnCard(f, d, 30, false, .5, .4)).toBe(1);
  });
  it("turns start only when the speaker changes: back-to-back presenter scenes are one turn", () => {
    // covers: BIV-GFX-010
    expect(["anchor", "question", "answer", "clip", "question", "answer", "anchor", "anchor"].map(speakerOf))
      .toEqual(["presenter", "presenter", "founder", null, "presenter", "founder", "presenter", "presenter"]);
    expect(turnStarts(["anchor", "question", "answer", "clip", "question", "answer", "anchor", "anchor"]))
      .toEqual([true, false, true, false, true, true, true, false]);
    expect(turnStarts(["clip", "broll", "anchor"])).toEqual([false, false, true]);
  });
  it("very short scenes still bring the card fully in and never produce a bad value", () => {
    // covers: BIV-GFX-010
    for (const d of [1, 2, 8, 20]) {
      const v = Array.from({ length: d }, (_, f) => turnCard(f, d, 30, true, .5, .4));
      expect(v.every(x => Number.isFinite(x) && x >= 0 && x <= 1)).toBe(true);
      if (d >= 8) expect(v[d - 1]).toBe(1);
    }
  });
});
