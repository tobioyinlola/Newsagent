import { describe, expect, it } from "vitest";
import { defaultCurrency, optionsFor, priceIn, standardIn, type Currency, type MediaPackage } from "./packages";

const cs: Currency[] = [
  { code: "USD", name: "US dollar", per_usd: "1" }, { code: "NGN", name: "Naira", per_usd: "1400" }, { code: "GBP", name: "Pound", per_usd: "0.7599" },
  { code: "CAD", name: "Canadian dollar", per_usd: "1.4318" }, { code: "AED", name: "Dirham", per_usd: "3.6725" }, { code: "QAR", name: "Riyal", per_usd: "3.64" },
];
const base = { id: "1", slug: "s", kind: "regional", region: "us", campaign: "", name: "P", usd_price: "995.00", usd_estimate: null, standard_usd: null, percent_off: null, credits: "368.52", local_prices: {}, outlets: [], includes: [], ideal_for: "", note: "", slots_total: null, slots_left: null, ends_at: null, state: "open" } as MediaPackage;

describe("a card shows one currency", () => {
  it("uses the document's own price where it states one, and converts the rest", () => {
    const launch = { ...base, usd_price: "651.57", local_prices: { NGN: "912203.49" } };
    expect(priceIn(launch, "NGN", cs)).toBe("₦912,203.49"); // as written, not 651.57 x 1400
    expect(priceIn(launch, "USD", cs)).toBe("US$651.57");
    expect(priceIn(base, "NGN", cs)).toBe("₦1,393,000"); // 995 x 1400: just the amount, no estimate sign
    expect(standardIn({ ...base, standard_usd: "1495.00" }, "NGN", cs)).toBe("₦2,093,000");
  });
  it("shows a price-on-request package in the document's own currencies", () => {
    const gulf = { ...base, usd_price: null, usd_estimate: "495.57", region: "middle_east", local_prices: { AED: "1820", QAR: "1805" } };
    expect(priceIn(gulf, "AED", cs)).toBe("AED 1,820");
    expect(priceIn(gulf, "QAR", cs)).toBe("QAR 1,805");
    expect(priceIn({ ...gulf, usd_estimate: null, local_prices: {} }, "NGN", cs)).toBeNull(); // nothing to show it from: "Custom quote"
  });
});

describe("the currency a card opens in", () => {
  it("is the region's own, as in the document", () => {
    expect(defaultCurrency({ ...base, region: "canada", usd_price: "961.74", local_prices: { CAD: "1377.02" } })).toBe("CAD");
    expect(defaultCurrency({ ...base, region: "nigeria", local_prices: { NGN: "506000" } })).toBe("NGN");
    expect(defaultCurrency({ ...base, region: "uk_europe", local_prices: { GBP: "19678.19" } })).toBe("GBP");
    expect(defaultCurrency({ ...base, region: "uk_europe", usd_price: null, local_prices: { GBP: "530" } })).toBe("GBP");
    expect(defaultCurrency({ ...base, region: "middle_east", usd_price: null, local_prices: { AED: "1820", QAR: "1805" } })).toBe("AED");
  });
  it("is dollars for the US, Africa-wide, the organisations and the campaign deals", () => {
    expect(defaultCurrency(base)).toBe("USD");
    expect(defaultCurrency({ ...base, region: "africa", local_prices: { GHS: "18022" } })).toBe("USD");
    expect(defaultCurrency({ ...base, kind: "campaign", region: "campaign", local_prices: { NGN: "912203.49" } })).toBe("USD");
  });
});

describe("what a card's picker offers", () => {
  it("lists the document's currencies first", () => {
    const canada = { ...base, region: "canada", usd_price: "961.74", local_prices: { CAD: "1377.02" } };
    expect(optionsFor(canada, cs).slice(0, 2).map((c) => c.code)).toEqual(["USD", "CAD"]);
  });
  it("never offers dollars for a package priced on request", () => {
    const gulf = { ...base, usd_price: null, local_prices: { AED: "1820", QAR: "1805" } };
    const codes = optionsFor(gulf, cs).map((c) => c.code);
    expect(codes.slice(0, 2)).toEqual(["AED", "QAR"]);
    expect(codes).not.toContain("USD");
  });
});
