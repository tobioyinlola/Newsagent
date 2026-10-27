import { describe, expect, it } from "vitest";
import { ago, date, num, shortDay, usd } from "./format";

describe("format", () => {
  it("shows whole dollars without cents and fractions with them", () => {
    expect(usd("148")).toBe("$148");
    expect(usd("12.5")).toBe("$12.50");
    expect(usd(0)).toBe("$0");
  });
  it("shows numbers compactly", () => {
    expect(num("1234.56")).toBe("1,234.6");
  });
  it("says how long ago, and never for something that never happened", () => {
    expect(ago(null)).toBe("never");
    expect(ago(new Date().toISOString())).toBe("just now");
    expect(ago(new Date(Date.now() - 2 * 3600_000).toISOString())).toBe("2 h ago");
    expect(date(undefined)).toBe("never");
  });
  it("labels chart days", () => {
    expect(shortDay("2026-10-22")).toMatch(/22/);
  });
});
