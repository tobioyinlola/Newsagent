import { describe, expect, it } from "vitest";
import { contrastRatio, isHex } from "./contrast";

describe("contrast", () => {
  it("matches the API for known pairs", () => {
    expect(contrastRatio("#000000", "#FFFFFF")).toBe(21);
    expect(contrastRatio("#0B3D91", "#FFFFFF")).toBe(10.04); // same value the API test suite sees
    expect(contrastRatio("#F5A623", "#111111")).toBe(9.32);
  });
  it("validates hex", () => {
    expect(isHex("#0B3D91")).toBe(true);
    expect(isHex("blue")).toBe(false);
  });
});
