import { describe, expect, it } from "vitest";
import { backoffInterval } from "./polling";

describe("backoffInterval", () => {
  const t0 = 1_000_000;
  it("asks quickly at first, then slows down the longer the page stays open", () => {
    expect(backoffInterval(t0, 4000, t0)).toBe(4000);
    expect(backoffInterval(t0, 4000, t0 + 29_999)).toBe(4000);
    expect(backoffInterval(t0, 4000, t0 + 30_000)).toBe(10_000);
    expect(backoffInterval(t0, 4000, t0 + 119_999)).toBe(10_000);
    expect(backoffInterval(t0, 4000, t0 + 120_000)).toBe(20_000);
    expect(backoffInterval(t0, 4000, t0 + 3_600_000)).toBe(20_000); // never stops, never slower than 20 s
  });
  it("never goes faster than asked for", () => {
    expect(backoffInterval(t0, 30_000, t0 + 60_000)).toBe(30_000);
  });
});
