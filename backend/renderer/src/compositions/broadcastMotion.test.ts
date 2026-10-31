import { describe, expect, it } from "vitest";
import { cardMotion } from "./broadcastMotion";
import { broadcastClock } from "./broadcastClock";

describe("broadcast graphics", () => {
  it("brings cards in and out smoothly without shifting scene timing", () => {
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
});
