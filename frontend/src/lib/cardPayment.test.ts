import { describe, expect, it } from "vitest";
import { cardErrors, emptyCard, expiryParts } from "./cardPayment";
const valid = { ...emptyCard, first_name: "Ada", last_name: "Obi", number: "4111 1111 1111 1111", expiry: "12/35", cvv: "123", address_line_one: "1 Main Street", city: "Lagos", state: "Lagos", country: "NG" };
describe("card validation", () => {
  it("accepts a valid Luhn number and normalizes expiry", () => {
    expect(cardErrors(valid, new Date("2030-01-01"))).toEqual({});
    expect(expiryParts("2 / 35")).toEqual({ month: "02", year: "2035" });
  });
  it("rejects invalid numbers, expired cards, missing addresses and malformed country codes", () => {
    const errors = cardErrors({ ...valid, number: "4111111111111112", expiry: "12/25", cvv: "1", address_line_one: "", country: "Nigeria" }, new Date("2030-01-01"));
    for (const key of ["number", "expiry", "cvv", "address_line_one", "country"] as const) expect(errors[key]).toBeTruthy();
  });
  it("keeps a card valid through its expiration month", () => {
    expect(cardErrors({ ...valid, expiry: "01/30" }, new Date("2030-01-31")).expiry).toBeUndefined();
    expect(cardErrors({ ...valid, expiry: "01/30" }, new Date("2030-02-01")).expiry).toBeTruthy();
  });
});
