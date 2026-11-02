import { describe, expect, it } from "vitest";
import { answerTiming, answerWindow, COUNTDOWN_S } from "./timing";

describe("answer recording contract", () => {
  it("always prepares five seconds before recording and never shortens later answers", () => {
    // covers: BIV-INT-004, BIV-INT-006
    expect(COUNTDOWN_S).toBe(5);
    expect(answerWindow(290, 4)).toBe(60);
    expect(answerWindow(800, 1)).toBe(60);
  });
  it("counts down the minute, grants exactly five seconds to round up, then stops", () => {
    // covers: BIV-INT-004, BIV-INT-007
    expect(answerTiming(0)).toEqual({ roundingUp: false, remaining: 60, shouldStop: false });
    expect(answerTiming(59)).toEqual({ roundingUp: false, remaining: 1, shouldStop: false });
    expect(answerTiming(60)).toEqual({ roundingUp: true, remaining: 5, shouldStop: false });
    expect(answerTiming(64)).toEqual({ roundingUp: true, remaining: 1, shouldStop: false });
    expect(answerTiming(65)).toEqual({ roundingUp: true, remaining: 0, shouldStop: true });
  });
});
