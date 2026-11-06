import { beforeEach, describe, expect, it } from "vitest";
import { ALL, counts, emptyReason, groupOutlets, isAllowedAfter, matches, outletTitle, peekAfterAuth, readPick, savePick, setAfterAuth, takeAfterAuth, clearPick } from "./distributionFilters";

const outlets = [
  { id: "1", topic: "Technology", region: "Africa", country: "Nigeria" },
  { id: "2", topic: "General News", region: "Africa", country: "Nigeria" },
  { id: "3", topic: "Gossip Blogs", region: "Africa", country: "Nigeria" },
  { id: "4", topic: "General News", region: "Africa", country: "Kenya" },
  { id: "5", topic: "General News", region: "North America", country: "United States" },
];
const filters = { topics: ["Technology", "General News", "Gossip Blogs"], locations: [{ region: "Africa", countries: ["Nigeria", "Ghana", "Kenya", "Uganda"] }, { region: "North America", countries: ["Canada", "United States"] }, { region: "Europe", countries: ["United Kingdom"] }] };

beforeEach(() => localStorage.clear());

describe("filtering", () => {
  it("shows everything when nothing is chosen and narrows by topic, region and country", () => {
    expect(outlets.filter((o) => matches(o, ALL))).toHaveLength(5);
    expect(outlets.filter((o) => matches(o, { ...ALL, topic: "General News" })).map((o) => o.id)).toEqual(["2", "4", "5"]);
    expect(outlets.filter((o) => matches(o, { ...ALL, region: "Africa" }))).toHaveLength(4);
    expect(outlets.filter((o) => matches(o, { topic: "General News", region: "Africa", country: "Kenya" })).map((o) => o.id)).toEqual(["4"]);
  });
  it("counts what each choice would show, given the others", () => {
    const c = counts(outlets, { ...ALL, region: "Africa" }, filters);
    expect(c.topic).toEqual({ Technology: 1, "General News": 2, "Gossip Blogs": 1 });
    expect(c.all).toBe(4);
    expect(counts(outlets, ALL, filters).country.Ghana).toBe(0);
  });
  it("explains an empty result", () => {
    expect(emptyReason(outlets, ALL)).toBeNull();
    expect(emptyReason(outlets, { ...ALL, country: "Ghana" })).toMatch(/no outlets in Ghana yet/);
    expect(emptyReason(outlets, { topic: "Technology", region: "Africa", country: "Kenya" })).toMatch(/No outlets match/);
  });
});

describe("the saved choice", () => {
  it("is kept, and forgotten after a week or when cleared", () => {
    savePick(["2", "5"]);
    expect(readPick()).toEqual(["2", "5"]);
    expect(readPick(Date.now() + 8 * 24 * 3600 * 1000)).toEqual([]);
    expect(readPick()).toEqual([]); // the expired one was removed
    savePick(["1"]); clearPick();
    expect(readPick()).toEqual([]);
  });
  it("ignores damaged storage", () => {
    localStorage.setItem("newsagent.distribution.pick", "{not json");
    expect(readPick()).toEqual([]);
    localStorage.setItem("newsagent.distribution.pick", JSON.stringify({ ids: [1, "2"], at: Date.now() }));
    expect(readPick()).toEqual(["2"]);
  });
  it("only ever sends people to the distribution request page after sign-in", () => {
    expect(isAllowedAfter("/distribution/request?pick=1")).toBe(true);
    expect(isAllowedAfter("/distribution/request")).toBe(true);
    for (const bad of ["https://evil.test", "//evil.test", "/dashboard", "/distribution/requestx", "/distribution/request/../../admin"]) expect(isAllowedAfter(bad)).toBe(false);
    setAfterAuth("https://evil.test");
    expect(peekAfterAuth()).toBeNull();
    setAfterAuth("/distribution/request?pick=1");
    expect(peekAfterAuth()).toBe("/distribution/request?pick=1");
    expect(takeAfterAuth()).toBe("/distribution/request?pick=1");
    expect(takeAfterAuth()).toBeNull(); // used once
  });
});

describe("grouping", () => {
  const more = [...outlets, { id: "6", topic: "Technology", region: "Africa", country: null }, { id: "7", topic: "Technology", region: "North America", country: "United States" }, { id: "8", region: "Europe", country: "United Kingdom" }];
  it("groups by topic, then by place, in a steady order, leaving empty groups out", () => {
    const g = groupOutlets(more, filters);
    expect(g.map((x) => `${x.topic}:${x.count}`)).toEqual(["General News:3", "Technology:3", "Gossip Blogs:1", "Others:1"]); // General News first
    expect(g[1].locations.map((l) => l.label)).toEqual(["Nigeria", "Africa (region-wide)", "US & Canada"]); // countries first, then the whole region, then the next region
    expect(g[0].locations.map((l) => `${l.label}:${l.items.length}`)).toEqual(["United States:1", "Nigeria:1", "Kenya:1"]);
    expect(groupOutlets(outlets.filter((o) => o.country === "Kenya"), filters).map((x) => x.topic)).toEqual(["General News"]);
    expect(groupOutlets([], filters)).toEqual([]);
  });
  it("works without the filter list too", () => {
    expect(groupOutlets(outlets)[0].topic).toBe("General News");
  });
  it("joins the United States and Canada in Technology", () => {
    const tech = [
      { id: "a", topic: "Technology", region: "North America", country: "United States" },
      { id: "b", topic: "Technology", region: "North America", country: "Canada" },
      { id: "c", topic: "Technology", region: "Africa", country: "Nigeria" },
    ];
    const g = groupOutlets(tech, filters)[0];
    expect(g.locations.map((l) => `${l.label}:${l.items.length}`)).toEqual(["Nigeria:1", "US & Canada:2"]);
  });
  it("orders General News: Canada, United States, Nigeria, United Kingdom, the Gulf, then the rest of Europe together", () => {
    const at = (id: string, region: string, country: string) => ({ id, topic: "General News", region, country });
    const news = [
      at("1", "Europe", "Portugal"), at("2", "Middle East", "Qatar"), at("3", "Europe", "United Kingdom"), at("4", "Africa", "Nigeria"), at("5", "Europe", "Germany"),
      at("6", "North America", "United States"), at("7", "Middle East", "United Arab Emirates"), at("8", "North America", "Canada"), at("9", "Africa", "Kenya"), at("10", "Europe", "Switzerland"),
    ];
    const g = groupOutlets(news, filters)[0];
    expect(g.locations.map((l) => l.label)).toEqual(["Canada", "United States", "Nigeria", "United Kingdom", "United Arab Emirates", "Qatar", "Kenya", "Europe"]);
    expect(g.locations[7].items.map((o) => o.id)).toEqual(["1", "5", "10"]);
  });
});

describe("outlet names", () => {
  it("shows the country in brackets for European outlets, and leaves the others alone", () => {
    const eu = (name: string, country: string) => outletTitle({ name, region: "Europe", country });
    expect(eu("Vogue Switzerland", "Switzerland")).toBe("Vogue (Switzerland)");
    expect(eu("Vanity Fair Germany", "Germany")).toBe("Vanity Fair (Germany)");
    expect(eu("Mashable NL", "Netherlands")).toBe("Mashable (Netherlands)");
    expect(eu("Forbes Liechtenstein", "Liechtenstein")).toBe("Forbes (Liechtenstein)");
    expect(eu("Portugal News", "Portugal")).toBe("Portugal News (Portugal)");
    expect(outletTitle({ name: "The Sun (UK)", region: "Europe", country: "United Kingdom" })).toBe("The Sun (UK)");
    expect(outletTitle({ name: "Reuters", region: "North America", country: "United States" })).toBe("Reuters");
  });
});
