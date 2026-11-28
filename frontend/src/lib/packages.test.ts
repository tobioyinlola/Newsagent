import { beforeEach, describe, expect, it } from "vitest";
import { priceIn, rememberCurrency, standardIn, startingCurrency, type Currency, type MediaPackage } from "./packages";

const cs: Currency[] = [
  { code: "USD", name: "US dollar", per_usd: "1" }, { code: "NGN", name: "Naira", per_usd: "1400" }, { code: "GBP", name: "Pound", per_usd: "0.7599" },
  { code: "CAD", name: "Canadian dollar", per_usd: "1.4318" }, { code: "AED", name: "Dirham", per_usd: "3.6725" },
];
const base = { id: "1", slug: "s", kind: "regional", region: "us", campaign: "", name: "P", usd_price: "995.00", usd_estimate: null, standard_usd: null, percent_off: null, credits: "368.52", local_prices: {}, outlets: [], includes: [], ideal_for: "", note: "", slots_total: null, slots_left: null, ends_at: null, state: "open" } as MediaPackage;

describe("prices in other currencies", () => {
  it("shows a price the document states exactly, and converts the rest", () => {
    const launch = { ...base, usd_price: "651.57", local_prices: { NGN: "912203.49" } };
    expect(priceIn(launch, "NGN", cs)).toEqual({ text: "₦912,203.49", approx: false }); // as written, not 651.57 x 1400
    expect(priceIn(launch, "USD", cs)).toEqual({ text: "US$651.57", approx: false });
    expect(priceIn(base, "NGN", cs)).toEqual({ text: "₦1,393,000", approx: true }); // 995 x 1400, marked as converted
    expect(priceIn(base, "CAD", cs)).toEqual({ text: "C$1,425", approx: true });
  });
  it("converts the usual price too, and shows the dollar one as it is", () => {
    const deal = { ...base, standard_usd: "1495.00" };
    expect(standardIn(deal, "NGN", cs)).toBe("₦2,093,000");
    expect(standardIn(deal, "USD", cs)).toBe("US$1,495");
    expect(standardIn(base, "NGN", cs)).toBeNull();
  });
  it("shows a quote-only package in any currency from the price the document gave it", () => {
    const quote = { ...base, usd_price: null, usd_estimate: "697.46", local_prices: { GBP: "530" } };
    expect(priceIn(quote, "GBP", cs)).toEqual({ text: "£530", approx: false });
    expect(priceIn(quote, "NGN", cs)).toEqual({ text: "₦976,444", approx: true });
    expect(priceIn({ ...quote, usd_estimate: null, local_prices: {} }, "NGN", cs)).toBeNull(); // nothing to convert: "Custom quote"
  });
});

describe("the currency a visitor starts with", () => {
  beforeEach(() => localStorage.clear());
  it("remembers a choice, ignoring one that is not on offer", () => {
    expect(startingCurrency(cs)).toBe("USD");
    rememberCurrency("GBP");
    expect(startingCurrency(cs)).toBe("GBP");
    rememberCurrency("XYZ");
    expect(startingCurrency(cs)).toBe("USD");
  });
});
