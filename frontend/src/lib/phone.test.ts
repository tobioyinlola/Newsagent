import { describe, expect, it } from "vitest";
import { nationalPhone, normalizePhone, phoneCountry, phoneCountries, validPhone } from "./phone";

describe("country phone numbers", () => {
  it.each([
    ["08031234567", "NG", "+2348031234567"],
    ["07700900123", "GB", "+447700900123"],
    ["9058052110", "CA", "+19058052110"],
    ["0669821234", "IT", "+390669821234"],
  ] as const)("formats %s using %s without losing meaningful leading zeros", (raw, country, expected) => {
    expect(normalizePhone(raw, country)).toBe(expected);
  });
  it("recognizes existing Canadian numbers despite the shared +1 code", () => {
    expect(phoneCountry("+19058052110")).toBe("CA");
    expect(nationalPhone("+19058052110", "CA")).toBe("9058052110");
    expect(phoneCountry("+19058052110", "US")).toBe("US");
  });
  it("does not duplicate a pasted international prefix", () => {
    expect(normalizePhone("+234 803 123 4567", "NG")).toBe("+2348031234567");
    expect(validPhone("+234 803 123 4567", "NG")).toBe(true);
  });
  it("requires country selection for local numbers and rejects malformed or mismatched numbers", () => {
    expect(validPhone("08031234567")).toBe(false);
    expect(validPhone("08031234567", "NG")).toBe(true);
    expect(validPhone("123", "NG")).toBe(false);
    expect(validPhone("call +2348031234567", "NG")).toBe(false);
    expect(validPhone("+19058052110", "NG")).toBe(false);
    expect(validPhone("+2348031234567890000", "NG")).toBe(false);
  });
  it("includes countries sharing dialing codes as separate choices", () => {
    expect(phoneCountries.find(c => c.code === "US")?.dial).toBe("1");
    expect(phoneCountries.find(c => c.code === "CA")?.dial).toBe("1");
    expect(phoneCountries.find(c => c.code === "NG")?.dial).toBe("234");
  });
});
